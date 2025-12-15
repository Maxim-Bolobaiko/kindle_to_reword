# 📚 Kindle2ReWord Bot

A Telegram bot that converts your Kindle highlights (`My Clippings.txt`) into ready-to-use CSV flashcards for the **ReWord** app.

The bot automatically translates words, finds transcriptions, examples, and synonyms using a hybrid approach (Yandex Dictionary + Yandex Cloud API).

## ✨ Features

* **📄 Automated Parsing:** Accepts `My Clippings.txt` and extracts words grouped by book.
* **🧠 Hybrid Translation:**
    * **Yandex Dictionary API:** Provides transcriptions `[ts]`, synonyms, and dictionary definitions.
    * **Yandex Cloud API:** Handles idioms, phrases, and words missing from the dictionary (AI-powered translation).
* **💾 History Tracking:** Remembers words you've already learned to prevent duplicates.
* **⚡ Smart Limits:** Filters out long sentences (max 6 words) to focus on vocabulary.
* **🛠 ReWord Ready:** Generates `.csv` files strictly formatted for import into ReWord.

## 🚀 Tech Stack

* **Python 3.10+**
* **Aiogram 3.x** (Telegram Bot Framework)
* **Requests** (API calls)
* **SQLite** (User history storage)
* **Docker** (Containerization)

## 🛠 Installation & Setup

### 1. Clone the repository
```bash
git clone https://github.com/Maxim-Bolobaiko/kindle_to_reword
cd kindle-bot
```
### 2. Configure Environment Variables

Create a `.env` file in the root directory:
```ini
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
YANDEX_DICT_KEY=your_yandex_dictionary_key
YANDEX_CLOUD_KEY=your_yandex_cloud_api_key
```
* **`TELEGRAM_BOT_TOKEN`**: Get from [@BotFather](https://t.me/BotFather).
* **`YANDEX_DICT_KEY`**: Get a free key at [Yandex Dictionary API](https://yandex.ru/dev/dictionary/).
* **`YANDEX_CLOUD_KEY`**: Create a Service Account in [Yandex Cloud](https://cloud.yandex.ru/) with the `ai.translate.user` role.

### 3. Run with Docker (Recommended)
```Bash
# Build the image
docker build -t kindle-bot .
# Run the container
docker run -d --env-file .env --name kindle-bot-container kindle-bot
```

### 4. Run Locally (Manual)
```Bash
# Install dependencies
pip install -r requirements.txt
# Run the bot
python bot.py
```
## 📱 How to Use

1. Connect your Kindle to PC via USB.
2. Locate `documents/My Clippings.txt`.
3. Send the file to the bot.
4. Download the returned `.csv` files.
5. Open **ReWord**, go to categories, and import the CSV.

## 📜 License

MIT
