# config.py
import os

USER_IDS = [
    "58916637091",
    "62584671960",
    "62582654993",
    "56993024596",
    "60079583626",
    "64026646834",
    "60164717043",
    "47411093205",
    "48871716256",
    "47342895164",
    "47115255959",
    "64582096899",
    "64385655319",
    "64041068777",
    "64393485278",
    "64241648371",
    "69417922840",
    "64568107636",
    "59184886264",
    "58972024942",
    "69423074382",
    "64400068675",
    "64174919342",
    "60612580669",
    "60418301335",
    "62752303281",
    "61120897001",
    "64402276598",
    "68919961665",
    "61002144457",
    "60343660883",
    "68854357506",
    "60604355011",
    "60173887870",
    "63060704607",
    "60888060200",
    "60488039622",
    "54983805051",
    "60558470794",
    "59086230185",
    "65715085597",
    "46054970930",
    "61837194708",
    "48694298932",
    "60670828469",
    "47734694486",
    "48787952428",
    "60805158025",
    "56080813489",
    "68907499258",
    "68775834543",
    "55000706515",
    "48272772540",
    "60450538986",
    "68922115931",
    "68346828483",
    "285659578",
    "68713830537",
    "68850837860",
    "48144493470",
    "56542482786",
    "69004286127",
    "55456477801",
    "49018516078",
    "498478492",
    "48542658776",
    "60198605217",
    "55746750682",
    "58889959053",
    "64735118312",
    "68816751468",
    "56020117830",
    "47238730159",
    "65123595268",
    "65902509536",
    "48031270577",
    "59444554120",
    "572736748",
    "60070087677",
    "7690789389",
    "41940187",
    "389839482",
    "494261252",
    "285115958",
    "66358113469",
    "255258901",
    "257914971",
    "56364616975",
    "69426886574",
    "65903006417",
    "48644766387",
    "442610255",
    "61412873536",
    "61166346053",
    "65946740681",
    "56703878423",
    "55883121445",
    "60989155125",
    "69427589827",
    "365086782",
    "60500944535",
    "59397409435",
    "65224054578",
]


# Number of days to look back for old posts
DAYS_TO_LOOK_BACK = 180

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
