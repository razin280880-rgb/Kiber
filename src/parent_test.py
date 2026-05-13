"""5-вопросный тест родителя.

Цель — НЕ психодиагностика. Цель — дать родителю инсайт за 2 минуты:
«какое из 4 IT-направлений KIBERone подходит вашему ребёнку».

Каждый ответ — это +1 к одному из 4 треков:
    game     — Game Dev Track (игры, графика, интерактив)
    ai       — AI/Data Track (нейросети, данные, логика)
    web      — Web/Design Track (сайты, UX, продуктовое мышление)
    robotics — Robotics Track (роботы, электроника, IoT)

Победитель по сумме — итоговая рекомендация. При равенстве — берём
первый по порядку (game первый, потому что это базовый трек KIBERone).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


TrackKey = Literal["game", "ai", "web", "robotics"]


@dataclass(frozen=True)
class TestOption:
    key: str       # уникальный ключ ответа в вопросе (a/b/c/d)
    label: str
    track: TrackKey


@dataclass(frozen=True)
class TestQuestion:
    id: str
    question: str
    options: list[TestOption]


@dataclass(frozen=True)
class Track:
    key: TrackKey
    label: str
    tagline: str
    description: str


TRACKS: dict[TrackKey, Track] = {
    "game": Track(
        key="game",
        label="Game Dev Track",
        tagline="Создавать игры, которые играются",
        description=(
            "Ребёнок мыслит сценариями, любит интерактив и хочет видеть результат на экране сразу. "
            "На Game Dev Track он научится делать 2D и 3D игры, придумывать механики и баланс — "
            "и через год соберёт портфолио из 5-7 готовых проектов."
        ),
    ),
    "ai": Track(
        key="ai",
        label="AI / Data Track",
        tagline="Учить компьютер думать",
        description=(
            "Ребёнку интересно как устроены ChatGPT и нейросети, он любит логические задачи. "
            "На AI/Data Track он научится работать с данными, обучать модели и собирать собственных AI-ассистентов — "
            "одна из самых востребованных профессий ближайших 10 лет."
        ),
    ),
    "web": Track(
        key="web",
        label="Web / Design Track",
        tagline="Делать продукты, которыми пользуются",
        description=(
            "Ребёнок мыслит визуально, любит когда красиво и удобно. "
            "На Web/Design Track он научится делать сайты, мобильные интерфейсы и собственные онлайн-проекты — "
            "к концу курса будет своё портфолио и понимание как зарабатывают в IT."
        ),
    ),
    "robotics": Track(
        key="robotics",
        label="Robotics Track",
        tagline="Соединять код и реальный мир",
        description=(
            "Ребёнку нравится разбирать, собирать и видеть как код управляет железом. "
            "На Robotics Track он научится программировать роботов, работать с датчиками и Arduino — "
            "это путь к инженерным олимпиадам и проф-конкурсам."
        ),
    ),
}


QUESTIONS: list[TestQuestion] = [
    TestQuestion(
        id="q1_role",
        question="Какая роль кажется ближе вашему ребёнку?",
        options=[
            TestOption("a", "Архитектор — планирует, продумывает, строит", "web"),
            TestOption("b", "Инженер — решает задачи, экспериментирует, чинит", "robotics"),
            TestOption("c", "Творец — придумывает миры и истории", "game"),
            TestOption("d", "Исследователь — копается, разбирается, ищет закономерности", "ai"),
        ],
    ),
    TestQuestion(
        id="q2_strength",
        question="Что ребёнку даётся легче всего?",
        options=[
            TestOption("a", "Логические задачи (математика, шахматы, головоломки)", "ai"),
            TestOption("b", "Творческие проекты (рисует, лепит, фантазирует)", "game"),
            TestOption("c", "Истории и тексты (читает, придумывает, описывает)", "web"),
            TestOption("d", "Конструкторы и техника (Лего, моторчики, разбирает игрушки)", "robotics"),
        ],
    ),
    TestQuestion(
        id="q3_problem",
        question="Когда встречается сложная задача, ребёнок чаще:",
        options=[
            TestOption("a", "Долго придумывает план и пробует много вариантов", "ai"),
            TestOption("b", "Пробует руками, ломает, переделывает", "robotics"),
            TestOption("c", "Рисует или представляет в голове как должно получиться", "web"),
            TestOption("d", "Превращает в игру — придумывает правила и проходит уровень", "game"),
        ],
    ),
    TestQuestion(
        id="q4_screen",
        question="Что ребёнок чаще делает за экраном?",
        options=[
            TestOption("a", "Играет в игры (Roblox, Minecraft, мобильные)", "game"),
            TestOption("b", "Смотрит обучающие/любопытные ролики, гуглит факты", "ai"),
            TestOption("c", "Сидит в соцсетях, ведёт блог, мечтает о канале", "web"),
            TestOption("d", "Смотрит про машины, технику, ракеты, эксперименты", "robotics"),
        ],
    ),
    TestQuestion(
        id="q5_goal",
        question="Какая ваша главная цель, отдавая ребёнка в IT?",
        options=[
            TestOption("a", "Развить мышление и логику", "ai"),
            TestOption("b", "Чтобы понимал технологии и не боялся их", "robotics"),
            TestOption("c", "Дать профессию будущего и заработок", "web"),
            TestOption("d", "Чтобы нашёл хобби, среду общения, кайф от создания", "game"),
        ],
    ),
]

QUESTIONS_BY_ID: dict[str, TestQuestion] = {q.id: q for q in QUESTIONS}


def score_test(answers: dict[str, str]) -> tuple[TrackKey, dict[TrackKey, int]]:
    """answers: {question_id: option_key} → (winning_track, full_score)."""
    score: dict[TrackKey, int] = {"game": 0, "ai": 0, "web": 0, "robotics": 0}
    for q in QUESTIONS:
        chosen = answers.get(q.id)
        if not chosen:
            continue
        for opt in q.options:
            if opt.key == chosen:
                score[opt.track] += 1
                break

    # Победитель: максимум, при равенстве — game / ai / web / robotics (порядок ключей)
    winner: TrackKey = "game"
    best = -1
    for key in ("game", "ai", "web", "robotics"):
        if score[key] > best:  # type: ignore[index]
            best = score[key]  # type: ignore[index]
            winner = key  # type: ignore[assignment]
    return winner, score
