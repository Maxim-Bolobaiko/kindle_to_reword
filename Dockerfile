# 1. Use lightweight Python image
FROM python:3.10-slim

# 2. Disable buffering for logs
ENV PYTHONUNBUFFERED=1

# 3. Create working directory
WORKDIR /app

# 4. Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. Copy project files
COPY . .

# 6. Run the bot
CMD ["python", "bot.py"]