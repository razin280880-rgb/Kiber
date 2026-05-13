# Python 3.12 slim — лёгкий образ под Flask + waitress + Anthropic SDK.
# Если в проекте появится что-то нативное (Playwright, Pillow с системными
# зависимостями) — переходи на python:3.12 (не slim).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Зависимости — отдельным слоем, чтобы pip install кешировался при изменении кода
COPY requirements.txt ./
RUN pip install -r requirements.txt

# Код приложения
COPY src/ ./src/
COPY templates/ ./templates/
COPY static/ ./static/

# Data-папки создаём пустыми — реально мапятся томами из docker-compose
RUN mkdir -p /app/games /app/sessions /app/videos /app/photos /app/passports

EXPOSE 8000

# Web-сервер: waitress (production-ready WSGI). Worker запускается отдельным сервисом.
CMD ["python", "-m", "waitress", "--host=0.0.0.0", "--port=8000", "--threads=8", "src.app:app"]
