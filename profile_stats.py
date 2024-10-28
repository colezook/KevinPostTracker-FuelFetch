import asyncio
import os
import psycopg2
from psycopg2 import sql
from config import USER_IDS as DEFAULT_USER_IDS, DB_CONFIG
import argparse
from hikerapi import Client
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def get_user_profile(client, user_id):
    """Fetch user profile data from Hiker API."""
    try:
        # Call the method without await since it's not an async method
        response = client.user_by_id_v1(id=user_id)
        return response
    except Exception as e:
        logger.error(f"Error fetching profile for user {user_id}: {e}")
        return None

def create_profile_table(cursor, user_id):
    """Create profile table if it doesn't exist."""
    create_table_query = sql.SQL("""
    CREATE TABLE IF NOT EXISTS {} (
        user_id TEXT PRIMARY KEY,
        username TEXT,
        full_name TEXT,
        media_count INTEGER,
        follower_count INTEGER,
        following_count INTEGER,
        biography TEXT,
        external_url TEXT,
        created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """).format(sql.Identifier(f"profile_{user_id}"))

    # Create trigger for updating updated_at
    create_trigger_query = sql.SQL("""
    CREATE OR REPLACE FUNCTION update_profile_updated_at()
    RETURNS TRIGGER AS $$
    BEGIN
        NEW.updated_at = CURRENT_TIMESTAMP;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;

    DROP TRIGGER IF EXISTS {trigger_name} ON {table_name};
    CREATE TRIGGER {trigger_name}
    BEFORE UPDATE ON {table_name}
    FOR EACH ROW
    EXECUTE FUNCTION update_profile_updated_at();
    """).format(
        trigger_name=sql.Identifier(f"update_profile_{user_id}_updated_at"),
        table_name=sql.Identifier(f"profile_{user_id}")
    )

    cursor.execute(create_table_query)
    cursor.execute(create_trigger_query)

async def insert_profile_data(conn, cursor, profile_data, user_id):
    """Insert or update profile data in the database."""
    if not profile_data:
        logger.error(f"No profile data to insert for user {user_id}")
        return False

    # Create table if it doesn't exist
    create_profile_table(cursor, user_id)

    # Insert or update profile data
    upsert_query = sql.SQL("""
    INSERT INTO {} (
        user_id, username, full_name, media_count,
        follower_count, following_count, biography, external_url
    ) VALUES (
        %s, %s, %s, %s, %s, %s, %s, %s
    )
    ON CONFLICT (user_id) DO UPDATE SET
        username = EXCLUDED.username,
        full_name = EXCLUDED.full_name,
        media_count = EXCLUDED.media_count,
        follower_count = EXCLUDED.follower_count,
        following_count = EXCLUDED.following_count,
        biography = EXCLUDED.biography,
        external_url = EXCLUDED.external_url,
        updated_at = CURRENT_TIMESTAMP
    """).format(sql.Identifier(f"profile_{user_id}"))

    try:
        values = (
            profile_data.get('pk'),
            profile_data.get('username'),
            profile_data.get('full_name'),
            profile_data.get('media_count'),
            profile_data.get('follower_count'),
            profile_data.get('following_count'),
            profile_data.get('biography'),
            profile_data.get('external_url')
        )
        
        cursor.execute(upsert_query, values)
        conn.commit()
        print(f"Successfully updated profile data for user {user_id}")
        return True
    except Exception as e:
        logger.error(f"Error inserting profile data for user {user_id}: {e}")
        conn.rollback()
        return False

async def process_user_profile(user_id):
    """Process profile data for a single user."""
    try:
        access_key = os.environ.get('HAPI_KEY')
        if not access_key:
            logger.error("HAPI_KEY environment variable not found")
            return

        client = Client(access_key)
        
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        try:
            profile_data = await get_user_profile(client, user_id)
            if profile_data:
                logger.info(f"Retrieved profile data for user {user_id}: {profile_data}")
                success = await insert_profile_data(conn, cursor, profile_data, user_id)
                if success:
                    print(f"Profile data processed successfully for user {user_id}")
                else:
                    logger.error(f"Failed to process profile data for user {user_id}")
            else:
                logger.error(f"No profile data retrieved for user {user_id}")
        finally:
            cursor.close()
            conn.close()
    except Exception as e:
        logger.error(f"Unexpected error processing user {user_id}: {str(e)}", exc_info=True)

async def main(user_ids):
    """Main function to process profile data for multiple users."""
    print(f"Fetching profile data for users: {', '.join(user_ids)}")
    
    tasks = [process_user_profile(user_id) for user_id in user_ids]
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Process Instagram user profile data.')
    parser.add_argument('--user_ids', type=str, help='Comma-separated list of user IDs')
    args = parser.parse_args()

    user_ids_to_process = args.user_ids.split(',') if args.user_ids else DEFAULT_USER_IDS
    asyncio.run(main(user_ids_to_process))
