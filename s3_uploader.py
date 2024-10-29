import boto3
from botocore.exceptions import NoCredentialsError
import requests
from psycopg2 import sql
import os
import logging

# Set up logging
logger = logging.getLogger(__name__)

def get_s3_client():
    aws_access_key_id = os.getenv('AWS_ACCESS_KEY_ID_VBRAIN1.0')
    aws_secret_access_key = os.getenv('AWS_SECRETACCESS_KEY_ID_VBRAIN1.0')

    if not aws_access_key_id or not aws_secret_access_key:
        logger.error("AWS credentials not found in environment variables")
        raise ValueError("AWS credentials not found")

    return boto3.client('s3',
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
        region_name='us-east-1'
    )

def generate_cloudfront_url(s3_url_or_key):
    if s3_url_or_key is None:
        return None
    cloudfront_domain = 'd16ptydiypnzmb.cloudfront.net'  # Your actual CloudFront domain
    # If it's a full S3 URL, extract the object key
    if s3_url_or_key.startswith('http'):
        # Assuming the URL format is https://bucket-name.s3.amazonaws.com/object-key
        object_key = s3_url_or_key.split('.com/')[-1]
    else:
        # If it's already just the object key, use it as is
        object_key = s3_url_or_key
    return f"https://{cloudfront_domain}/{object_key}"

async def upload_to_s3(file_url, bucket_name, object_name):
    s3 = get_s3_client()
    try:
        # Download the file from the URL
        response = requests.get(file_url)
        response.raise_for_status()

        # Upload the file to S3
        s3.put_object(Bucket=bucket_name, Key=object_name, Body=response.content)
        s3_url = f"https://{bucket_name}.s3.amazonaws.com/{object_name}"
        return s3_url
    except requests.exceptions.RequestException as e:
        print(f"Failed to download file from {file_url}: {e}")
        return None
    except NoCredentialsError:
        print("Credentials not available for AWS S3")
        return None

async def upload_media_to_s3_and_update_db(conn, cursor, user_id, total_posts):
    """
    Upload media files to S3 and update database with CloudFront URLs.
    """
    cursor.execute(
        sql.SQL("""
            SELECT post_id, video_url, cover_url 
            FROM {} 
            WHERE (
                (video_url IS NOT NULL AND video_url NOT LIKE 'https://d16ptydiypnzmb.cloudfront.net%') OR 
                (cover_url IS NOT NULL AND cover_url NOT LIKE 'https://d16ptydiypnzmb.cloudfront.net%')
            )
        """).format(sql.Identifier(f"clips_{user_id}"))
    )
    posts = cursor.fetchall()
    
    print(f"\nFound {len(posts)} posts with media to process for user {user_id}")
    
    bucket_name = 'vbrain1.0'
    
    for i, (post_id, video_url, cover_url) in enumerate(posts, 1):
        print(f"\nProcessing media {i}/{len(posts)} for post {post_id}")
        new_video_url = None
        new_cover_url = None
        
        try:
            if video_url and not video_url.startswith('https://d16ptydiypnzmb.cloudfront.net'):
                print(f"[{i}/{len(posts)}] Uploading video for post {post_id}")
                video_object_name = f"fuelvideos/{post_id}_{user_id}.mp4"
                s3_video_url = await upload_to_s3(video_url, bucket_name, video_object_name)
                if s3_video_url:
                    new_video_url = generate_cloudfront_url(video_object_name)
                    print(f"✓ Video uploaded successfully: {new_video_url}")
                else:
                    print(f"✗ Failed to upload video for post {post_id}")
            
            if cover_url and not cover_url.startswith('https://d16ptydiypnzmb.cloudfront.net'):
                print(f"[{i}/{len(posts)}] Uploading cover image for post {post_id}")
                cover_object_name = f"fuelcovers/{post_id}_{user_id}.jpg"
                s3_cover_url = await upload_to_s3(cover_url, bucket_name, cover_object_name)
                if s3_cover_url:
                    new_cover_url = generate_cloudfront_url(cover_object_name)
                    print(f"✓ Cover image uploaded successfully: {new_cover_url}")
                else:
                    print(f"✗ Failed to upload cover image for post {post_id}")
            
            # Update database only if we have new URLs
            if new_video_url or new_cover_url:
                update_query = []
                update_values = []
                
                if new_video_url:
                    update_query.append("video_url = %s")
                    update_values.append(new_video_url)
                
                if new_cover_url:
                    update_query.append("cover_url = %s")
                    update_values.append(new_cover_url)
                
                if update_query:
                    try:
                        query = sql.SQL("""
                            UPDATE {}
                            SET {} 
                            WHERE post_id = %s
                        """).format(
                            sql.Identifier(f"clips_{user_id}"),
                            sql.SQL(", ").join(map(sql.SQL, update_query))
                        )
                        
                        cursor.execute(query, update_values + [post_id])
                        conn.commit()
                        print(f"✓ Database updated successfully for post {post_id}")
                    except Exception as db_error:
                        conn.rollback()  # Rollback the failed transaction
                        print(f"✗ Database update failed for post {post_id}: {str(db_error)}")
                        continue  # Continue with next post
            
            print(f"Completed {i}/{len(posts)} ({(i/len(posts)*100):.1f}%) media conversions for user {user_id}")
            
        except Exception as e:
            conn.rollback()  # Rollback any failed transaction
            print(f"✗ Error processing post {post_id}: {str(e)}")
            continue  # Continue with next post
