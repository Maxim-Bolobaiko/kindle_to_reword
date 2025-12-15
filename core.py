import csv
import logging
import re
import unicodedata
from collections import defaultdict

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import YANDEX_CLOUD_KEY, YANDEX_DICT_KEY

logger = logging.getLogger(__name__)


# --- Networking Setup ---
def create_retry_session():
    """Creates a requests session with retry logic for network stability."""
    session = requests.Session()
    retries = Retry(
        total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504]
    )
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("https://", adapter)
    return session


NET_SESSION = create_retry_session()


class SmartTranslator:
    def _translate_yandex_cloud(self, text):
        """
        Fallback & Phrase Translator: Yandex Cloud Translate API.
        Uses neural networks. Good for phrases and context, but no transcription.
        """
        url = "https://translate.api.cloud.yandex.net/translate/v2/translate"

        headers = {"Authorization": f"Api-Key {YANDEX_CLOUD_KEY}"}

        body = {
            "targetLanguageCode": "ru",
            "texts": [text],
        }

        try:
            resp = NET_SESSION.post(url, json=body, headers=headers, timeout=5)

            if resp.status_code != 200:
                logger.error(f"Cloud API Error {resp.status_code}: {resp.text}")
                return None

            result = resp.json()
            # Response format: {"translations": [{"text": "..."}]}
            translation = result.get("translations", [{}])[0].get("text")

            if not translation:
                return None

            return {
                "word": text,
                "translation": translation,
                "transcription": "",  # Cloud API does not provide transcription
                "example_en": "",
                "example_ru": "",
            }

        except Exception as e:
            logger.error(f"Yandex Cloud request failed: {e}")
            return None

    def _translate_yandex_dict(self, word_clean):
        """
        Primary Translator: Yandex Dictionary API.
        Provides transcription, synonyms, and examples.
        """
        url = "https://dictionary.yandex.net/api/v1/dicservice.json/lookup"
        params = {
            "key": YANDEX_DICT_KEY,
            "lang": "en-ru",
            "text": word_clean,
            "ui": "ru",
        }

        try:
            resp = NET_SESSION.get(url, params=params, timeout=5)
            if resp.status_code != 200:
                logger.warning(f"Dict API Error {resp.status_code}")
                return None

            data = resp.json()
            definitions = data.get("def")

            if not definitions:
                return None

            # 1. Extract Transcription (from the first definition)
            first_def = definitions[0]
            transcription = f"[{first_def.get('ts')}]" if first_def.get("ts") else ""

            # 2. Extract Translations (Aggregate from all parts of speech)
            collected_words = []
            for i, definition in enumerate(definitions):
                translations = definition.get("tr", [])
                if not translations:
                    continue

                # Main translation
                top_tr = translations[0]
                collected_words.append(top_tr["text"])

                # Add synonyms ONLY from the first definition (most frequent)
                if i == 0:
                    syns = [s["text"] for s in top_tr.get("syn", [])][:3]
                    collected_words.extend(syns)

            # Remove duplicates while preserving order
            unique_words = list(dict.fromkeys(collected_words))
            full_translation = ", ".join(unique_words)

            # 3. Extract Example (First valid one found)
            ex_en = ""
            ex_ru = ""
            for definition in definitions:
                for tr in definition.get("tr", []):
                    if tr.get("ex"):
                        first_ex = tr["ex"][0]
                        ex_en = first_ex.get("text")
                        if first_ex.get("tr"):
                            ex_ru = first_ex["tr"][0].get("text")
                        break
                if ex_en:
                    break

            return {
                "word": word_clean,
                "translation": full_translation,
                "transcription": transcription,
                "example_en": ex_en,
                "example_ru": ex_ru,
            }

        except Exception as e:
            logger.error(f"Yandex Dictionary request failed: {e}")
            return None

    def fetch_word_data(self, word):
        """
        Logic:
        1. If 1-2 words -> Try Dictionary (for transcription). If fail -> Cloud.
        2. If 3+ words -> Straight to Cloud.
        """
        word_clean = word.strip()
        word_count = len(word_clean.split())

        # Case A: Phrase (3 words or more) -> Cloud
        if word_count >= 3:
            return self._translate_yandex_cloud(word_clean)

        # Case B: Short word/idiom -> Dictionary first
        dict_result = self._translate_yandex_dict(word_clean)
        if dict_result:
            return dict_result

        # Fallback to Cloud if Dictionary found nothing
        return self._translate_yandex_cloud(word_clean)


# --- Parsing & CSV Utils ---


def sanitize_filename(name):
    """Removes illegal characters from filenames."""
    name = unicodedata.normalize("NFKC", name)
    clean = re.sub(r"[^\w\s\(\)\-а-яА-Я]", "", name)
    return clean.strip()[:50]


def parse_clippings_content(content, history_set):
    """Parses 'My Clippings.txt'."""
    raw_clips = content.split("==========")
    books_dict = defaultdict(list)
    session_words = set()

    for clip in reversed(raw_clips):
        lines = [line.strip() for line in clip.split("\n") if line.strip()]
        if len(lines) < 2:
            continue

        book_title = lines[0]
        clean_word = lines[-1].strip(' .,?!:;"“”‘’«»()')

        # Limit: Max 6 words (to filter out long sentences)
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

        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        with open(output_path, mode="w", encoding="utf-8-sig", newline="") as file:
            writer = csv.writer(file, delimiter=";", quoting=csv.QUOTE_ALL)

            for entry in data_list:
                writer.writerow(
                    [
                        entry["word"],
                        entry.get("transcription", ""),
                        entry["translation"],
                        entry["example_en"],
                        entry["example_ru"],
                    ]
                )
        return output_path
    except Exception as e:
        logger.error(f"CSV creation failed: {e}")
        return None
