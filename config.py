# config.py
import os

USER_IDS = [
    "56413349678",
    "1671387607",
    "11706414183",
    "60460786182",
    "2940087474",
    "50062729418",
    "27451965377",
    "45778329299",
    "64398516412",
    "45098556",
    "67467810580",
    "63504017887",
    "66846646498",
    "55349692730",
]


# Number of days to look back for old posts
DAYS_TO_LOOK_BACK = 100

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
