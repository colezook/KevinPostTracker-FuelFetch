import aiohttp
import asyncio
import os
import json
from datetime import datetime

async def get_user_clips(access_key, user_id, page_id=None):
    url = "https://api.hikerapi.com/v2/user/clips"

    headers = {
        "x-access-key": access_key,
        "accept": "application/json"
    }

    params = {
        "user_id": user_id
    }

    if page_id:
        params["page_id"] = page_id

    print(f"Making request to {url} with params: {params}")

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, params=params) as response:
            print(f"Response status: {response.status}")
            response_text = await response.text()

            if response.status == 200:
                return json.loads(response_text)
            else:
                return f"Error: {response.status}, {response_text}"

def save_json_to_file(data, folder_name):
    # Create the folder if it doesn't exist
    if not os.path.exists(folder_name):
        os.makedirs(folder_name)

    # Generate a filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"user_clips_{timestamp}.json"
    filepath = os.path.join(folder_name, filename)

    # Save the JSON data to the file
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2)

    print(f"JSON data saved to {filepath}")

async def main():
    access_key = os.environ['HAPI_KEY']
    user_id = "50062729418"  # Replace with the actual user ID
    folder_name = "api_output"  # Folder where JSON files will be saved

    print(f"Using access key: {access_key[:5]}...{access_key[-5:]}")
    print(f"Fetching clips for user ID: {user_id}")

    result = await get_user_clips(access_key, user_id)

    if isinstance(result, dict):
        print("Successfully retrieved data from API")
        save_json_to_file(result, folder_name)

        clips = result.get("data", [])
        next_page_id = result.get("next_page_id")
        print(f"Number of clips retrieved: {len(clips)}")
        print(f"Next page ID: {next_page_id}")
    else:
        print(f"An error occurred: {result}")

if __name__ == "__main__":
    asyncio.run(main())