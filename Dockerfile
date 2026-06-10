# Используем официальный образ Playwright с установленными браузерами и зависимостями Ubuntu
FROM mcr.microsoft.com/playwright/python:v1.41.0-jammy

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем зависимости и устанавливаем их
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем сам скрипт
COPY scraper.py .

# Запуск скрипта
CMD ["python", "scraper.py"]
