import logging
import os
import time

import telebot

import core
import database
from config import TELEGRAM_BOT_TOKEN, TEMP_DIR

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Initialize Bot
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
translator = core.SmartTranslator()


@bot.message_handler(commands=["start"])
def send_welcome(message):
    """Handles the /start command."""
    bot.reply_to(
        message,
        "👋 Hello! Send me your 'My Clippings.txt' file, and I will convert it to CSV for ReWord.",
    )


@bot.message_handler(content_types=["document"])
def handle_docs(message):
    """Main logic: handles file uploads."""
    try:
        user_id = message.from_user.id
        file_info = message.document
        file_name = file_info.file_name

        # 1. Check file extension
        if not file_name.endswith(".txt"):
            bot.reply_to(message, "⚠️ Please send a .txt file (My Clippings.txt).")
            return

        status_msg = bot.reply_to(message, "⏳ File received. Analyzing...")

        # 2. Download file
        file_path_tg = bot.get_file(file_info.file_id).file_path
        downloaded_file = bot.download_file(file_path_tg)

        # 3. Decode content (handle different encodings)
        content = None
        for enc in ["utf-8-sig", "utf-8", "cp1251"]:
            try:
                content = downloaded_file.decode(enc)
                break
            except UnicodeDecodeError:
                continue

        if not content:
            bot.edit_message_text(
                "❌ Error: Could not decode file. Unknown encoding.",
                chat_id=user_id,
                message_id=status_msg.message_id,
            )
            return

        # 4. Get user history
        history_set = database.get_user_history(user_id)

        # 5. Parse content
        books_data = core.parse_clippings_content(content, history_set)

        if not books_data:
            bot.edit_message_text(
                "ℹ️ No new words found.",
                chat_id=user_id,
                message_id=status_msg.message_id,
            )
            return

        total_words = sum(len(v) for v in books_data.values())
        bot.edit_message_text(
            f"🔎 Found {total_words} new words/phrases. Starting translation...",
            chat_id=user_id,
            message_id=status_msg.message_id,
        )

        # 6. Process each book
        all_new_words = []

        for book_title, words in books_data.items():
            book_results = []

            # Send progress message
            prog_msg = bot.send_message(
                user_id, f"📖 Processing: {book_title} ({len(words)} words)"
            )

            for word in words:
                # Anti-spam delay
                time.sleep(1.5)

                info = translator.fetch_word_data(word)
                if info:
                    book_results.append(info)
                    all_new_words.append(word)

            if book_results:
                # Create CSV
                safe_name = core.sanitize_filename(book_title)
                current_date = time.strftime("%d.%m.%Y")
                csv_filename = f"{safe_name}_{current_date}.csv"
                csv_path = os.path.join(TEMP_DIR, csv_filename)

                if core.create_csv(book_results, csv_path):
                    with open(csv_path, "rb") as f:
                        bot.send_document(
                            user_id,
                            f,
                            caption=f"📕 {book_title}\n✅ Words: {len(book_results)}",
                        )
                    # Cleanup temp file
                    os.remove(csv_path)

            # Clean up progress message
            try:
                bot.delete_message(user_id, prog_msg.message_id)
            except Exception:
                pass

        # 7. Update Database
        if all_new_words:
            database.add_words_to_history(user_id, all_new_words)
            bot.send_message(
                user_id,
                "✅ All words added to your history. They will be skipped next time.",
            )

        # Cleanup status message
        try:
            bot.delete_message(user_id, status_msg.message_id)
        except Exception:
            pass

        bot.send_message(
            user_id,
            "✅ When you have new words, just send me the Clippings.txt file again!",
        )

    except Exception as e:
        logger.error(
            f"Error processing user {message.from_user.id}: {e}", exc_info=True
        )
        bot.reply_to(message, "❌ An internal error occurred. Please try again later.")


if __name__ == "__main__":
    logger.info("Bot started...")
    bot.infinity_polling()
