# Kindle Word-to-Dictionary Converter (AI Powered)

A Telegram bot that converts your Kindle vocabulary clippings into a clean, ready-to-import CSV format for learning apps like ReWord.

**Current Version:** v2.0 (AI-Core)

## 🚀 Key Features

* **AI-Powered Lemmatization (YandexGPT):** 
    * Intelligently converts words to their base forms (e.g., *went* -> *go*, *mice* -> *mouse*, *biggest* -> *big*).
    * Handles complex spelling rules (e.g., *hopping* -> *hop* vs *hoped* -> *hope*).
    * Context-aware (distinguishes between nouns and verbs where possible).
* **Idioms & Phrasal Verbs Support:** 
    * Recognizes and preserves multi-word expressions like *"give up"*, *"piece of cake"*, or *"out of the blue"*.
* **Hybrid Architecture:** 
    * Uses **LLM** (YandexGPT) for linguistic analysis and initial translation.
    * Uses **Dictionary API** (Yandex Dictionary) for phonetic transcriptions, synonyms, and usage examples.
* **Smart Parsing:** 
    * Processes raw *"My Clippings.txt"* files from Kindle.
    * Filters duplicates and separates words by book title.

## 🛠 Tech Stack

* **Python 3.x**
* **aiogram 3.x** (Telegram Bot API)
* **Yandex Cloud Foundation Models** (YandexGPT Pro/Lite)
* **Yandex Dictionary API**

## ⚙️ Configuration

The project requires access to Yandex Cloud services. Ensure your `config.py` or environment variables are set up with:

* `BOT_TOKEN`: Your Telegram Bot API token.
* `YANDEX_CLOUD_KEY`: API Key for Yandex Cloud (Service Account).
* `YANDEX_FOLDER_ID`: Folder ID where the Service Account has `ai.languageModels.user` role.
* `YANDEX_DICT_KEY`: API Key for Yandex Dictionary.

## 🧠 Logic Pipeline

1.  **Input:** User sends a word or phrase (e.g., *"better"*).
2.  **AI Analysis:** System asks YandexGPT for the lemma and translation -> Returns *"good"* (lemma) & *"хороший"* (translation).
3.  **Enrichment:** System queries Yandex Dictionary for *"good"* to fetch transcription `[ɡʊd]` and additional synonyms.
4.  **Output:** A structured CSV entry ready for memorization.

## 📝 Usage

1.  Start the bot via Telegram.
2.  Send a single word/phrase to test the translation.
3.  Upload your `My Clippings.txt` file to process bulk vocabulary.
4.  Receive a processed `.csv` file.

---
*Disclaimer: This project uses 3rd party APIs which may incur costs, though they are minimal for personal use.*