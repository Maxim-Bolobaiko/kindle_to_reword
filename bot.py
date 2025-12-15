import asyncio
import logging
import os

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import FSInputFile

import core
import database
from config import TELEGRAM_BOT_TOKEN, TEMP_DIR

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher()
translator = core.SmartTranslator()


@dp.message(Command("start"))
async def send_welcome(message: types.Message):
    await message.answer(
        "👋 Привет! Пришли мне файл 'My Clippings.txt', и я сделаю CSV для ReWord."
    )


@dp.message(F.document)
async def handle_docs(message: types.Message):
    try:
        user_id = message.from_user.id
        file_name = message.document.file_name

        if not file_name.endswith(".txt"):
            await message.reply("⚠️ Пожалуйста, пришли файл .txt (My Clippings.txt).")
            return

        status_msg = await message.reply("⏳ Файл принят. Анализирую...")

        file_id = message.document.file_id
        file = await bot.get_file(file_id)
        file_path_on_server = file.file_path

        downloaded_file = await bot.download_file(file_path_on_server)
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
                "❌ Неверная кодировка файла.",
                chat_id=user_id,
                message_id=status_msg.message_id,
            )
            return

        history_set = database.get_user_history(user_id)
        books_data = core.parse_clippings_content(content, history_set)

        if not books_data:
            await bot.edit_message_text(
                "ℹ️ Новых слов не найдено.",
                chat_id=user_id,
                message_id=status_msg.message_id,
            )
            return

        total_words = sum(len(v) for v in books_data.values())
        await bot.edit_message_text(
            f"🔎 Найдено {total_words} новых слов. Перевожу...",
            chat_id=user_id,
            message_id=status_msg.message_id,
        )

        all_new_words = []

        for book_title, words in books_data.items():
            book_results = []
            prog_msg = await message.answer(f"📖 {book_title} ({len(words)} слов)")

            for word in words:
                # Яндекс работает быстро, большая пауза не нужна
                await asyncio.sleep(0.1)

                info = translator.fetch_word_data(word)
                if info:
                    book_results.append(info)
                    all_new_words.append(word)

            if book_results:
                safe_name = core.sanitize_filename(book_title)
                os.makedirs(TEMP_DIR, exist_ok=True)
                csv_path = os.path.join(TEMP_DIR, f"{safe_name}.csv")

                if core.create_csv(book_results, csv_path):
                    doc_file = FSInputFile(csv_path)
                    await bot.send_document(
                        user_id,
                        doc_file,
                        caption=f"📕 {book_title}\n✅ Добавлено слов: {len(book_results)}",
                    )
                    os.remove(csv_path)

            try:
                await bot.delete_message(user_id, prog_msg.message_id)
            except:
                pass

        if all_new_words:
            database.add_words_to_history(user_id, all_new_words)
            await message.answer("✅ Слова добавлены в историю.")

        try:
            await bot.delete_message(user_id, status_msg.message_id)
        except:
            pass

    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        await message.reply("❌ Произошла ошибка.")


async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
