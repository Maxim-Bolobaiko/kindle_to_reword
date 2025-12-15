import asyncio
import logging
import os
import random

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import FSInputFile

import core
import database
from config import TELEGRAM_BOT_TOKEN, TEMP_DIR

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Initialize Bot (Aiogram 3.x)
bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher()
translator = core.SmartTranslator()


@dp.message(Command("start"))
async def send_welcome(message: types.Message):
    """Handles /start command."""
    await message.answer(
        "👋 Hello! Send me your 'My Clippings.txt' file, and I will convert it to CSV for ReWord."
    )


@dp.message(F.document)
async def handle_docs(message: types.Message):
    """Main handler for file uploads."""
    try:
        user_id = message.from_user.id
        file_name = message.document.file_name

        # 1. Validate file extension
        if not file_name.endswith(".txt"):
            await message.reply("⚠️ Please send a .txt file (My Clippings.txt).")
            return

        status_msg = await message.reply("⏳ File received. Analyzing...")

        # 2. Download file
        file_id = message.document.file_id
        file = await bot.get_file(file_id)
        file_path_on_server = file.file_path

        # Download into memory
        downloaded_file = await bot.download_file(file_path_on_server)
        file_bytes = downloaded_file.read()

        # 3. Decode content (try different encodings)
        content = None
        for enc in ["utf-8-sig", "utf-8", "cp1251"]:
            try:
                content = file_bytes.decode(enc)
                break
            except UnicodeDecodeError:
                continue

        if not content:
            await bot.edit_message_text(
                "❌ Error: Could not decode file. Unknown encoding.",
                chat_id=user_id,
                message_id=status_msg.message_id,
            )
            return

        # 4. Fetch user history (to skip duplicates)
        history_set = database.get_user_history(user_id)

        # 5. Parse words
        books_data = core.parse_clippings_content(content, history_set)

        if not books_data:
            await bot.edit_message_text(
                "ℹ️ No new words found.",
                chat_id=user_id,
                message_id=status_msg.message_id,
            )
            return

        total_words = sum(len(v) for v in books_data.values())
        await bot.edit_message_text(
            f"🔎 Found {total_words} new words. Starting translation...",
            chat_id=user_id,
            message_id=status_msg.message_id,
        )

        # 6. Process each book
        all_new_words = []

        for book_title, words in books_data.items():
            book_results = []

            # Progress message
            prog_msg = await message.answer(
                f"📖 Processing: {book_title} ({len(words)} words)"
            )

            for word in words:
                # PAUSE to prevent banning (1.0 - 1.5 sec)
                await asyncio.sleep(random.uniform(1.0, 1.5))

                # Fetch translation
                info = translator.fetch_word_data(word)
                if info:
                    book_results.append(info)
                    all_new_words.append(word)

            if book_results:
                # Generate CSV
                safe_name = core.sanitize_filename(book_title)
                os.makedirs(TEMP_DIR, exist_ok=True)

                csv_filename = f"{safe_name}.csv"
                csv_path = os.path.join(TEMP_DIR, csv_filename)

                if core.create_csv(book_results, csv_path):
                    # Send file
                    doc_file = FSInputFile(csv_path)
                    await bot.send_document(
                        user_id,
                        doc_file,
                        caption=f"📕 {book_title}\n✅ Words: {len(book_results)}",
                    )
                    # Cleanup temp file
                    os.remove(csv_path)

            # Delete progress message
            try:
                await bot.delete_message(user_id, prog_msg.message_id)
            except Exception:
                pass

        # 7. Update Database
        if all_new_words:
            database.add_words_to_history(user_id, all_new_words)
            await message.answer(
                "✅ All words added to history. They will be skipped next time."
            )

        # Delete status message
        try:
            await bot.delete_message(user_id, status_msg.message_id)
        except Exception:
            pass

    except Exception as e:
        logger.error(
            f"Error processing user {message.from_user.id}: {e}", exc_info=True
        )
        await message.reply("❌ Internal error. Please try again later.")


# Main Entry Point
async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    logger.info("Bot started via Aiogram (Simple Mode)...")
    asyncio.run(main())
