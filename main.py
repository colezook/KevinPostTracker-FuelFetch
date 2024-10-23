import aiohttp
import asyncio
import os
import json
from datetime import datetime, timezone, timedelta
from config import USER_IDS as DEFAULT_USER_IDS, API_BASE_URL, OUTPUT_FOLDER, DAYS_TO_LOOK_BACK, DB_CONFIG
import psycopg2
from psycopg2 import sql
import sys
import argparse

ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
BASE = len(ALPHABET)

def unix_to_utc(timestamp):
    return datetime.fromtimestamp(timestamp, tz=timezone.utc)

def instagram_id_to_url_segment(instagram_id):
    id_num = int(instagram_id)
    result = []
    while id_num > 0:
        result.insert(0, ALPHABET[id_num % BASE])
        id_num //= BASE
    return ''.join(result)

async def get_user_clips(session, access_key, user_id, page_id=None):
    headers = {
        "x-access-key": access_key,
        "accept": "application/json"
    }

    params = {
        "user_id": user_id
    }

    if page_id:
        params["page_id"] = page_id

    print(f"Making request for user {user_id} with params: {params}")

    async with session.get(API_BASE_URL, headers=headers, params=params) as response:
        print(f"Response status for user {user_id}: {response.status}")

        if response.status == 200:
            return await response.json()
        else:
            return f"Error: {response.status}, {await response.text()}"

def save_json_to_file(data, user_id, page_number):
    folder_name = os.path.join(OUTPUT_FOLDER, user_id)
    if not os.path.exists(folder_name):
        os.makedirs(folder_name)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"user_clips_page_{page_number}_{timestamp}.json"
    filepath = os.path.join(folder_name, filename)

    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2)

    print(f"JSON data saved to {filepath}")

def is_older_than_configured_days(taken_at):
    try:
        current_time = datetime.now(timezone.utc)
        post_time = unix_to_utc(taken_at)
        configured_days_ago = current_time - timedelta(days=DAYS_TO_LOOK_BACK)
        return post_time < configured_days_ago
    except (ValueError, OverflowError):
        print(f"Invalid timestamp encountered: {taken_at}")
        return False

def find_old_timestamp(data):
    if isinstance(data, dict):
        for key, value in data.items():
            if key == "taken_at" and isinstance(value, (int, float)):
                if is_older_than_configured_days(value):
                    return value
                else:
                    print(f"Analyzed 'taken_at': {value} (not older than {DAYS_TO_LOOK_BACK} days)")
            elif isinstance(value, (dict, list)):
                result = find_old_timestamp(value)
                if result:
                    return result
    elif isinstance(data, list):
        for item in data:
            result = find_old_timestamp(item)
            if result:
                return result
    return None

async def insert_post_data(conn, cursor, post_data, allowed_user_ids, user_id):
    # Check if the post's user_id is in the allowed_user_ids list
    if str(post_data['user']['pk']) not in allowed_user_ids:
        print(f"Skipping post {post_data['pk']} from user {post_data['user']['pk']} (not in allowed user list)")
        return

    query = sql.SQL("""
    INSERT INTO {} (
        user_id, post_id, username, caption, play_count, comment_count, 
        like_count, save_count, share_count, video_url, cover_url, timestamp, url
    ) VALUES (
        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
    )
    ON CONFLICT (post_id) DO UPDATE SET
        play_count = EXCLUDED.play_count,
        comment_count = EXCLUDED.comment_count,
        like_count = EXCLUDED.like_count,
        save_count = EXCLUDED.save_count,
        share_count = EXCLUDED.share_count,
        updated_at = CURRENT_TIMESTAMP
    """).format(sql.Identifier(f"clips_{user_id}"))

    taken_at = post_data.get('taken_at')
    utc_timestamp = unix_to_utc(taken_at) if taken_at else None
    
    url_segment = instagram_id_to_url_segment(post_data['pk'])
    instagram_url = f"https://www.instagram.com/reel/{url_segment}/"

    caption = post_data.get('caption')
    caption_text = caption.get('text') if isinstance(caption, dict) else None

    values = (
        post_data['user']['pk'],
        post_data['pk'],
        post_data['user']['username'],
        caption_text,
        post_data.get('play_count', 0),
        post_data.get('comment_count', 0),
        post_data.get('like_count', 0),
        post_data.get('save_count') if 'save_count' in post_data else None,
        post_data.get('reshare_count', 0),
        post_data.get('video_url'),
        post_data.get('thumbnail_url'),
        utc_timestamp,
        instagram_url
    )

    cursor.execute(query, values)
    conn.commit()

async def process_user(session, access_key, user_id, allowed_user_ids):
    print(f"Processing user ID: {user_id}")
    next_page_id = None
    page_number = 1
    found_old_post = False

    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()

    try:
        # Check if the table exists for this user_id
        cursor.execute(f"SELECT to_regclass('public.clips_{user_id}')")
        table_exists = cursor.fetchone()[0]

        if not table_exists:
            # Create the table if it doesn't exist
            create_table_query = f"""
            CREATE TABLE clips_{user_id} (
                post_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                username TEXT NOT NULL,
                timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
                play_count INTEGER,
                like_count INTEGER,
                comment_count INTEGER,
                save_count INTEGER,
                share_count INTEGER,
                url TEXT,
                video_url TEXT,
                cover_url TEXT,
                caption TEXT,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE OR REPLACE FUNCTION update_updated_at()
            RETURNS TRIGGER AS $$
            BEGIN
                NEW.updated_at = CURRENT_TIMESTAMP;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;

            CREATE TRIGGER update_clips_{user_id}_updated_at
            BEFORE UPDATE ON clips_{user_id}
            FOR EACH ROW
            EXECUTE FUNCTION update_updated_at();
            """
            cursor.execute(create_table_query)
            conn.commit()
            print(f"Created table clips_{user_id}")

        while not found_old_post:
            result = await get_user_clips(session, access_key, user_id, next_page_id)

            if isinstance(result, dict):
                print(f"\nProcessing data from API for user {user_id} (Page {page_number})")

                save_json_to_file(result, user_id, page_number)

                # Process and insert each post
                for item in result['response']['items']:
                    post_data = item['media']
                    await insert_post_data(conn, cursor, post_data, allowed_user_ids, user_id)

                old_timestamp = find_old_timestamp(result)
                if old_timestamp:
                    post_time = unix_to_utc(old_timestamp)
                    print(f"Found a post older than {DAYS_TO_LOOK_BACK} days for user {user_id}. Taken at: {post_time}")
                    found_old_post = True
                else:
                    print(f"No posts older than {DAYS_TO_LOOK_BACK} days found on this page for user {user_id}.")

                next_page_id = result.get("next_page_id")

                if found_old_post or not next_page_id:
                    print(f"Stopping pagination for user {user_id}.")
                    break

                page_number += 1
            else:
                print(f"An error occurred for user {user_id}: {result}")
                break

        print(f"Total pages fetched for user {user_id}: {page_number}")
    finally:
        cursor.close()
        conn.close()

async def main(user_ids):
    access_key = os.environ['HAPI_KEY']

    print(f"Scraping clips from the IDs: {', '.join(user_ids)}")
    print(f"Timeframe: Last {DAYS_TO_LOOK_BACK} days")
    print(f"Using access key: {access_key[:5]}...{access_key[-5:]}")
    print(f"Using database: {DB_CONFIG['dbname']} on host: {DB_CONFIG['host']}")

    async with aiohttp.ClientSession() as session:
        tasks = [process_user(session, access_key, user_id, user_ids) for user_id in user_ids]
        await asyncio.gather(*tasks)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Process Instagram user clips.')
    parser.add_argument('--user_ids', type=str, help='Comma-separated list of user IDs')
    args = parser.parse_args()

    user_ids_to_process = args.user_ids.split(',') if args.user_ids else DEFAULT_USER_IDS
    asyncio.run(main(user_ids_to_process))
