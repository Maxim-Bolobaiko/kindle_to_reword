import csv
import logging
import re
import unicodedata
from collections import defaultdict

import requests
import translators as ts
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import YANDEX_API_KEY

logger = logging.getLogger(__name__)


# --- Networking Setup ---
def create_retry_session():
    """Создает сессию с защитой от сбоев сети."""
    session = requests.Session()
    retries = Retry(
        total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504]
    )
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("https://", adapter)
    return session


NET_SESSION = create_retry_session()


class SmartTranslator:
    def _translate_google(self, word_clean):
        """ПЛАН Б: Google Translate (Простой текст)."""
        try:
            translation = ts.translate_text(
                word_clean,
                translator="google",
                from_language="en",
                to_language="ru",
                is_detail_result=False,
            )
            return {
                "word": word_clean,
                "translation": translation,
                "transcription": "",
                "example_en": "",
                "example_ru": "",
            }
        except Exception as e:
            logger.error(f"Google fallback failed for '{word_clean}': {e}")
            return None

    def _translate_yandex(self, word_clean):
        """ПЛАН А: Яндекс Словарь (Собираем значения со всех частей речи)."""
        url = "https://dictionary.yandex.net/api/v1/dicservice.json/lookup"
        params = {
            "key": YANDEX_API_KEY,
            "lang": "en-ru",
            "text": word_clean,
            "ui": "ru",
        }

        try:
            resp = NET_SESSION.get(url, params=params, timeout=5)
            if resp.status_code != 200:
                logger.warning(f"Yandex API error {resp.status_code}")
                return None

            data = resp.json()
            definitions = data.get("def")

            # Если словарь пуст
            if not definitions:
                return None

            # 1. Транскрипция (берем из первого блока, она обычно общая)
            first_def = definitions[0]
            transcription = f"[{first_def.get('ts')}]" if first_def.get("ts") else ""

            # 2. СБОР ПЕРЕВОДОВ (AGREGATION)
            collected_words = []

            # Проходим по всем частям речи (Сущ, Глагол, Прил...)
            for i, definition in enumerate(definitions):
                translations = definition.get("tr", [])
                if not translations:
                    continue

                # Берем самый главный перевод в этой группе
                top_tr = translations[0]
                collected_words.append(top_tr["text"])

                # Если это САМАЯ ПЕРВАЯ группа (наиболее частотное значение),
                # берем оттуда еще пару синонимов для точности.
                if i == 0:
                    syns = [s["text"] for s in top_tr.get("syn", [])][:3]
                    collected_words.extend(syns)

            # Удаляем дубликаты, сохраняя порядок (на всякий случай)
            unique_words = list(dict.fromkeys(collected_words))
            full_translation = ", ".join(unique_words)

            # 3. Примеры (ищем первый попавшийся пример)
            ex_en = ""
            ex_ru = ""

            # Пробегаемся и ищем первый хороший пример
            for definition in definitions:
                for tr in definition.get("tr", []):
                    if tr.get("ex"):
                        first_ex = tr["ex"][0]
                        ex_en = first_ex.get("text")
                        if first_ex.get("tr"):
                            ex_ru = first_ex["tr"][0].get("text")
                        break  # Нашли пример - выходим из цикла tr
                if ex_en:
                    break  # Нашли пример - выходим из цикла definitions

            return {
                "word": word_clean,
                "translation": full_translation,
                "transcription": transcription,
                "example_en": ex_en,
                "example_ru": ex_ru,
            }

        except Exception as e:
            logger.error(f"Yandex request failed: {e}")
            return None

    def fetch_word_data(self, word):
        word_clean = word.strip()

        # Шаг 1: Пробуем Яндекс
        yandex_result = self._translate_yandex(word_clean)
        if yandex_result:
            return yandex_result

        # Шаг 2: Если Яндекс пуст, зовем Гугл
        return self._translate_google(word_clean)


# --- Парсинг и CSV ---


def sanitize_filename(name):
    name = unicodedata.normalize("NFKC", name)
    clean = re.sub(r"[^\w\s\(\)\-а-яА-Я]", "", name)
    return clean.strip()[:50]


def parse_clippings_content(content, history_set):
    raw_clips = content.split("==========")
    books_dict = defaultdict(list)
    session_words = set()

    for clip in reversed(raw_clips):
        lines = [line.strip() for line in clip.split("\n") if line.strip()]
        if len(lines) < 2:
            continue

        book_title = lines[0]
        clean_word = lines[-1].strip(' .,?!:;"“”‘’«»()')

        if clean_word and len(clean_word.split()) <= 5:
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
            writer.writerow(
                ["Word", "Transcription", "Translation", "Example", "Ex.Translation"]
            )

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
