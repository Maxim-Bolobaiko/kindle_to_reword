import asyncio
import html
import logging
import os
from datetime import datetime, timedelta, timezone

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    BotCommand,
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

import core
import database
from config import TELEGRAM_BOT_TOKEN, TEMP_DIR

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Initialize Bot
bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher()
translator = core.SmartTranslator()

# --- Setup Interface ---


async def setup_bot_interface(bot: Bot):
    main_menu_commands = [
        BotCommand(command="/start", description="Restart & Welcome"),
        BotCommand(command="/help", description="How to find the file?"),
    ]
    await bot.set_my_commands(main_menu_commands)

    await bot.set_my_short_description(
        "📚 Turn your Kindle highlights into flashcards for ReWord.\n\n"
        "Send me your 'My Clippings.txt' file! 📤"
    )

    await bot.set_my_description(
        "I am your Kindle Vocabulary Assistant. 🤖\n\n"
        "1. Send me your 'My Clippings.txt' file.\n"
        "2. I will extract new words.\n"
        "3. I will translate them using Yandex Dictionary & Cloud API.\n"
        "4. You get a CSV file ready for ReWord app."
    )


# --- Handlers ---


@dp.message(CommandStart())
async def send_welcome(message: types.Message):
    user_name = html.escape(message.from_user.first_name)
    kb = [
        [
            InlineKeyboardButton(
                text="❓ Where do I find the file?", callback_data="show_help"
            )
        ]
    ]
    keyboard = InlineKeyboardMarkup(inline_keyboard=kb)

    welcome_text = (
        f"👋 <b>Hello, {user_name}!</b>\n\n"
        f"I am your <b>Kindle Vocabulary Assistant</b>. 🤖\n"
        f"I can turn your Kindle highlights into flashcards for <b>ReWord</b>.\n\n"
        f"📂 <b>To start:</b>\n"
        f"Simply drag and drop your <code>My Clippings.txt</code> file here."
    )
    await message.answer(welcome_text, parse_mode="HTML", reply_markup=keyboard)


@dp.message(Command("help"))
async def send_help_command(message: types.Message):
    await show_help_text(message)


@dp.callback_query(F.data == "show_help")
async def send_help_callback(callback: CallbackQuery):
    await show_help_text(callback.message)
    await callback.answer()


async def show_help_text(message: types.Message):
    help_text = (
        "📖 <b>How to find your file:</b>\n\n"
        "1. Connect your Kindle to your computer via USB 🔌.\n"
        "2. Open the Kindle drive.\n"
        "3. Go to the <code>documents</code> folder.\n"
        "4. Look for a file named <code>My Clippings.txt</code>.\n"
        "5. Drag and drop that file right here! 📤"
    )
    await message.answer(help_text, parse_mode="HTML")


@dp.message(F.document)
async def handle_docs(message: types.Message):
    try:
        user_id = message.from_user.id
        file_name = message.document.file_name
        file_size = message.document.file_size

        # 1. Validate Extension
        if not file_name.endswith(".txt"):
            await message.reply(
                "⚠️ Please send a <b>.txt</b> file (specifically <code>My Clippings.txt</code>).",
                parse_mode="HTML",
            )
            return

        # 2. Validate Size (Limit to 20MB)
        if file_size > 20 * 1024 * 1024:
            await message.reply(
                "⚠️ <b>File is too large.</b> Please send a file smaller than 20MB.",
                parse_mode="HTML",
            )
            return

        # 3. Validate Empty File
        if file_size == 0:
            await message.reply(
                "⚠️ <b>File is empty.</b> Please check your file.", parse_mode="HTML"
            )
            return

        status_msg = await message.reply(
            "⏳ File received. <b>Analyzing...</b>", parse_mode="HTML"
        )

        # 4. Download & Decode
        file_id = message.document.file_id
        file = await bot.get_file(file_id)
        downloaded_file = await bot.download_file(file.file_path)
        file_bytes = downloaded_file.read()

        content = None
        for enc in ["utf-8-sig", "utf-8", "cp1251"]:
            try:
                content = file_bytes.decode(enc)
                break
            except UnicodeDecodeError:
                continue

        if not content:
            await bot.edit_message_text(
                "❌ <b>Error:</b> Unknown encoding.",
                chat_id=user_id,
                message_id=status_msg.message_id,
                parse_mode="HTML",
            )
            return

        # 5. Parse
        history_set = database.get_user_history(user_id)
        books_data = core.parse_clippings_content(content, history_set)

        # EDGE CASE: Invalid format (no separators)
        if books_data is None:
            await bot.edit_message_text(
                "⚠️ <b>Invalid file format.</b>\n\n"
                "This doesn't look like a Kindle clippings file.\n"
                "Please check that the file contains the <code>==========</code> separators.",
                chat_id=user_id,
                message_id=status_msg.message_id,
                parse_mode="HTML",
            )
            return

        # EDGE CASE: No new words
        if not books_data:
            await bot.edit_message_text(
                "ℹ️ <b>No new words found.</b>\nIt seems all words are already in your history! ✅",
                chat_id=user_id,
                message_id=status_msg.message_id,
                parse_mode="HTML",
            )
            return

        total_words = sum(len(v) for v in books_data.values())
        await bot.edit_message_text(
            f"🔎 Found <b>{total_words}</b> new words. <b>Translating...</b> 🚀",
            chat_id=user_id,
            message_id=status_msg.message_id,
            parse_mode="HTML",
        )

        # 6. Process Books
        all_new_words = []
        for book_title, words in books_data.items():
            book_results = []
            safe_title = html.escape(book_title)
            prog_msg = await message.answer(
                f"📖 Processing: <b>{safe_title}</b> ({len(words)} words)...",
                parse_mode="HTML",
            )

            for word in words:
                info = translator.fetch_word_data(word)
                if info:
                    book_results.append(info)
                    all_new_words.append(word)

            if book_results:
                safe_name = core.sanitize_filename(book_title)

                local_now = datetime.now()
                utc_now_naive = datetime.now(timezone.utc).replace(tzinfo=None)

                diff_seconds = abs((local_now - utc_now_naive).total_seconds())
                if diff_seconds < 300:
                    final_time = local_now + timedelta(hours=3)
                else:
                    final_time = local_now

                timestamp = final_time.strftime("%d-%m-%y__%H-%M")

                csv_filename = f"{safe_name}_{timestamp}"

                os.makedirs(TEMP_DIR, exist_ok=True)
                csv_path = os.path.join(TEMP_DIR, f"{csv_filename}.csv")

                if core.create_csv(book_results, csv_path):
                    doc_file = FSInputFile(csv_path)
                    try:
                        await bot.send_document(
                            user_id,
                            doc_file,
                            caption=f"📕 <b>{safe_title}</b>\n✅ Words added: <b>{len(book_results)}</b>",
                            parse_mode="HTML",
                        )
                    except Exception as e:
                        logger.error(f"Failed to send document: {e}")
                    finally:
                        if os.path.exists(csv_path):
                            os.remove(csv_path)

            try:
                await bot.delete_message(user_id, prog_msg.message_id)
            except:
                pass

        if all_new_words:
            database.add_words_to_history(user_id, all_new_words)
            await message.answer(
                "✅ <b>Done!</b> All words saved to history.", parse_mode="HTML"
            )

        try:
            await bot.delete_message(user_id, status_msg.message_id)
        except:
            pass

    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        await message.reply(
            "❌ <b>Internal error.</b> Please try again later.", parse_mode="HTML"
        )


async def main():
    await setup_bot_interface(bot)
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Bot started! 🚀")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
