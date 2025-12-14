import csv
import json
import logging
import os
import re
import unicodedata
from collections import defaultdict

import requests
import translators as ts
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


# --- Networking ---
def create_retry_session():
    """Creates a requests session with retry logic."""
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
    def fetch_word_data(self, word):
        """
        Determines the translation engine based on word count.
        - < 3 words: Reverso (Context, Synonyms)
        - >= 3 words: Google (Direct translation)
        """
        word_clean = word.strip()
        word_count = len(word_clean.split())

        # BRANCH 1: Long phrase -> Google Translate
        if word_count >= 3:
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
                    "example_en": "",  # No redundant context for long phrases
                    "example_ru": "",
                }
            except Exception as e:
                logger.error(f"Google translate failed for '{word}': {e}")
                # Fallback to Reverso is possible here, but usually unnecessary
                return None

        # BRANCH 2: Short word/phrase -> Reverso Context
        try:
            data = ts.translate_text(
                word_clean,
                translator="reverso",
                from_language="en",
                to_language="ru",
                is_detail_result=True,
            )

            if isinstance(data, str):
                data = json.loads(data)

            result = {
                "word": word_clean,
                "translation": "",
                "example_en": "",
                "example_ru": "",
            }

            # 1. Main translation
            if data.get("translation"):
                # Take top 5 synonyms
                synonyms = data.get("translation", [])[:5]
                result["translation"] = ", ".join(synonyms)

            # 2. Context examples
            context = data.get("contextResults", {}).get("results", [])
            for item in context:
                src = item.get("sourceExamples", [])
                tgt = item.get("targetExamples", [])
                if src and tgt:
                    # Clean HTML tags
                    result["example_en"] = (
                        str(src[0]).replace("<em>", "").replace("</em>", "")
                    )
                    result["example_ru"] = (
                        str(tgt[0]).replace("<em>", "").replace("</em>", "")
                    )
                    break

            return result if result["translation"] else None

        except Exception as e:
            logger.warning(f"Reverso failed for '{word}': {e}")
            return None


# --- Helper Functions ---


def sanitize_filename(name):
    """Cleans filename from illegal characters."""
    name = unicodedata.normalize("NFKC", name)
    # Allow alphanumeric, spaces, parenthesis, hyphens
    clean = re.sub(r"[^\w\s\(\)\-а-яА-Я]", "", name)
    return clean.strip()[:50]


def parse_clippings_content(content, history_set):
    """
    Parses the raw content of My Clippings.txt.
    Returns: dict {book_title: [list_of_words]}
    """
    raw_clips = content.split("==========")
    books_dict = defaultdict(list)
    session_words = set()

    for clip in reversed(raw_clips):
        lines = [line.strip() for line in clip.split("\n") if line.strip()]
        if len(lines) < 2:
            continue

        book_title = lines[0]
        # Clean punctuation from the highlighted text
        clean_word = lines[-1].strip(' .,?!:;"“”‘’«»()')

        # Max length filter (e.g., skip extremely long highlights > 15 words)
        if clean_word and len(clean_word.split()) <= 15:
            word_lower = clean_word.lower()

            # Check against DB history and current session duplicates
            if word_lower not in history_set and word_lower not in session_words:
                books_dict[book_title].append(clean_word)
                session_words.add(word_lower)

    return books_dict


def create_csv(data_list, output_path):
    """Generates the final CSV file."""
    try:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, mode="w", encoding="utf-8-sig", newline="") as file:
            writer = csv.writer(file, delimiter=";", quoting=csv.QUOTE_ALL)

            for entry in data_list:
                writer.writerow(
                    [
                        entry["word"],
                        "",  # Transcription is left empty
                        entry["translation"],
                        entry["example_en"],
                        entry["example_ru"],
                    ]
                )
        return output_path
    except Exception as e:
        logger.error(f"CSV creation failed: {e}")
        return None
