"""Чекпойнты пробного урока ИгроВАН.

Наставник тыкает кнопки в админке, родитель видит, как растёт прогресс
ребёнка в реальном времени на своей странице.

Список рассчитан под Scratch-урок (~60 минут): 7 этапов, ~8-9 минут на каждый.
Если потребуется адаптировать под другой сценарий — менять здесь, остальной
код не зависит от конкретных id.

ВАЖНО: id используются как ключи в JSON-хранилище. Если переименуешь —
старые сессии перестанут отображать прогресс корректно. Лучше добавлять
новые, не трогая существующие.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Checkpoint:
    id: str
    emoji: str
    title_admin: str        # коротко для наставника
    title_parent: str       # развёрнуто для родителя
    parent_message: str     # что увидит родитель — эмоционально, на «вы»


CHECKPOINTS: list[Checkpoint] = [
    Checkpoint(
        id="arrival",
        emoji="🎒",
        title_admin="Прибыл, получил бейдж",
        title_parent="Миссия началась",
        parent_message="Ваш ребёнок получил бейдж разработчика и приступил к миссии.",
    ),
    Checkpoint(
        id="intro",
        emoji="🧠",
        title_admin="Знакомство с инструментами",
        title_parent="Знакомство с инструментами",
        parent_message="Изучает рабочую среду — то, в чём программисты создают игры.",
    ),
    Checkpoint(
        id="first_blocks",
        emoji="🧩",
        title_admin="Соединил первые блоки",
        title_parent="Первые строки кода",
        parent_message="Соединил первые блоки кода. Это его первая программа в жизни.",
    ),
    Checkpoint(
        id="character_alive",
        emoji="🏃",
        title_admin="Герой ожил",
        title_parent="Герой ожил",
        parent_message="Персонаж задвигался на экране! Ребёнок только что заставил картинку реагировать на свои команды.",
    ),
    Checkpoint(
        id="enemies_added",
        emoji="👾",
        title_admin="Добавил врагов / препятствия",
        title_parent="Появились вызовы",
        parent_message="Добавил препятствия и противников — игра становится по-настоящему сложной.",
    ),
    Checkpoint(
        id="game_runs",
        emoji="🎮",
        title_admin="Игра запустилась",
        title_parent="Игра работает!",
        parent_message="Полноценная игра запустилась. Ребёнок играет в то, что создал сам.",
    ),
    Checkpoint(
        id="presentation",
        emoji="🎤",
        title_admin="Защитил игру перед группой",
        title_parent="Защита проекта",
        parent_message="Только что вышел и защитил свою работу перед группой. Это был его первый питч.",
    ),
]


CHECKPOINTS_BY_ID: dict[str, Checkpoint] = {c.id: c for c in CHECKPOINTS}


def get_checkpoint(checkpoint_id: str) -> Checkpoint | None:
    return CHECKPOINTS_BY_ID.get(checkpoint_id)


def total_count() -> int:
    return len(CHECKPOINTS)
