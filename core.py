import csv
import json
import logging
import re
import unicodedata
from collections import defaultdict

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import YANDEX_CLOUD_KEY, YANDEX_DICT_KEY, YANDEX_FOLDER_ID

logger = logging.getLogger(__name__)


# --- Networking Setup ---
def create_retry_session():
    session = requests.Session()
    retries = Retry(
        total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504]
    )
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("https://", adapter)
    return session


NET_SESSION = create_retry_session()


class SmartTranslator:
    def _ask_yandex_gpt(self, word):
        """
        Uses YandexGPT to lemmatize and translate words, phrases, and idioms.
        Returns dict: {'lemma': '...', 'ru': '...'} or None on failure.
        """
        url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"

        payload = {
            "modelUri": f"gpt://{YANDEX_FOLDER_ID}/yandexgpt/latest",
            "completionOptions": {
                "stream": False,
                "temperature": 0.1,
                "maxTokens": 100,
            },
            "messages": [
                {
                    "role": "system",
                    "text": (
                        "Ты профессиональный лингвист-переводчик. Твоя задача: найти начальную словарную форму (лемму) "
                        "и перевод для английского текста (слова или фразы)."
                        "\n\nПравила:"
                        "\n1. Глаголы (went) -> Инфинитив (go)."
                        "\n2. Существительные (mice) -> Ед. число (mouse)."
                        "\n3. Фразовые глаголы (took off) -> Начальная форма (take off)."
                        "\n4. Идиомы (piece of cake) -> Оставляй как есть (piece of cake)."
                        "\n5. Если это устойчивое выражение, переводи его целиком по смыслу."
                        '\n\nОтвет СТРОГО в JSON: {"lemma": "english_base", "ru": "русский_перевод"}. '
                        "Без лишнего текста."
                    ),
                },
                {"role": "user", "text": f"Текст: {word}"},
            ],
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Api-Key {YANDEX_CLOUD_KEY}",
            "x-folder-id": YANDEX_FOLDER_ID,
        }

        try:
            resp = NET_SESSION.post(url, headers=headers, json=payload, timeout=10)
            if resp.status_code != 200:
                logger.error(f"GPT Error {resp.status_code}: {resp.text}")
                return None

            result = resp.json()
            raw_text = result["result"]["alternatives"][0]["message"]["text"]

            clean_json = raw_text.replace("```json", "").replace("```", "").strip()
            data = json.loads(clean_json)

            # --- FIX ---
            if isinstance(data, list):
                if len(data) > 0 and isinstance(data[0], dict):
                    return data[0]
                else:
                    logger.warning(
                        f"GPT returned empty or invalid list for word: {word}"
                    )
                    return None

            if not isinstance(data, dict):
                logger.warning(
                    f"GPT returned unexpected type {type(data)} for word: {word}"
                )
                return None

            return data

        except Exception as e:
            logger.error(f"GPT Exception: {e}")
            return None

    def _lookup_dictionary(self, text):
        """Standard Dictionary API lookup."""
        url = "https://dictionary.yandex.net/api/v1/dicservice.json/lookup"
        params = {"key": YANDEX_DICT_KEY, "lang": "en-ru", "text": text, "ui": "ru"}
        try:
            resp = NET_SESSION.get(url, params=params, timeout=5)
            if resp.status_code == 200:
                return resp.json().get("def", [])
        except Exception:
            pass
        return None

    def fetch_word_data(self, word):
        word_clean = word.strip()

        # 1. Ask AI for the Lemma
        ai_data = self._ask_yandex_gpt(word_clean)

        final_lemma = word_clean
        ai_translation = ""

        if ai_data:
            final_lemma = ai_data.get("lemma", word_clean)
            ai_translation = ai_data.get("ru", "")

        # 2. Enrich with Dictionary Data
        dict_defs = self._lookup_dictionary(final_lemma)

        # 3. Pack the Result
        transcription = ""
        full_translation = ai_translation
        ex_en = ""
        ex_ru = ""

        if dict_defs:
            first_def = dict_defs[0]

            if first_def.get("ts"):
                transcription = f"[{first_def.get('ts')}]"

            collected_words = []
            if ai_translation:
                collected_words.append(ai_translation)

            for definition in dict_defs:
                for tr_entry in definition.get("tr", []):
                    collected_words.append(tr_entry["text"])
                    syns = [s["text"] for s in tr_entry.get("syn", [])][:3]
                    collected_words.extend(syns)

            unique_words = list(dict.fromkeys(collected_words))
            full_translation = ", ".join(unique_words)

            for definition in dict_defs:
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
            "word": final_lemma,
            "translation": full_translation,
            "transcription": transcription,
            "example_en": ex_en,
            "example_ru": ex_ru,
        }


# --- Parsing & CSV Utils ---


def sanitize_filename(name):
    name = unicodedata.normalize("NFKC", name)
    clean = re.sub(r"[^\w\s\(\)\-а-яА-Я]", "", name)
    return clean.strip()[:50]


def parse_clippings_content(content, history_set):
    if "==========" not in content:
        return None
    raw_clips = content.split("==========")
    books_dict = defaultdict(list)
    session_words = set()
    for clip in reversed(raw_clips):
        lines = [line.strip() for line in clip.split("\n") if line.strip()]
        if len(lines) < 2:
            continue
        book_title = lines[0]
        clean_word = lines[-1].strip(' .,?!:;"“”‘’«»()-—')
        if clean_word and len(clean_word.split()) <= 6:
            word_lower = clean_word.lower()
            if word_lower not in history_set and word_lower not in session_words:
                books_dict[book_title].append(clean_word)
                session_words.add(word_lower)
    return books_dict


def create_csv(data_list, output_path):
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
