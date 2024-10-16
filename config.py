# config.py
import os

USER_IDS = [
    "56413349678",
    "50062729418",
    "45778329299",
    "11706414183",
]


# Number of days to look back for old posts
DAYS_TO_LOOK_BACK = 30

# You can add other configuration variables here if needed
API_BASE_URL = "https://api.hikerapi.com/v2/user/clips"
OUTPUT_FOLDER = "api_output"

# Database configuration using environment variables
DB_CONFIG = {
    "dbname": os.environ['PGDATABASE'],
    "user": os.environ['PGUSER'],
    "password": os.environ['PGPASSWORD'],
    "host": os.environ['PGHOST'],
    "port": os.environ['PGPORT'],
    "sslmode": "require"  # Add this line to enable SSL
}
