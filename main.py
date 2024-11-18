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
from s3_uploader import upload_media_to_s3_and_update_db  # Import only the necessary function
import time
from contextlib import contextmanager
import psycopg2.pool
from psycopg2.pool import PoolError

ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
BASE = len(ALPHABET)
MAX_DB_RETRIES = 5
DB_RETRY_DELAY = 10
DB_KEEPALIVE_INTERVAL = 30
MIN_POOL_SIZE = 3
MAX_POOL_SIZE = 20
POOL_TIMEOUT = 30

# Add semaphore for limiting concurrent DB operations
DB_SEMAPHORE_LIMIT = 5  # Adjust based on your MAX_POOL_SIZE

# Create a global connection pool
db_pool = None

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

    # First check if post exists and get its current URLs
    cursor.execute(
        "SELECT video_url, cover_url FROM clips WHERE post_id = %s",
        [post_data['pk']]
    )
    existing_urls = cursor.fetchone()

    # Keep existing Cloudfront URLs if they exist
    video_url = post_data.get('video_url')
    cover_url = post_data.get('thumbnail_url')
    
    if existing_urls:
        existing_video_url, existing_cover_url = existing_urls
        if existing_video_url and existing_video_url.startswith('https://d16ptydiypnzmb.cloudfront.net'):
            video_url = existing_video_url
        if existing_cover_url and existing_cover_url.startswith('https://d16ptydiypnzmb.cloudfront.net'):
            cover_url = existing_cover_url

    taken_at = post_data.get('taken_at')
    utc_timestamp = unix_to_utc(taken_at) if taken_at else None
    
    url_segment = instagram_id_to_url_segment(post_data['pk'])
    instagram_url = f"https://www.instagram.com/reel/{url_segment}/"

    caption = post_data.get('caption')
    caption_text = caption.get('text') if isinstance(caption, dict) else None

    values = (
        post_data['user']['pk'],                                      # user_id
        post_data['pk'],                                             # post_id
        post_data['user']['username'],                               # username
        caption_text,                                                # caption
        post_data.get('play_count', 0),                             # play_count
        post_data.get('comment_count', 0),                          # comment_count
        post_data.get('like_count', 0),                             # like_count
        post_data.get('save_count') if 'save_count' in post_data else None,  # save_count
        post_data.get('reshare_count', 0),                          # share_count
        video_url,                                                   # video_url
        cover_url,                                                   # cover_url
        utc_timestamp,                                              # timestamp
        instagram_url                                               # url
    )

    # Add retry logic for database operations
    for attempt in range(MAX_DB_RETRIES):
        try:
            query = """
                INSERT INTO clips (
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
                    video_url = CASE 
                        WHEN clips.video_url IS NULL OR NOT clips.video_url LIKE %s
                        THEN EXCLUDED.video_url
                        ELSE clips.video_url
                    END,
                    cover_url = CASE 
                        WHEN clips.cover_url IS NULL OR NOT clips.cover_url LIKE %s
                        THEN EXCLUDED.cover_url
                        ELSE clips.cover_url
                    END,
                    updated_at = CURRENT_TIMESTAMP
            """
            
            # Add the cloudfront pattern to the values tuple for the LIKE conditions
            cloudfront_pattern = 'https://d16ptydiypnzmb.cloudfront.net%'
            all_values = values + (cloudfront_pattern, cloudfront_pattern)
            
            cursor.execute(query, all_values)
            conn.commit()
            return  # Success
        except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
            if attempt == MAX_DB_RETRIES - 1:
                print(f"Failed to insert post {post_data['pk']} after {MAX_DB_RETRIES} attempts")
                raise
            print(f"Database operation attempt {attempt + 1} failed, retrying in {DB_RETRY_DELAY} seconds...")
            time.sleep(DB_RETRY_DELAY)

@contextmanager
def get_db_connection():
    """Context manager for getting a connection from the pool with retry logic"""
    global db_pool
    conn = None
    
    for attempt in range(MAX_DB_RETRIES):
        try:
            conn = db_pool.getconn()
            if conn:
                try:
                    # Set session characteristics
                    conn.set_session(autocommit=False)
                    conn.set_client_encoding('UTF8')
                    yield conn
                finally:
                    # Always return connection to pool
                    if conn:
                        try:
                            if conn.closed == 0:  # If connection is still open
                                conn.rollback()  # Rollback any uncommitted changes
                            db_pool.putconn(conn)
                        except Exception as e:
                            print(f"Error returning connection to pool: {e}")
                return
        except (psycopg2.OperationalError, psycopg2.InterfaceError, PoolError) as e:
            if conn:
                try:
                    db_pool.putconn(conn, close=True)
                except:
                    pass
                conn = None
            
            if attempt == MAX_DB_RETRIES - 1:  # Last attempt
                print(f"Failed to get connection from pool after {MAX_DB_RETRIES} attempts: {str(e)}")
                raise
            print(f"Database connection attempt {attempt + 1} failed, retrying in {DB_RETRY_DELAY} seconds... Error: {str(e)}")
            time.sleep(DB_RETRY_DELAY)
            
            # Try to reinitialize the pool if we're having connection issues
            try:
                init_db_pool()
            except:
                pass

async def process_user(session, access_key, user_id, allowed_user_ids, semaphore):
    """Modified to use semaphore for DB connection management"""
    print(f"Processing user ID: {user_id}")
    next_page_id = None
    page_number = 1
    found_old_post = False
    posts_to_process = []

    # Use semaphore to limit concurrent DB operations
    async with semaphore:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            try:
                # Check if the clips table exists
                cursor.execute("SELECT to_regclass('public.clips')")
                table_exists = cursor.fetchone()[0]

                if not table_exists:
                    # Create the table if it doesn't exist
                    create_table_query = """
                    CREATE TABLE clips (
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

                    CREATE TRIGGER update_clips_updated_at
                    BEFORE UPDATE ON clips
                    FOR EACH ROW
                    EXECUTE FUNCTION update_updated_at();

                    CREATE INDEX idx_clips_user_id ON clips(user_id);
                    CREATE INDEX idx_clips_timestamp ON clips(timestamp);
                    """
                    cursor.execute(create_table_query)
                    conn.commit()
                    print("Created table clips with indexes")

                while not found_old_post:
                    result = await get_user_clips(session, access_key, user_id, next_page_id)

                    if isinstance(result, dict):
                        print(f"\nProcessing data from API for user {user_id} (Page {page_number})")

                        save_json_to_file(result, user_id, page_number)

                        # Collect posts for processing
                        for item in result['response']['items']:
                            post_data = item['media']
                            if str(post_data['user']['pk']) in allowed_user_ids:
                                posts_to_process.append(post_data)
                            else:
                                print(f"Skipping post {post_data['pk']} from user {post_data['user']['pk']} (not in allowed user list)")

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
                print(f"Found {len(posts_to_process)} posts to process for user {user_id}")
                print("Inserting posts into database...")

                # Process posts in batches (silently)
                for post_data in posts_to_process:
                    await insert_post_data(conn, cursor, post_data, allowed_user_ids, user_id)
                    
                print(f"Successfully inserted {len(posts_to_process)} posts into database")

            finally:
                cursor.close()

def init_db_pool():
    """Initialize the database connection pool"""
    global db_pool
    try:
        db_pool = psycopg2.pool.SimpleConnectionPool(
            MIN_POOL_SIZE,
            MAX_POOL_SIZE,
            **DB_CONFIG,
            keepalives=1,
            keepalives_idle=DB_KEEPALIVE_INTERVAL,
            keepalives_interval=DB_KEEPALIVE_INTERVAL,
            keepalives_count=5
        )
        print(f"Created connection pool with {MIN_POOL_SIZE} to {MAX_POOL_SIZE} connections")
    except psycopg2.Error as e:
        print(f"Error creating connection pool: {e}")
        raise

def cleanup_db_pool():
    """Clean up the database connection pool"""
    global db_pool
    if db_pool:
        db_pool.closeall()
        print("Closed all database connections in the pool")

async def main(user_ids):
    access_key = os.environ['HAPI_KEY']
    
    print(f"Scraping clips from the IDs: {', '.join(user_ids)}")
    print(f"Timeframe: Last {DAYS_TO_LOOK_BACK} days")
    print(f"Using access key: {access_key[:5]}...{access_key[-5:]}")
    print(f"Using database: {DB_CONFIG['dbname']} on host: {DB_CONFIG['host']}")

    # Initialize the connection pool
    init_db_pool()
    
    # Create semaphore for limiting concurrent DB operations
    semaphore = asyncio.Semaphore(DB_SEMAPHORE_LIMIT)

    async with aiohttp.ClientSession() as session:
        try:
            # Create tasks with semaphore
            clips_tasks = [
                process_user(session, access_key, user_id, user_ids, semaphore) 
                for user_id in user_ids
            ]

            # Run clips tasks concurrently
            await asyncio.gather(*clips_tasks)
        except Exception as e:
            print(f"Error during processing: {str(e)}")
            raise
        finally:
            cleanup_db_pool()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Process Instagram user clips and profiles.')
    parser.add_argument('--user_ids', type=str, help='Comma-separated list of user IDs')
    args = parser.parse_args()

    user_ids_to_process = args.user_ids.split(',') if args.user_ids else DEFAULT_USER_IDS
    asyncio.run(main(user_ids_to_process))