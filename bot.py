import asyncio
import logging
import os

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import FSInputFile

import core
import database
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TEMP_DIR

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Initialize Bot and Dispatcher (Aiogram 3.x)
bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher()
translator = core.SmartTranslator()


@dp.message(Command("start"))
async def send_welcome(message: types.Message):
    """Handles the /start command."""
    await message.reply(
        "👋 Hello! Send me your 'My Clippings.txt' file, and I will convert it to CSV for ReWord."
    )


@dp.message(F.document)
async def handle_docs(message: types.Message):
    """Main logic: handles file uploads."""
    try:
        user_id = message.from_user.id
        file_name = message.document.file_name

        # 1. Check file extension
        if not file_name.endswith(".txt"):
            await message.reply("⚠️ Please send a .txt file (My Clippings.txt).")
            return

        status_msg = await message.reply("⏳ File received. Analyzing...")

        # 2. Download file
        file_id = message.document.file_id
        file = await bot.get_file(file_id)
        file_path_on_server = file.file_path

        # Download content to memory buffer
        downloaded_file = await bot.download_file(file_path_on_server)
        file_bytes = downloaded_file.read()

        # 3. Decode content
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

        # 4. Get user history
        history_set = database.get_user_history(user_id)

        # 5. Parse content
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
            f"🔎 Found {total_words} new words/phrases. Starting translation...",
            chat_id=user_id,
            message_id=status_msg.message_id,
        )

        # 6. Process each book
        all_new_words = []

        for book_title, words in books_data.items():
            book_results = []

            # Send progress message
            prog_msg = await bot.send_message(
                user_id, f"📖 Processing: {book_title} ({len(words)} words)"
            )

            for word in words:
                # Small delay to be polite to APIs
                await asyncio.sleep(1.0)

                # Note: core.fetch_word_data is synchronous, but for this load it's acceptable.
                # In high-load production, this should run in an executor.
                info = translator.fetch_word_data(word)
                if info:
                    book_results.append(info)
                    all_new_words.append(word)

            if book_results:
                # Create CSV
                safe_name = core.sanitize_filename(book_title)
                # Ensure temp directory exists (double check)
                os.makedirs(TEMP_DIR, exist_ok=True)

                csv_filename = f"{safe_name}.csv"
                csv_path = os.path.join(TEMP_DIR, csv_filename)

                if core.create_csv(book_results, csv_path):
                    # Send document using FSInputFile
                    doc_file = FSInputFile(csv_path)
                    await bot.send_document(
                        user_id,
                        doc_file,
                        caption=f"📕 {book_title}\n✅ Words: {len(book_results)}",
                    )
                    # Cleanup temp file
                    os.remove(csv_path)

            # Clean up progress message
            try:
                await bot.delete_message(user_id, prog_msg.message_id)
            except Exception:
                pass

        # 7. Update Database
        if all_new_words:
            database.add_words_to_history(user_id, all_new_words)
            await bot.send_message(
                user_id,
                "✅ All words added to your history. They will be skipped next time.",
            )

        # Cleanup status message
        try:
            await bot.delete_message(user_id, status_msg.message_id)
        except Exception:
            pass

    except Exception as e:
        logger.error(
            f"Error processing user {message.from_user.id}: {e}", exc_info=True
        )
        await message.reply("❌ An internal error occurred. Please try again later.")


async def main():
    # Remove webhook if it exists (useful for local dev)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    logger.info("Bot started via Aiogram...")
    asyncio.run(main())
