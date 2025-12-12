import csv
import json
import logging
import os
import random
import re
import time
import traceback
import unicodedata
from collections import defaultdict

import requests
import translators as ts
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# --- LOGGING SETUP ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# --- CONFIG IMPORT ---
try:
    from config import AUTO_CONFIRM, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
except ImportError:
    logger.critical("Config file not found. Please create config.py.")
    exit()

try:
    import win32com.client

    WIN32_AVAILABLE = True
except ImportError:
    WIN32_AVAILABLE = False
    logger.warning("pywin32 library not found. MTP support disabled.")


# --- CONSTANTS ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
HISTORY_DIR = os.path.join(BASE_DIR, "history")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

HISTORY_FILE = os.path.join(HISTORY_DIR, "processed_words.txt")
CACHE_FILE = os.path.join(DATA_DIR, "translation_cache.json")
LOCAL_CLIPPINGS_FILE = os.path.join(DATA_DIR, "My Clippings.txt")
KINDLE_FILENAME_PART = "Clippings"


# --- NETWORK SESSION SETUP ---
def create_retry_session():
    """
    Creates a requests session with automatic retries for robust networking.
    Retries on common server errors (5xx) and rate limits (429).
    """
    session = requests.Session()
    retries = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "POST", "OPTIONS"],
    )
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


NET_SESSION = create_retry_session()


# --- FUNCTIONS ---


def send_telegram_message(text):
    """
    Sends a simple text message to the configured Telegram chat using the global retry session.
    Args:
        text (str): The message to send.
    """
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
    try:
        NET_SESSION.post(url, data=data, timeout=10)
    except Exception as e:
        logger.error(f"Failed to send Telegram text: {e}")


def notify_error(error_message, exception=None):
    """
    Logs an error to the console and sends a notification to Telegram.
    Args:
        error_message (str): The user-friendly error description.
        exception (Exception, optional): The actual exception object for logging details.
    """
    full_msg = f"ERROR: {error_message}"
    logger.error(full_msg)
    if exception:
        logger.exception("Exception details:")
    send_telegram_message(full_msg)


def setup_directories():
    """
    Creates the necessary directory structure (data, history, output) if it does not exist.
    """
    for folder in [DATA_DIR, HISTORY_DIR, OUTPUT_DIR]:
        if not os.path.exists(folder):
            try:
                os.makedirs(folder)
                logger.info(f"Created directory: {folder}")
            except Exception as e:
                notify_error(f"Failed to create directory {folder}", e)


def sanitize_filename(name):
    """
    Sanitizes a string to be used as a valid filename.
    Uses unicode normalization and removes illegal characters.
    Args:
        name (str): The original string (e.g. book title).
    Returns:
        str: Safe filename string.
    """
    name = unicodedata.normalize("NFKC", name)
    clean = re.sub(r"[^\w\s\(\)\-]", "", name)
    return clean.strip()[:50]


def load_history():
    """
    Loads the set of previously processed words from the history file.
    Returns:
        set: A set of lowercase words.
    """
    if not os.path.exists(HISTORY_FILE):
        return set()
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return set(line.strip().lower() for line in f)
    except Exception as e:
        notify_error("Failed to read history file", e)
        return set()


def update_history(new_words):
    """
    Appends new words to the history file to prevent future duplicates.
    Args:
        new_words (list): List of words to append.
    """
    try:
        with open(HISTORY_FILE, "a", encoding="utf-8") as f:
            for word in new_words:
                f.write(f"{word}\n")
        logger.info("History updated successfully.")
    except Exception as e:
        notify_error("Failed to update history file", e)


# --- CACHE SYSTEM ---


class TranslationCache:
    """
    Simple JSON-based cache system to store translation results locally.
    Reduces API calls and speeds up repeated runs.
    """

    def __init__(self, filepath):
        self.filepath = filepath
        self.cache = self._load()

    def _load(self):
        """Loads cache from JSON file."""
        if not os.path.exists(self.filepath):
            return {}
        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            logger.warning("Failed to load cache, starting fresh.")
            return {}

    def get(self, word):
        """Retrieves data for a word if it exists."""
        return self.cache.get(word.lower())

    def set(self, word, data):
        """Saves data for a word in memory."""
        self.cache[word.lower()] = data

    def save(self):
        """Writes the current cache state to the JSON file."""
        try:
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, ensure_ascii=False, indent=2)
            logger.info("Translation cache saved.")
        except Exception as e:
            logger.error(f"Failed to save cache: {e}")


# --- MTP LOGIC ---


def copy_from_mtp():
    """
    Attempts to locate a connected Kindle device via Windows MTP (Shell API)
    and copy the 'My Clippings.txt' file to the local data directory.
    Returns:
        bool: True if successful, False otherwise.
    """
    if not WIN32_AVAILABLE:
        return False

    logger.info("Searching for Kindle (MTP)...")
    try:
        shell = win32com.client.Dispatch("Shell.Application")
        computer = shell.NameSpace(17)

        found_kindle = None
        for item in computer.Items():
            if "Kindle" in item.Name:
                logger.info(f"Device found: {item.Name}")
                found_kindle = item
                break

        if not found_kindle:
            return False

        def find_file_recursive(folder, target_part, depth=0):
            if depth > 3:
                return None
            for item in folder.GetFolder.Items():
                if (
                    not item.IsFolder
                    and target_part.lower() in item.Name.lower()
                    and item.Name.endswith(".txt")
                ):
                    return item
                if item.IsFolder:
                    if item.Name in [
                        "Internal Storage",
                        "documents",
                        "internal documents",
                    ]:
                        res = find_file_recursive(item, target_part, depth + 1)
                        if res:
                            return res
            return None

        file_item = find_file_recursive(found_kindle, KINDLE_FILENAME_PART)

        if file_item:
            logger.info(f"File found on device: {file_item.Name}")
            target_path = os.path.join(DATA_DIR, file_item.Name)

            if os.path.exists(target_path):
                try:
                    os.remove(target_path)
                except Exception as e:
                    logger.warning(f"Failed to remove old file: {e}")

            dest_folder = shell.NameSpace(DATA_DIR)
            dest_folder.CopyHere(file_item, 276)
            logger.info("File copied to data folder.")

            if target_path != LOCAL_CLIPPINGS_FILE:
                if os.path.exists(LOCAL_CLIPPINGS_FILE):
                    os.remove(LOCAL_CLIPPINGS_FILE)
                os.rename(target_path, LOCAL_CLIPPINGS_FILE)
            return True
        else:
            return False

    except Exception as e:
        logger.exception("MTP copy failed")
        notify_error("MTP copy failed", e)
        return False


def parse_kindle_clippings(file_path, history_set):
    """
    Parses the Kindle clippings file and groups words by book.
    Filters out duplicates (history & session) and phrases longer than 5 words.
    Args:
        file_path (str): Path to clippings text file.
        history_set (set): Set of words already processed.
    Returns:
        dict: {book_title: [word_list]}
    """
    logger.info(f"Analyzing file: {file_path}")
    try:
        with open(file_path, "r", encoding="utf-8-sig") as f:
            content = f.read()
    except Exception as e:
        notify_error(f"Failed to open file {file_path}", e)
        return {}

    raw_clips = content.split("==========")
    books_dict = defaultdict(list)
    session_words_lower = set()

    for clip in reversed(raw_clips):
        lines = [line.strip() for line in clip.split("\n") if line.strip()]

        if len(lines) < 2:
            continue

        book_title = lines[0]
        # The content is usually the last non-empty line
        clean_word = lines[-1].strip(' .,?!:;"“”‘’')
        clean_word_lower = clean_word.lower()

        if clean_word and len(clean_word.split()) <= 5:
            if clean_word_lower in history_set:
                continue
            if clean_word_lower in session_words_lower:
                continue

            books_dict[book_title].append(clean_word)
            session_words_lower.add(clean_word_lower)

    return books_dict


# --- TRANSLATOR ---


class ReversoTranslator:
    """
    Handles translation logic using Reverso Context API with Caching.
    """

    def __init__(self, cache_system):
        self.cache_system = cache_system

    def fetch_word_data(self, word):
        """
        Fetches detailed translation (synonyms, context) for a word.
        Checks local cache first, then API.
        Args:
            word (str): English word or phrase.
        Returns:
            dict or None: Translation data structure.
        """
        # 1. Check Cache first
        cached_data = self.cache_system.get(word)
        if cached_data:
            return cached_data

        # 2. If not in cache, fetch from Web
        try:
            data = ts.translate_text(
                word,
                translator="reverso",
                from_language="en",
                to_language="ru",
                is_detail_result=True,
            )

            if isinstance(data, str):
                try:
                    data = json.loads(data)
                except json.JSONDecodeError:
                    return None

            if not isinstance(data, dict):
                return None

            result = {
                "word": word.strip(),
                "translation": "",
                "example_en": "",
                "example_ru": "",
            }
            collected_synonyms = []
            seen_synonyms = set()

            translation_list = data.get("translation")
            if isinstance(translation_list, list) and translation_list:
                main = translation_list[0]
                collected_synonyms.append(main)
                seen_synonyms.add(main.lower())

            context_results = data.get("contextResults", {}).get("results", [])
            if not isinstance(context_results, list):
                context_results = []

            for item in context_results:
                if not isinstance(item, dict):
                    continue

                rus = item.get("translation")
                if not rus or not isinstance(rus, str):
                    continue

                if rus.lower() == word.lower():
                    continue
                if rus.lower() not in seen_synonyms:
                    collected_synonyms.append(rus)
                    seen_synonyms.add(rus.lower())

                if not result["example_en"]:
                    src = item.get("sourceExamples", [])
                    tgt = item.get("targetExamples", [])
                    if (isinstance(src, list) and src) and (
                        isinstance(tgt, list) and tgt
                    ):
                        result["example_en"] = (
                            str(src[0]).replace("<em>", "").replace("</em>", "")
                        )
                        result["example_ru"] = (
                            str(tgt[0]).replace("<em>", "").replace("</em>", "")
                        )

            result["translation"] = ", ".join(collected_synonyms[:5])

            final_res = result if result["translation"] else None

            # 3. Save to Cache if successful
            if final_res:
                self.cache_system.set(word, final_res)

            return final_res

        except Exception as e:
            logger.warning(f"Translation failed for '{word}': {e}")
            return None


def save_to_csv(data_list, filename):
    """
    Saves a list of word dictionaries to a ReWord-compatible CSV file.
    Args:
        data_list (list): List of dicts with word data.
        filename (str): Name of the CSV file.
    Returns:
        str: Full path to the saved file or None on failure.
    """
    full_path = os.path.join(OUTPUT_DIR, filename)
    try:
        with open(full_path, mode="w", encoding="utf-8-sig", newline="") as file:
            writer = csv.writer(file, delimiter=";", quoting=csv.QUOTE_ALL)
            writer.writerow(
                ["Word", "Transcription", "Translation", "Example", "Ex.Translation"]
            )
            for entry in data_list:
                writer.writerow(
                    [
                        entry["word"],
                        "",
                        entry["translation"],
                        entry["example_en"],
                        entry["example_ru"],
                    ]
                )
        logger.info(f"CSV saved: {filename}")
        return full_path
    except Exception as e:
        notify_error(f"Failed to save CSV {filename}", e)
        return None


def send_to_telegram_doc(file_path, caption=""):
    """
    Uploads a file to Telegram with retry logic.
    Args:
        file_path (str): Path to the file to upload.
        caption (str): Caption text (supports emojis).
    Returns:
        bool: True if successful, False otherwise.
    """
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendDocument"
    filename = os.path.basename(file_path)
    logger.info(f"Sending to Telegram: {filename}...")

    for attempt in range(1, 4):
        try:
            with open(file_path, "rb") as f:
                files = {"document": f}
                data = {"chat_id": TELEGRAM_CHAT_ID, "caption": caption}
                r = NET_SESSION.post(url, files=files, data=data, timeout=30)

                if r.status_code == 200:
                    return True
                else:
                    logger.error(f"Telegram returned status {r.status_code}: {r.text}")

        except requests.exceptions.RequestException as e:
            logger.warning(f"Network error (attempt {attempt}): {e}")

        if attempt < 3:
            time.sleep(3)

    notify_error(f"Failed to send {filename} after 3 attempts.")
    return False


# --- MAIN ---
if __name__ == "__main__":
    try:
        setup_directories()
        history = load_history()

        # Init Cache and Translator
        cache = TranslationCache(CACHE_FILE)
        translator = ReversoTranslator(cache)

        print("\n--- KINDLE TO REWORD ---")

        copy_success = copy_from_mtp()
        target_file = None

        if copy_success:
            target_file = LOCAL_CLIPPINGS_FILE
        elif os.path.exists(LOCAL_CLIPPINGS_FILE):
            logger.warning("Kindle not found.")
            mod_time = os.path.getmtime(LOCAL_CLIPPINGS_FILE)
            time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(mod_time))
            print(f"Local file available from: {time_str}")

            choice = input("Use local file? (y/n): ")
            if choice.lower() == "y":
                target_file = LOCAL_CLIPPINGS_FILE
                logger.info("Using local file.")
            else:
                logger.info("Operation cancelled.")
                exit()
        else:
            logger.error("No Kindle and no local file found.")
            exit()

        books_data = parse_kindle_clippings(target_file, history)

        if not books_data:
            print("No new words found.")
        else:
            total_words = sum(len(v) for v in books_data.values())
            print(f"\nFound {total_words} new words in {len(books_data)} books.")

            should_process = False
            if AUTO_CONFIRM:
                should_process = True
            else:
                ans = input("\nProceed with translation? (y/n): ")
                if ans.lower() == "y":
                    should_process = True

            if should_process:
                global_successful_words = []

                for book_title, words in books_data.items():
                    print(f"\nBook: {book_title}")
                    book_data = []
                    current_book_successful_words = []

                    for word in words:
                        print(f"   {word}...", end=" ")

                        # Fetch (Web or Cache)
                        info = translator.fetch_word_data(word)

                        if info:
                            book_data.append(info)
                            current_book_successful_words.append(word)
                            print("[OK]")
                        else:
                            print("[FAIL]")

                        # Delay only if not cached (to be polite to Reverso)
                        if not cache.get(word):
                            time.sleep(random.uniform(1.0, 2.0))

                    if book_data:
                        safe_name = sanitize_filename(book_title)
                        current_date = time.strftime("%d.%m.%Y__%H-%M")
                        filename = f"{safe_name}_{current_date}.csv"

                        full_csv_path = save_to_csv(book_data, filename)

                        if full_csv_path:
                            # Caption for Telegram (Emojis kept here)
                            caption = f"📕 {book_title}\n📅 {current_date}\nСлов: {len(book_data)}"

                            if send_to_telegram_doc(full_csv_path, caption):
                                global_successful_words.extend(
                                    current_book_successful_words
                                )
                        else:
                            logger.error(f"File save failed: {book_title}")

                # Save cache to disk
                cache.save()

                if global_successful_words:
                    update_history(global_successful_words)
                    print("\nSuccess. History updated.")
                else:
                    print("\nHistory not updated.")

    except KeyboardInterrupt:
        print("\nStopped by user.")
    except Exception as critical_e:
        notify_error("Critical script error", critical_e)
        traceback.print_exc()
