"""Worker: автоматическая отправка родителю после пробного урока.

Два потока:

1) Через 1 час после finish_at — короткое сообщение с ссылкой на видео-нарезку
   (если загружена) и на игру (если есть). Решает VIDEO_DELAY_MINUTES.

2) Через 24 часа после finish_at — генерация персонального отчёта через Claude
   и отправка родителю ссылки /parent/<token>/report. Решает REPORT_DELAY_MINUTES.

Worker идемпотентен: для каждого этапа на сессии есть свой timestamp
(video_sent_at / report_sent_at). Повторный запуск ничего не дублирует.

Запуск:
    .venv\\Scripts\\python.exe -m src.worker            # непрерывный режим
    .venv\\Scripts\\python.exe -m src.worker --once     # один проход и выход
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from datetime import datetime, timedelta
from typing import Optional

from dotenv import load_dotenv

from src import storage
from src.ai_writer import generate_report
from src.checkpoints import CHECKPOINTS_BY_ID
from src.wazzup import WazzupClient


load_dotenv()

# Windows-консоль по умолчанию в cp1251 — насильно переключаемся на UTF-8,
# иначе emoji и кириллица в логах падают с UnicodeEncodeError.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("igrovan.worker")


BASE_URL = os.getenv("BASE_URL", "http://localhost:5000").rstrip("/")
VIDEO_DELAY_MINUTES = int(os.getenv("VIDEO_DELAY_MINUTES", "60"))
REPORT_DELAY_MINUTES = int(os.getenv("REPORT_DELAY_MINUTES", "1440"))  # 24 часа
POLL_INTERVAL_SECONDS = int(os.getenv("WORKER_POLL_SECONDS", "300"))


def build_message(sess: storage.TrialSession) -> str:
    parent_url = f"{BASE_URL}/parent/{sess.token}"
    game_url = f"{BASE_URL}/game/{sess.game_slug}" if sess.game_slug else None

    lines = [
        f"Здравствуйте, {sess.parent_name}!",
        "",
        f"{sess.child_name} только что прошёл(а) пробный урок KIBERone — "
        f"и создал(а) свою первую игру.",
        "",
    ]

    if sess.video_filename:
        lines.append("Вот короткое видео с урока:")
        lines.append(f"{parent_url}")
        lines.append("")

    if game_url:
        lines.append("А вот сама игра — открывается прямо в браузере:")
        lines.append(game_url)
        lines.append("")

    lines.extend([
        "Через 24 часа я пришлю развёрнутый персональный отчёт "
        "с рекомендациями по дальнейшему обучению.",
        "",
        f"С уважением, {sess.tutor_name}",
        f"KIBERone · {sess.filial}",
    ])
    return "\n".join(lines)


def _finished_minutes_ago(sess: storage.TrialSession) -> Optional[float]:
    if not sess.is_finished or not sess.finished_at:
        return None
    try:
        finished_at = datetime.fromisoformat(sess.finished_at)
    except (ValueError, TypeError):
        return None
    return (datetime.now() - finished_at).total_seconds() / 60.0


def should_send_video(sess: storage.TrialSession) -> bool:
    if sess.video_sent_at or not sess.parent_phone:
        return False
    elapsed = _finished_minutes_ago(sess)
    return elapsed is not None and elapsed >= VIDEO_DELAY_MINUTES


def should_send_report(sess: storage.TrialSession) -> bool:
    if sess.report_sent_at or not sess.parent_phone:
        return False
    elapsed = _finished_minutes_ago(sess)
    return elapsed is not None and elapsed >= REPORT_DELAY_MINUTES


def process_videos(client: WazzupClient) -> int:
    sent = 0
    for sess in storage.list_sessions(limit=200):
        if not should_send_video(sess):
            continue
        try:
            text = build_message(sess)
            client.send_text(sess.parent_phone, text)
            storage.mark_video_sent(sess.token)
            logger.info(
                "Sent video message to %s (child=%s, token=%s)",
                sess.parent_phone, sess.child_name, sess.token,
            )
            sent += 1
        except Exception as e:
            logger.exception("Failed to send video message for %s: %s", sess.token, e)
    return sent


def _build_checkpoints_payload(sess: storage.TrialSession) -> list[dict]:
    """Готовим список чекпойнтов в виде, понятном ai_writer."""
    out: list[dict] = []
    for ev in sess.checkpoints:
        cp = CHECKPOINTS_BY_ID.get(ev.id)
        if not cp:
            continue
        out.append({
            "id": cp.id,
            "emoji": cp.emoji,
            "title_admin": cp.title_admin,
            "parent_message": cp.parent_message,
            "timestamp": ev.timestamp,
            "note": ev.note,
        })
    return out


def build_report_message(sess: storage.TrialSession) -> str:
    report_url = f"{BASE_URL}/parent/{sess.token}/report"
    lines = [
        f"{sess.parent_name}, доброго времени!",
        "",
        f"Подготовили персональный разбор пробного урока {sess.child_name} — "
        "наши наблюдения, сильные стороны ребёнка и рекомендации.",
        "",
        f"Открыть отчёт: {report_url}",
        "",
        f"Если возникнут вопросы — я на связи.",
        f"{sess.tutor_name}, KIBERone · {sess.filial}",
    ]
    return "\n".join(lines)


def process_reports(client: WazzupClient) -> int:
    sent = 0
    for sess in storage.list_sessions(limit=200):
        if not should_send_report(sess):
            continue
        try:
            # 1. Генерируем отчёт (если ещё не было)
            if not sess.report_data:
                logger.info("Generating report for token=%s", sess.token)
                report = generate_report(
                    child_name=sess.child_name,
                    child_age=sess.child_age,
                    grade=sess.grade,
                    parent_name=sess.parent_name,
                    tutor_name=sess.tutor_name,
                    filial=sess.filial,
                    checkpoints=_build_checkpoints_payload(sess),
                    parent_test=sess.parent_test,
                )
                storage.save_report(sess.token, report)

            # 2. Отправляем ссылку
            text = build_report_message(sess)
            client.send_text(sess.parent_phone, text)
            storage.mark_report_sent(sess.token)
            logger.info(
                "Sent report link to %s (child=%s, token=%s)",
                sess.parent_phone, sess.child_name, sess.token,
            )
            sent += 1
        except Exception as e:
            logger.exception("Failed to process report for %s: %s", sess.token, e)
    return sent


def process_pending(client: WazzupClient) -> int:
    """Один проход — обоих потоков."""
    return process_videos(client) + process_reports(client)


def main() -> None:
    parser = argparse.ArgumentParser(description="ИгроВАН worker — отправка через 1ч")
    parser.add_argument("--once", action="store_true", help="Один проход и выход (для cron)")
    args = parser.parse_args()

    client = WazzupClient()
    logger.info(
        "Worker запущен. video_delay=%dmin, report_delay=%dmin, poll=%ds, dry_run=%s",
        VIDEO_DELAY_MINUTES, REPORT_DELAY_MINUTES, POLL_INTERVAL_SECONDS, client.dry_run,
    )

    if args.once:
        n = process_pending(client)
        logger.info("Однократный проход завершён, отправлено: %d", n)
        return

    while True:
        try:
            n = process_pending(client)
            if n:
                logger.info("Цикл завершён, отправлено: %d", n)
        except Exception as e:
            logger.exception("Ошибка в цикле worker: %s", e)
        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
