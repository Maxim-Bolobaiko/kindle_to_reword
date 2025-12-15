import asyncio
import html
import logging
import os

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
    """
    Sets up the menu commands and the 'Short Description'
    (the text visible before clicking Start).
    """
    # 1. Main Menu Commands
    main_menu_commands = [
        BotCommand(command="/start", description="Restart & Welcome"),
        BotCommand(command="/help", description="How to find the file?"),
    ]
    await bot.set_my_commands(main_menu_commands)

    # 2. Short Description (Placeholder text)
    await bot.set_my_short_description(
        "📚 Turn your Kindle highlights into flashcards for ReWord.\n\n"
        "Send me your 'My Clippings.txt' file! 📤"
    )

    # 3. Full Description (Bot Profile)
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
    """Handles /start command."""
    user_name = html.escape(message.from_user.first_name)

    # Inline Keyboard
    kb = [
        [
            InlineKeyboardButton(
                text="❓ Where do I find the file?", callback_data="show_help"
            )
        ]
    ]
    keyboard = InlineKeyboardMarkup(inline_keyboard=kb)

    # Using HTML for formatting
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
    """Handles /help command."""
    await show_help_text(message)


@dp.callback_query(F.data == "show_help")
async def send_help_callback(callback: CallbackQuery):
    """Handles the button click."""
    await show_help_text(callback.message)
    await callback.answer()


async def show_help_text(message: types.Message):
    """Common function to send help instructions."""
    help_text = (
        "📖 <b>How to find your file:</b>\n\n"
        "1. Connect your Kindle to your computer via USB 🔌.\n"
        "2. Open the Kindle drive (like a USB stick).\n"
        "3. Go to the <code>documents</code> folder.\n"
        "4. Look for a file named <code>My Clippings.txt</code>.\n"
        "5. Drag and drop that file right here into this chat! 📤"
    )
    await message.answer(help_text, parse_mode="HTML")


@dp.message(F.document)
async def handle_docs(message: types.Message):
    """Main handler for file uploads."""
    try:
        user_id = message.from_user.id
        file_name = message.document.file_name

        # 1. Validate extension
        if not file_name.endswith(".txt"):
            await message.reply(
                "⚠️ Please send a <b>.txt</b> file (specifically <code>My Clippings.txt</code>).",
                parse_mode="HTML",
            )
            return

        status_msg = await message.reply(
            "⏳ File received. <b>Analyzing...</b>", parse_mode="HTML"
        )

        # 2. Download file
        file_id = message.document.file_id
        file = await bot.get_file(file_id)
        file_path_on_server = file.file_path

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
                "❌ <b>Error:</b> Could not decode file. Unknown encoding.",
                chat_id=user_id,
                message_id=status_msg.message_id,
                parse_mode="HTML",
            )
            return

        # 4. Parse content
        history_set = database.get_user_history(user_id)
        books_data = core.parse_clippings_content(content, history_set)

        if not books_data:
            await bot.edit_message_text(
                "ℹ️ <b>No new words found.</b>\nMaybe you already processed them?",
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

        # 5. Process each book
        all_new_words = []

        for book_title, words in books_data.items():
            book_results = []
            safe_title = html.escape(book_title)

            # Progress message
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
                # Generate CSV
                safe_name = core.sanitize_filename(book_title)
                os.makedirs(TEMP_DIR, exist_ok=True)

                csv_filename = f"{safe_name}.csv"
                csv_path = os.path.join(TEMP_DIR, csv_filename)

                if core.create_csv(book_results, csv_path):
                    doc_file = FSInputFile(csv_path)
                    await bot.send_document(
                        user_id,
                        doc_file,
                        caption=f"📕 <b>{safe_title}</b>\n✅ Words added: <b>{len(book_results)}</b>",
                        parse_mode="HTML",
                    )
                    os.remove(csv_path)

            try:
                await bot.delete_message(user_id, prog_msg.message_id)
            except Exception:
                pass

        # 6. Update History
        if all_new_words:
            database.add_words_to_history(user_id, all_new_words)
            await message.answer(
                "✅ <b>Done!</b> All words saved to history. They will be skipped next time.",
                parse_mode="HTML",
            )

        try:
            await bot.delete_message(user_id, status_msg.message_id)
        except Exception:
            pass

    except Exception as e:
        logger.error(
            f"Error processing user {message.from_user.id}: {e}", exc_info=True
        )
        await message.reply(
            "❌ <b>Internal error.</b> Please try again later.", parse_mode="HTML"
        )


# --- Startup ---


async def main():
    # Setup commands and descriptions
    await setup_bot_interface(bot)

    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Bot started! 🚀")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
