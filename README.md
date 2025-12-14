# Kindle2ReWord Bot 📚🤖

A smart Telegram bot that automates the workflow between **Amazon Kindle** highlights and the **ReWord** app. It processes your clippings, intelligently translates them, and prevents duplicates.

## ✨ Features

* **Smart Hybrid Translation:**
    * **1-2 words:** Uses **Reverso Context** to provide synonyms and usage examples (ideal for learning deep context).
    * **3+ words:** Uses **Google Translate** for accurate full-sentence translation (ideal for phrases/sentences).
* **Duplicate Prevention:** Uses a persistent **SQLite database** to track user history. It ignores words you have already processed in previous uploads.
* **Kindle Parser:** Extracts clean words/sentences from the raw `My Clippings.txt` file.
* **Instant Export:** Generates a ready-to-import CSV file for ReWord directly in the Telegram chat.
* **Secure:** Configuration is separated from code using Environment Variables.

## 🛠 Installation

### 1. Clone the repository
```bash
git clone https://github.com/Maxim-Bolobaiko/kindle_to_reword
cd kindle_bot
```

### 2. Install dependencies

Ensure you have **Python 3.9+** installed.
```Bash
pip install -r requirements.txt
```
### 3. Configuration

1. Create a `.env` file in the root directory (use `.env.example` as a template).
2. Fill in your details:

```ini
BOT_TOKEN=your_telegram_bot_token
ADMIN_ID=your_telegram_user_id
AUTO_CONFIRM=True
```
## ▶️ Usage

Run the bot:
```Bash
python bot.py
```
1. Open your bot in Telegram and send `/start`.
2. Connect your Kindle via USB and locate `documents/My Clippings.txt`.
3. Drag and drop the `.txt` file into the Telegram chat.
4. Receive your CSV file and import it into ReWord!

## 📂 Project Structure

* `bot.py` - Main entry point (Telegram listener).
* `core.py` - "Brain" of the bot: parsing logic and translation router.
* `database.py` - SQLite management for user history.
* `config.py` - Environment configuration loader.

## 📄 License

MIT