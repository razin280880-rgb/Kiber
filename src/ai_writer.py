"""Claude-генератор персонального отчёта по пробному уроку.

Через 24 часа после finish worker зовёт этот модуль с данными сессии:
имя/возраст/грейд ребёнка, список чекпойнтов с заметками наставника,
результат теста родителя — и получает структурированный JSON отчёта,
который рендерится в шаблоне report.html.

Если ANTHROPIC_API_KEY не задан, модуль работает в fallback-режиме:
генерирует шаблонный, но всё ещё персонализированный отчёт без AI.
Это позволяет тестировать pipeline без затрат.

Кэширование: системный промпт (~600 токенов, не меняется между сессиями)
помечен cache_control=ephemeral. После первого вызова все последующие
платят 0.1x за input по этим токенам.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


# Импорт Anthropic SDK откладываем до фактического использования,
# чтобы worker мог стартовать без установленного пакета (dry-run).
try:
    from anthropic import Anthropic  # type: ignore
    _ANTHROPIC_AVAILABLE = True
except ImportError:  # pragma: no cover
    Anthropic = None  # type: ignore
    _ANTHROPIC_AVAILABLE = False


DEFAULT_MODEL = "claude-haiku-4-5"


SYSTEM_PROMPT = """Ты — куратор персональных отчётов в KIBERone, IT-академии \
для детей 6–14 лет (треки: Game Dev, AI/Data, Web/Design, Robotics).

Твоя задача — после пробного урока написать родителю короткий, тёплый, \
конкретный отчёт о том, что произошло с его ребёнком на уроке, и какие \
у него сильные стороны.

ПРИНЦИПЫ:
1. Пиши на «вы», по-человечески, без канцелярита и без слова «эффективный».
2. Ничего не выдумывай о ребёнке. Опирайся только на факты: какие \
   чекпойнты он прошёл, какие были заметки наставника, какой возрастной \
   грейд (Padawan 6–7 / Cadet 8–10 / Engineer 11–12 / Architect 13–14), \
   какое направление рекомендовано по тесту родителя.
3. Не обещай конкретные финансовые результаты («ребёнок будет зарабатывать»).
4. Не сравнивай ребёнка с другими детьми.
5. Каждое наблюдение должно отсылать к конкретному моменту урока \
   (если в чекпойнтах есть «защитил игру» — наблюдение про публичную \
   уверенность; если есть «добавил врагов» — про умение усложнять задачу).
6. Не используй штампы «огромный потенциал», «впечатляющие результаты», \
   «прекрасный ребёнок». Заменяй на конкретику.
7. Отвечай ВСЕГДА вызовом инструмента save_trial_report — никакого \
   свободного текста.
"""


REPORT_TOOL = {
    "name": "save_trial_report",
    "description": (
        "Сохранить структурированный отчёт о пробном уроке. "
        "Все поля обязательны."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": (
                    "Короткий эмоциональный заголовок, отражающий главное "
                    "наблюдение про конкретного ребёнка. 4–8 слов. "
                    "Пример: «Михаил готов создавать игры» или "
                    "«У Софии — голова инженера»."
                ),
            },
            "intro": {
                "type": "string",
                "description": (
                    "1–2 предложения с обращением к родителю по имени. "
                    "Тёплое, конкретное."
                ),
            },
            "observations": {
                "type": "array",
                "description": (
                    "3 наблюдения с урока. Каждое — про конкретный момент."
                ),
                "minItems": 3,
                "maxItems": 4,
                "items": {
                    "type": "object",
                    "properties": {
                        "emoji": {"type": "string", "description": "Один эмоджи"},
                        "title": {"type": "string", "description": "3–5 слов"},
                        "text": {"type": "string", "description": "2–3 предложения"},
                    },
                    "required": ["emoji", "title", "text"],
                },
            },
            "takeaways": {
                "type": "array",
                "description": (
                    "2–3 коротких вывода о сильных сторонах ребёнка, "
                    "по 1 предложению."
                ),
                "minItems": 2,
                "maxItems": 3,
                "items": {"type": "string"},
            },
            "cta": {
                "type": "string",
                "description": (
                    "1–2 предложения с конкретным следующим шагом для "
                    "родителя. Не «приходите на курс», а «давайте обсудим "
                    "что подойдёт именно вашему ребёнку». Упомяни рекомендованный трек."
                ),
            },
        },
        "required": ["title", "intro", "observations", "takeaways", "cta"],
    },
}


def _build_user_prompt(
    *,
    child_name: str,
    child_age: int,
    grade: str,
    parent_name: str,
    tutor_name: str,
    filial: str,
    checkpoints: list[dict],  # [{id, emoji, title_admin, parent_message, timestamp, note}]
    parent_test: Optional[dict],  # {result_key, result_label, answers}
) -> str:
    cp_lines = []
    for cp in checkpoints:
        line = f"- {cp['emoji']} {cp['title_admin']}"
        if cp.get("note"):
            line += f' — заметка наставника: "{cp["note"]}"'
        cp_lines.append(line)
    cp_block = "\n".join(cp_lines) if cp_lines else "(не отмечено)"

    test_block = "Тест родителя не пройден."
    if parent_test:
        test_block = (
            f"Тест родителя пройден. Рекомендованный трек: "
            f"{parent_test.get('result_label', 'unknown')} "
            f"(ключ: {parent_test.get('result_key', 'unknown')})."
        )

    return f"""Сгенерируй отчёт о пробном уроке для родителя.

ДАННЫЕ СЕССИИ:
- Ребёнок: {child_name}, {child_age} лет
- Грейд по возрасту: {grade}
- Родитель: {parent_name}
- Наставник: {tutor_name}
- Филиал KIBERone: {filial}

ЧЕКПОЙНТЫ УРОКА (что было отмечено наставником):
{cp_block}

ТЕСТ РОДИТЕЛЯ:
{test_block}

Напиши отчёт. Помни: только факты, никаких штампов, обращение к {parent_name} на «вы», \
наблюдения — про конкретные моменты, упомянутые выше.
"""


def _fallback_report(
    *,
    child_name: str,
    parent_name: str,
    tutor_name: str,
    checkpoint_titles: list[str],
    track_label: Optional[str],
) -> dict:
    """Шаблонный отчёт без AI — используется когда нет ANTHROPIC_API_KEY."""
    obs = [
        {
            "emoji": "🧩",
            "title": "Первый код в жизни",
            "text": (
                f"{child_name} соединил(а) свои первые блоки кода и заставил(а) "
                "персонажа двигаться. Это базовый навык, на котором стоит всё "
                "программирование — и теперь он у ребёнка есть."
            ),
        },
        {
            "emoji": "🎮",
            "title": "Игра, которая работает",
            "text": (
                "За один урок собрана полноценная игра — с героем, препятствиями "
                "и логикой. Не презентация и не задание, а настоящий рабочий проект."
            ),
        },
        {
            "emoji": "🎤",
            "title": "Защита перед группой",
            "text": (
                f"{child_name} вышел(а) и показал(а) свою игру другим детям. "
                "Этот навык — рассказать о своей работе — нужен любому современному "
                "специалисту, и развивается только практикой."
            ),
        },
    ]
    cta = (
        f"Уважаемая {parent_name}, давайте созвонимся и обсудим, какой курс "
        f"KIBERone подойдёт {child_name} лучше всего."
    )
    if track_label:
        cta = (
            f"По результатам теста и наблюдениям рекомендуем направление "
            f"{track_label}. {cta}"
        )
    return {
        "title": f"{child_name} создал(а) свою первую игру",
        "intro": (
            f"{parent_name}, спасибо что доверили нам ваш пробный урок. "
            "Ниже — короткий отчёт о том, что мы увидели."
        ),
        "observations": obs,
        "takeaways": [
            "Ребёнок прошёл полный цикл: от блоков кода до защиты проекта.",
            "Не было ступора при столкновении со сложностью — пробовал, переделывал.",
        ],
        "cta": cta,
    }


def generate_report(
    *,
    child_name: str,
    child_age: int,
    grade: str,
    parent_name: str,
    tutor_name: str,
    filial: str,
    checkpoints: list[dict],
    parent_test: Optional[dict] = None,
    model: str = DEFAULT_MODEL,
) -> dict:
    """Генерирует структурированный JSON отчёта.

    Возвращает dict с ключами: title, intro, observations, takeaways, cta.
    При отсутствии API-ключа или ошибке вызова возвращает fallback.
    """
    track_label = (parent_test or {}).get("result_label")
    checkpoint_titles = [cp.get("title_admin", "") for cp in checkpoints]

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key or not _ANTHROPIC_AVAILABLE:
        if not api_key:
            logger.warning("ANTHROPIC_API_KEY не задан — используем fallback-отчёт")
        else:
            logger.warning("Пакет anthropic не установлен — используем fallback-отчёт")
        return _fallback_report(
            child_name=child_name,
            parent_name=parent_name,
            tutor_name=tutor_name,
            checkpoint_titles=checkpoint_titles,
            track_label=track_label,
        )

    client = Anthropic(api_key=api_key)
    user_prompt = _build_user_prompt(
        child_name=child_name,
        child_age=child_age,
        grade=grade,
        parent_name=parent_name,
        tutor_name=tutor_name,
        filial=filial,
        checkpoints=checkpoints,
        parent_test=parent_test,
    )

    try:
        resp = client.messages.create(
            model=model,
            max_tokens=2000,
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            tools=[REPORT_TOOL],
            tool_choice={"type": "tool", "name": "save_trial_report"},
            messages=[{"role": "user", "content": user_prompt}],
        )
    except Exception as e:
        logger.exception("Claude API call failed: %s", e)
        return _fallback_report(
            child_name=child_name,
            parent_name=parent_name,
            tutor_name=tutor_name,
            checkpoint_titles=checkpoint_titles,
            track_label=track_label,
        )

    # Ищем tool_use блок в ответе
    for block in resp.content:
        if getattr(block, "type", None) == "tool_use" and block.name == "save_trial_report":
            data = dict(block.input)
            usage = getattr(resp, "usage", None)
            if usage:
                logger.info(
                    "Claude usage: in=%s out=%s cache_read=%s cache_write=%s",
                    getattr(usage, "input_tokens", None),
                    getattr(usage, "output_tokens", None),
                    getattr(usage, "cache_read_input_tokens", None),
                    getattr(usage, "cache_creation_input_tokens", None),
                )
            return data

    logger.error("Claude response had no tool_use block — fallback")
    return _fallback_report(
        child_name=child_name,
        parent_name=parent_name,
        tutor_name=tutor_name,
        checkpoint_titles=checkpoint_titles,
        track_label=track_label,
    )
