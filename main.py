import aiohttp
import asyncio
import os
import json
from datetime import datetime, timezone, timedelta
from config import USER_IDS, API_BASE_URL, OUTPUT_FOLDER, DAYS_TO_LOOK_BACK

def unix_to_utc(timestamp):
    return datetime.fromtimestamp(timestamp, tz=timezone.utc)

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

async def process_user(session, access_key, user_id):
    print(f"Processing user ID: {user_id}")
    next_page_id = None
    page_number = 1
    found_old_post = False

    while not found_old_post:
        result = await get_user_clips(session, access_key, user_id, next_page_id)

        if isinstance(result, dict):
            print(f"\nProcessing data from API for user {user_id} (Page {page_number})")

            save_json_to_file(result, user_id, page_number)

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

async def main():
    access_key = os.environ['HAPI_KEY']

    print(f"Using access key: {access_key[:5]}...{access_key[-5:]}")
    print(f"Looking for posts older than {DAYS_TO_LOOK_BACK} days")

    async with aiohttp.ClientSession() as session:
        tasks = [process_user(session, access_key, user_id) for user_id in USER_IDS]
        await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(main())