import os

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Key for Yandex Dictionary (Free, allows transcription)
YANDEX_DICT_KEY = os.getenv("YANDEX_DICT_KEY")

# Key for Yandex Cloud (Paid/Grant, smart neural translation)
YANDEX_CLOUD_KEY = os.getenv("YANDEX_CLOUD_KEY")

YANDEX_FOLDER_ID = os.getenv("YANDEX_FOLDER_ID")

TEMP_DIR = "temp_files"
