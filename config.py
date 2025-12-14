import os
import sys

from dotenv import load_dotenv

# Load variables from .env file
load_dotenv()

# --- Load Settings ---

# 1. Bot Token
TELEGRAM_BOT_TOKEN = os.getenv("BOT_TOKEN")
if not TELEGRAM_BOT_TOKEN:
    print("Error: BOT_TOKEN not found in .env")
    sys.exit(1)

# 2. Admin ID
admin_id_str = os.getenv("ADMIN_ID")
if not admin_id_str:
    print("Error: ADMIN_ID not found in .env")
    sys.exit(1)
try:
    TELEGRAM_CHAT_ID = int(admin_id_str)
except ValueError:
    print("Error: ADMIN_ID must be an integer")
    sys.exit(1)

# 3. Logic Settings
AUTO_CONFIRM = os.getenv("AUTO_CONFIRM", "False").lower() == "true"

# --- Paths ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# SQLite database file
DB_FILE = os.path.join(BASE_DIR, "bot_database.db")
# Temporary folder for processing files
TEMP_DIR = os.path.join(BASE_DIR, "temp")

# Create temp directory if it does not exist
if not os.path.exists(TEMP_DIR):
    os.makedirs(TEMP_DIR)
