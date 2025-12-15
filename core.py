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
    def _translate_google(self, word_clean):
        """Самый надежный, но простой перевод (План С)"""
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
            logger.error(f"Google fallback failed too for '{word_clean}': {e}")
            return None

    def _translate_deepl(self, word_clean):
        """Высокоточный перевод через DeepL (План Б)"""
        try:
            # Запрашиваем структуру
            data = ts.translate_text(
                word_clean,
                translator="deepl",
                from_language="en",
                to_language="ru",
                is_detail_result=True,
            )

            # DeepL иногда возвращает строку, иногда словарь. Обрабатываем оба варианта.
            if isinstance(data, str):
                try:
                    data = json.loads(data)
                except:
                    # Если это просто текст перевода
                    return {
                        "word": word_clean,
                        "translation": data,
                        "example_en": "",
                        "example_ru": "",
                    }

            # Парсим JSON структуру DeepL (beams)
            # Структура: result -> translations[0] -> beams -> [sentences -> text]
            variants = []

            # Безопасный доступ к вложенным ключам
            translations = data.get("result", {}).get("translations", [])
            if translations:
                beams = translations[0].get("beams", [])
                for beam in beams:
                    sentences = beam.get("sentences", [])
                    if sentences:
                        text = sentences[0].get("text")
                        if text:
                            variants.append(text)

            if not variants:
                # Если сложная структура не нашлась, пробуем простое поле
                raise ValueError("DeepL structure parsing failed")

            # Берем топ-3 уникальных варианта (чтобы не было спама)
            unique_variants = list(dict.fromkeys(variants))[:3]

            return {
                "word": word_clean,
                "translation": ", ".join(unique_variants),
                "example_en": "",  # DeepL в этом API редко дает примеры
                "example_ru": "",
            }

        except Exception as e:
            logger.warning(
                f"DeepL failed for '{word_clean}': {e}. Switching to Google."
            )
            # Если DeepL не справился - зовем Google
            return self._translate_google(word_clean)

    def fetch_word_data(self, word):
        """
        Умный каскад:
        1. Reverso (Идеал: синонимы + примеры)
        2. DeepL (Отлично: точные синонимы)
        3. Google (База: просто перевод)
        """
        word_clean = word.strip()
        word_count = len(word_clean.split())

        # Если это длинная фраза (больше 4 слов), Reverso и DeepL часто тупят при парсинге.
        # Лучше сразу отдать Google или DeepL (без detail mode)
        if word_count >= 4:
            return self._translate_google(word_clean)

        # --- ПЛАН А: REVERSO ---
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

            # 1. Перевод
            if data.get("translation"):
                synonyms = data.get("translation", [])[:5]
                result["translation"] = ", ".join(synonyms)

            # 2. Контекст
            context = data.get("contextResults", {}).get("results", [])
            for item in context:
                src = item.get("sourceExamples", [])
                tgt = item.get("targetExamples", [])
                if src and tgt:
                    result["example_en"] = (
                        str(src[0]).replace("<em>", "").replace("</em>", "")
                    )
                    result["example_ru"] = (
                        str(tgt[0]).replace("<em>", "").replace("</em>", "")
                    )
                    break

            if not result["translation"]:
                raise ValueError("Reverso returned empty translation")

            return result

        except Exception as e:
            logger.warning(
                f"Reverso failed for '{word}': {e}. Switching to DeepL.", exc_info=True
            )
            # --- ПЛАН Б: DEEPL ---
            return self._translate_deepl(word_clean)


# --- Helper Functions ---


def sanitize_filename(name):
    """Cleans filename from illegal characters."""
    name = unicodedata.normalize("NFKC", name)
    clean = re.sub(r"[^\w\s\(\)\-а-яА-Я]", "", name)
    return clean.strip()[:50]


def parse_clippings_content(content, history_set):
    """Parses the raw content of My Clippings.txt."""
    raw_clips = content.split("==========")
    books_dict = defaultdict(list)
    session_words = set()

    for clip in reversed(raw_clips):
        lines = [line.strip() for line in clip.split("\n") if line.strip()]
        if len(lines) < 2:
            continue

        book_title = lines[0]
        clean_word = lines[-1].strip(' .,?!:;"“”‘’«»()')

        if clean_word and len(clean_word.split()) <= 15:
            word_lower = clean_word.lower()

            if word_lower not in history_set and word_lower not in session_words:
                books_dict[book_title].append(clean_word)
                session_words.add(word_lower)

    return books_dict


def create_csv(data_list, output_path):
    """Generates the final CSV file."""
    try:
        import os

        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        with open(output_path, mode="w", encoding="utf-8-sig", newline="") as file:
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
        return output_path
    except Exception as e:
        logger.error(f"CSV creation failed: {e}")
        return None
