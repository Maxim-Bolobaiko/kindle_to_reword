# 1. Берем образ Python
FROM python:3.10-slim

# 2. Отключаем буферизацию
ENV PYTHONUNBUFFERED=1

# 3. Устанавливаем системные зависимости
# ВАЖНО: Добавляем установку nodejs для работы библиотеки translators (Reverso)
RUN apt-get update && \
    apt-get install -y nodejs && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# 4. Рабочая папка
WORKDIR /app

# 5. Зависимости Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 6. Копируем код
COPY . .

# 7. Запуск
CMD ["python", "bot.py"]