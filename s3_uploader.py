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

async def upload_media_to_s3_and_update_db(conn, cursor, user_id):
    bucket_name = 'vbrain1.0'
    all_successful = True
    
    # Fetch all posts that need to be uploaded
    cursor.execute(sql.SQL("SELECT post_id, video_url, cover_url FROM {}").format(sql.Identifier(f"clips_{user_id}")))
    posts = cursor.fetchall()

    for post_id, video_url, cover_url in posts:
        try:
            # Upload video to S3
            if video_url:
                video_s3_url = await upload_to_s3(video_url, bucket_name, f"fuelcovers/{post_id}_{user_id}.mp4")
                video_cloudfront_url = generate_cloudfront_url(video_s3_url)
            else:
                video_cloudfront_url = None

            # Upload cover to S3
            if cover_url:
                cover_s3_url = await upload_to_s3(cover_url, bucket_name, f"fuelcovers/{post_id}_{user_id}.jpg")
                cover_cloudfront_url = generate_cloudfront_url(cover_s3_url)
            else:
                cover_cloudfront_url = None

            # Update the database with the new CloudFront URLs
            update_query = sql.SQL("""
            UPDATE {} SET
                video_url = %s,
                cover_url = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE post_id = %s
            """).format(sql.Identifier(f"clips_{user_id}"))

            cursor.execute(update_query, (video_cloudfront_url, cover_cloudfront_url, post_id))
            conn.commit()
        except Exception as e:
            print(f"Error uploading {post_id} to S3 Bucket: {e}")
            all_successful = False

    if all_successful:
        print("All Cloudfront URLs Generated & Inserted")
