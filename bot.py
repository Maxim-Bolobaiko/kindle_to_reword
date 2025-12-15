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

# Настройка логирования
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Инициализация бота и диспетчера (Aiogram 3.x)
bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher()
translator = core.SmartTranslator()


@dp.message(Command("start"))
async def send_welcome(message: types.Message):
    """Обрабатывает команду /start"""
    await message.answer(
        "👋 Привет! Пришли мне файл 'My Clippings.txt', и я сделаю CSV для ReWord."
    )


@dp.message(F.document)
async def handle_docs(message: types.Message):
    """Основная логика: обработка файлов"""
    try:
        user_id = message.from_user.id
        file_name = message.document.file_name

        # 1. Проверка расширения
        if not file_name.endswith(".txt"):
            await message.reply("⚠️ Пожалуйста, пришли файл .txt (My Clippings.txt).")
            return

        status_msg = await message.reply("⏳ Файл принят. Анализирую...")

        # 2. Скачивание файла (асинхронно)
        file_id = message.document.file_id
        file = await bot.get_file(file_id)
        file_path_on_server = file.file_path

        # Скачиваем в память
        downloaded_file = await bot.download_file(file_path_on_server)
        # Aiogram возвращает BytesIO объект, читаем байты
        file_bytes = downloaded_file.read()

        # 3. Декодирование (подбор кодировки)
        content = None
        for enc in ["utf-8-sig", "utf-8", "cp1251"]:
            try:
                content = file_bytes.decode(enc)
                break
            except UnicodeDecodeError:
                continue

        if not content:
            await bot.edit_message_text(
                "❌ Ошибка: Не удалось прочитать файл. Неизвестная кодировка.",
                chat_id=user_id,
                message_id=status_msg.message_id,
            )
            return

        # 4. Получаем историю
        history_set = database.get_user_history(user_id)

        # 5. Парсим
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
            f"🔎 Найдено {total_words} новых слов/фраз. Начинаю перевод...",
            chat_id=user_id,
            message_id=status_msg.message_id,
        )

        # 6. Обработка по книгам
        all_new_words = []

        for book_title, words in books_data.items():
            book_results = []

            # Сообщение о прогрессе
            prog_msg = await message.answer(
                f"📖 Обрабатываю: {book_title} ({len(words)} слов)"
            )

            for word in words:
                # Небольшая пауза, чтобы быть вежливыми к API
                await asyncio.sleep(random.uniform(1.0, 2.0))

                # Вызываем синхронный переводчик
                # (для высокой нагрузки это стоило бы вынести в executor, но для личного бота ок)
                info = translator.fetch_word_data(word)
                if info:
                    book_results.append(info)
                    all_new_words.append(word)

            if book_results:
                # Создаем CSV
                safe_name = core.sanitize_filename(book_title)
                # Убедимся, что папка есть (хоть мы и фиксили это, но на всякий случай)
                os.makedirs(TEMP_DIR, exist_ok=True)

                csv_filename = f"{safe_name}.csv"
                csv_path = os.path.join(TEMP_DIR, csv_filename)

                if core.create_csv(book_results, csv_path):
                    # Отправка файла через FSInputFile
                    doc_file = FSInputFile(csv_path)
                    await bot.send_document(
                        user_id,
                        doc_file,
                        caption=f"📕 {book_title}\n✅ Слов: {len(book_results)}",
                    )
                    # Чистим файл
                    os.remove(csv_path)

            # Удаляем сообщение о прогрессе
            try:
                await bot.delete_message(user_id, prog_msg.message_id)
            except Exception:
                pass

        # 7. Обновляем БД
        if all_new_words:
            database.add_words_to_history(user_id, all_new_words)
            await message.answer(
                "✅ Все слова добавлены в историю. В следующий раз я их пропущу."
            )

        # Удаляем статусное сообщение
        try:
            await bot.delete_message(user_id, status_msg.message_id)
        except Exception:
            pass

    except Exception as e:
        logger.error(
            f"Error processing user {message.from_user.id}: {e}", exc_info=True
        )
        await message.reply("❌ Произошла внутренняя ошибка. Попробуйте позже.")


# Точка входа для асинхронного приложения
async def main():
    # Удаляем вебхуки, если они вдруг были (полезно при разработке)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    logger.info("Bot started via Aiogram...")
    asyncio.run(main())
