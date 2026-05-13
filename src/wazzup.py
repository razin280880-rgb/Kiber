"""Wazzup24 API — отправка сообщений родителю в WhatsApp.

Адаптация клиента из progress-report-bot. Для MVP отправляем только текст
(видео-ссылка/PDF — внутри текста, файлы напрямую через Wazzup24 v3
требуют публичного URL, что нормально только после деплоя на trial.kiberone.ru).

Если переменные WAZZUP_API_KEY / WAZZUP_CHANNEL_ID не заданы — клиент
переходит в режим dry-run и пишет сообщения в логи, не отправляя.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import requests


logger = logging.getLogger(__name__)


class WazzupClient:
    BASE_URL = "https://api.wazzup24.com/v3"

    def __init__(self, api_key: Optional[str] = None, channel_id: Optional[str] = None):
        self.api_key = api_key or os.getenv("WAZZUP_API_KEY")
        self.channel_id = channel_id or os.getenv("WAZZUP_CHANNEL_ID")
        self.dry_run = not (self.api_key and self.channel_id)
        if self.dry_run:
            logger.warning(
                "WazzupClient в dry-run — не задан WAZZUP_API_KEY / WAZZUP_CHANNEL_ID."
            )

    @staticmethod
    def normalize_phone(phone: str) -> str:
        """Приводит телефон к формату 79XXXXXXXXX (без + и других символов)."""
        digits = "".join(c for c in phone if c.isdigit())
        if digits.startswith("8") and len(digits) == 11:
            digits = "7" + digits[1:]
        if not digits.startswith("7"):
            digits = "7" + digits
        return digits

    def send_text(self, phone: str, text: str) -> dict:
        """Отправляет текстовое сообщение в WhatsApp. В dry-run возвращает фейковый ответ."""
        phone_norm = self.normalize_phone(phone)
        if self.dry_run:
            logger.info("[DRY-RUN Wazzup] to %s\n%s", phone_norm, text)
            return {"status": "dry_run", "phone": phone_norm}

        url = f"{self.BASE_URL}/message"
        payload = {
            "channelId": self.channel_id,
            "chatId": phone_norm,
            "chatType": "whatsapp",
            "text": text,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        resp = requests.post(url, headers=headers, json=payload, timeout=15)
        resp.raise_for_status()
        return resp.json()
