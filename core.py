import csv
import json
import logging
import re
import unicodedata
from collections import defaultdict

import requests
import translators as ts
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


# --- Networking Setup ---
def create_retry_session():
    """Creates a requests session with retry logic to handle network blips."""
    session = requests.Session()
    retries = Retry(
        total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504]
    )
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("https://", adapter)
    return session


NET_SESSION = create_retry_session()


# --- Translator Logic ---
class SmartTranslator:
    def _translate_google(self, word_clean):
        """Fallback method: Uses Google Translate for simple translation."""
        try:
            translation = ts.translate_text(
                word_clean,
                translator="google",
                from_language="en",
                to_language="ru",
            )
            return {
                "word": word_clean,
                "translation": translation,
                "example_en": "",
                "example_ru": "",
            }
        except Exception as e:
            logger.error(f"Google translation failed for '{word_clean}': {e}")
            return None

    def fetch_word_data(self, word):
        """
        Main logic:
        1. If word count < 3: Try Reverso (for context/synonyms).
        2. If word count >= 3 OR Reverso fails: Use Google.
        """
        word_clean = word.strip()
        word_count = len(word_clean.split())

        # CASE 1: Long phrase -> Use Google immediately
        if word_count >= 3:
            return self._translate_google(word_clean)

        # CASE 2: Short word -> Try Reverso first
        try:
            # Request detailed data from Reverso
            data = ts.translate_text(
                word_clean,
                translator="reverso",
                from_language="en",
                to_language="ru",
                is_detail_result=True,
            )

            # Handle potential JSON-in-string response
            if isinstance(data, str):
                data = json.loads(data)

            result = {
                "word": word_clean,
                "translation": "",
                "example_en": "",
                "example_ru": "",
            }

            # 1. Extract Translation (Synonyms)
            if data.get("translation"):
                synonyms = data.get("translation", [])[:5]
                result["translation"] = ", ".join(synonyms)

            # 2. Extract Context Examples
            context = data.get("contextResults", {}).get("results", [])
            for item in context:
                src = item.get("sourceExamples", [])
                tgt = item.get("targetExamples", [])
                if src and tgt:
                    # Clean HTML tags like <em>text</em>
                    result["example_en"] = (
                        str(src[0]).replace("<em>", "").replace("</em>", "")
                    )
                    result["example_ru"] = (
                        str(tgt[0]).replace("<em>", "").replace("</em>", "")
                    )
                    break

            # If Reverso returned empty translation, raise error to trigger fallback
            if not result["translation"]:
                raise ValueError("Reverso returned empty translation")

            return result

        except Exception as e:
            # Log the issue (e.g. Node.js missing or IP ban) but DO NOT CRASH.
            # Switch to Google automatically.
            logger.warning(f"Reverso failed for '{word}': {e}. Switching to Google.")
            return self._translate_google(word_clean)


# --- Parsing & CSV Utils ---


def sanitize_filename(name):
    """Removes illegal characters from filenames."""
    name = unicodedata.normalize("NFKC", name)
    clean = re.sub(r"[^\w\s\(\)\-а-яА-Я]", "", name)
    return clean.strip()[:50]


def parse_clippings_content(content, history_set):
    """Parses 'My Clippings.txt' content."""
    raw_clips = content.split("==========")
    books_dict = defaultdict(list)
    session_words = set()

    for clip in reversed(raw_clips):
        lines = [line.strip() for line in clip.split("\n") if line.strip()]
        if len(lines) < 2:
            continue

        book_title = lines[0]
        # Clean punctuation from the word
        clean_word = lines[-1].strip(' .,?!:;"“”‘’«»()')

        # Filter: Only accept words/phrases with 6 words or less
        # (This prevents translating full sentences)
        if clean_word and len(clean_word.split()) <= 6:
            word_lower = clean_word.lower()

            if word_lower not in history_set and word_lower not in session_words:
                books_dict[book_title].append(clean_word)
                session_words.add(word_lower)

    return books_dict


def create_csv(data_list, output_path):
    """Generates the CSV file for ReWord."""
    try:
        import os

        # Ensure temp directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        with open(output_path, mode="w", encoding="utf-8-sig", newline="") as file:
            writer = csv.writer(file, delimiter=";", quoting=csv.QUOTE_ALL)

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
        return output_path
    except Exception as e:
        logger.error(f"CSV creation failed: {e}")
        return None
