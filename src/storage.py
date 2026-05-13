"""JSON-хранилище для ИгроВАН.

Две сущности:
    GameRecord (Спринт 1) — итог пробного, загруженная игра + метаданные.
        games/<slug>.sb3 + games/<slug>.json

    TrialSession (Спринт 2) — сама сессия пробного урока: чекпойнты,
    тест родителя, привязка к телефону, ссылка на родительскую страницу.
        sessions/<token>.json
        videos/<token>.<ext>   (загружается опционально, для отправки через 1ч)

Сессия может существовать БЕЗ игры (ребёнок ушёл недоделав .sb3)
и игра может существовать БЕЗ сессии (загрузили постфактум). Связь —
опциональное поле game_slug в TrialSession.
"""

from __future__ import annotations

import json
import secrets
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from slugify import slugify


PROJECT_DIR = Path(__file__).resolve().parent.parent
GAMES_DIR = PROJECT_DIR / "games"
SESSIONS_DIR = PROJECT_DIR / "sessions"
VIDEOS_DIR = PROJECT_DIR / "videos"
PHOTOS_DIR = PROJECT_DIR / "photos"
PASSPORTS_DIR = PROJECT_DIR / "passports"
COUNTER_FILE = PASSPORTS_DIR / "counter.json"


# --- Возрастные грейды (для бейджа и паспорта) ---------------------

def grade_for_age(age: int) -> str:
    if age <= 7:
        return "Padawan"
    if age <= 10:
        return "Cadet"
    if age <= 12:
        return "Engineer"
    return "Architect"


# ===================================================================
#                    GameRecord (Спринт 1)
# ===================================================================

@dataclass
class GameRecord:
    slug: str
    child_name: str
    child_age: int
    filial: str
    tutor_name: str
    parent_phone: str
    created_at: str

    @property
    def sb3_path(self) -> Path:
        return GAMES_DIR / f"{self.slug}.sb3"

    @property
    def json_path(self) -> Path:
        return GAMES_DIR / f"{self.slug}.json"

    @property
    def grade(self) -> str:
        return grade_for_age(self.child_age)


def make_slug(child_name: str) -> str:
    base = slugify(child_name, lowercase=True) or "kid"
    stamp = datetime.now().strftime("%d%m%y-%H%M")
    return f"{base}-{stamp}"


def save_game(
    child_name: str,
    child_age: int,
    filial: str,
    tutor_name: str,
    parent_phone: str,
    sb3_bytes: bytes,
) -> GameRecord:
    GAMES_DIR.mkdir(parents=True, exist_ok=True)
    slug = make_slug(child_name)
    record = GameRecord(
        slug=slug,
        child_name=child_name.strip(),
        child_age=int(child_age),
        filial=filial.strip(),
        tutor_name=tutor_name.strip(),
        parent_phone=parent_phone.strip(),
        created_at=datetime.now().isoformat(timespec="seconds"),
    )
    record.sb3_path.write_bytes(sb3_bytes)
    record.json_path.write_text(
        json.dumps(asdict(record), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return record


def load_game(slug: str) -> Optional[GameRecord]:
    json_path = GAMES_DIR / f"{slug}.json"
    if not json_path.exists():
        return None
    data = json.loads(json_path.read_text(encoding="utf-8"))
    return GameRecord(**data)


def list_games(limit: int = 50) -> list[GameRecord]:
    if not GAMES_DIR.exists():
        return []
    files = sorted(
        GAMES_DIR.glob("*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[:limit]
    out: list[GameRecord] = []
    for f in files:
        try:
            out.append(GameRecord(**json.loads(f.read_text(encoding="utf-8"))))
        except Exception:
            continue
    return out


# ===================================================================
#                    TrialSession (Спринт 2)
# ===================================================================

@dataclass
class CheckpointEvent:
    """Зафиксированный наставником этап урока."""
    id: str           # совпадает с CHECKPOINTS[*].id из checkpoints.py
    timestamp: str    # ISO 8601
    note: str = ""    # необязательный комментарий наставника


@dataclass
class TrialSession:
    token: str        # короткий URL-safe токен для родительской страницы
    child_name: str
    child_age: int
    filial: str
    tutor_name: str
    parent_phone: str
    parent_name: str
    created_at: str
    finished_at: Optional[str] = None
    checkpoints: list[CheckpointEvent] = field(default_factory=list)
    parent_test: Optional[dict] = None    # {answers: {...}, result_key: '...', result_label: '...'}
    game_slug: Optional[str] = None       # если игра загружена (Спринт 1)
    video_filename: Optional[str] = None  # videos/<token>.<ext>
    video_sent_at: Optional[str] = None   # ISO timestamp когда worker отправил
    report_data: Optional[dict] = None    # {title, intro, observations: [...], takeaways: [...], cta}
    report_generated_at: Optional[str] = None
    report_sent_at: Optional[str] = None
    passport_serial: Optional[str] = None     # KBR-2026-NCK-0042
    passport_photo: Optional[str] = None      # photos/<token>.<ext>
    passport_created_at: Optional[str] = None

    @property
    def json_path(self) -> Path:
        return SESSIONS_DIR / f"{self.token}.json"

    @property
    def grade(self) -> str:
        return grade_for_age(self.child_age)

    @property
    def is_finished(self) -> bool:
        return self.finished_at is not None

    @property
    def checkpoint_ids(self) -> set[str]:
        return {c.id for c in self.checkpoints}


def _new_token() -> str:
    """URL-safe токен 12 символов. Достаточно энтропии для пары лет работы."""
    return secrets.token_urlsafe(9).replace("_", "").replace("-", "")[:12] or secrets.token_hex(6)


def create_session(
    child_name: str,
    child_age: int,
    filial: str,
    tutor_name: str,
    parent_phone: str,
    parent_name: str,
) -> TrialSession:
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    session = TrialSession(
        token=_new_token(),
        child_name=child_name.strip(),
        child_age=int(child_age),
        filial=filial.strip(),
        tutor_name=tutor_name.strip(),
        parent_phone=parent_phone.strip(),
        parent_name=parent_name.strip(),
        created_at=datetime.now().isoformat(timespec="seconds"),
    )
    _save_session(session)
    return session


def _save_session(session: TrialSession) -> None:
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    data = asdict(session)
    session.json_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_session(token: str) -> Optional[TrialSession]:
    path = SESSIONS_DIR / f"{token}.json"
    if not path.exists():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    checkpoints = [CheckpointEvent(**c) for c in raw.pop("checkpoints", [])]
    return TrialSession(**raw, checkpoints=checkpoints)


def list_sessions(limit: int = 50) -> list[TrialSession]:
    if not SESSIONS_DIR.exists():
        return []
    files = sorted(
        SESSIONS_DIR.glob("*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[:limit]
    out: list[TrialSession] = []
    for f in files:
        try:
            raw = json.loads(f.read_text(encoding="utf-8"))
            checkpoints = [CheckpointEvent(**c) for c in raw.pop("checkpoints", [])]
            out.append(TrialSession(**raw, checkpoints=checkpoints))
        except Exception:
            continue
    return out


def add_checkpoint(token: str, checkpoint_id: str, note: str = "") -> Optional[TrialSession]:
    session = load_session(token)
    if not session or session.is_finished:
        return session
    if checkpoint_id in session.checkpoint_ids:
        # уже отмечен — обновляем заметку, не дублируем событие
        for c in session.checkpoints:
            if c.id == checkpoint_id and note:
                c.note = note
                break
    else:
        session.checkpoints.append(
            CheckpointEvent(
                id=checkpoint_id,
                timestamp=datetime.now().isoformat(timespec="seconds"),
                note=note.strip(),
            )
        )
    _save_session(session)
    return session


def remove_checkpoint(token: str, checkpoint_id: str) -> Optional[TrialSession]:
    session = load_session(token)
    if not session or session.is_finished:
        return session
    session.checkpoints = [c for c in session.checkpoints if c.id != checkpoint_id]
    _save_session(session)
    return session


def finish_session(token: str) -> Optional[TrialSession]:
    session = load_session(token)
    if not session:
        return None
    if not session.is_finished:
        session.finished_at = datetime.now().isoformat(timespec="seconds")
        _save_session(session)
    return session


def attach_game(token: str, slug: str) -> Optional[TrialSession]:
    session = load_session(token)
    if not session:
        return None
    session.game_slug = slug
    _save_session(session)
    return session


def attach_video(token: str, filename: str) -> Optional[TrialSession]:
    session = load_session(token)
    if not session:
        return None
    session.video_filename = filename
    _save_session(session)
    return session


def save_parent_test(token: str, answers: dict, result_key: str, result_label: str) -> Optional[TrialSession]:
    session = load_session(token)
    if not session:
        return None
    session.parent_test = {
        "answers": answers,
        "result_key": result_key,
        "result_label": result_label,
        "submitted_at": datetime.now().isoformat(timespec="seconds"),
    }
    _save_session(session)
    return session


def mark_video_sent(token: str) -> Optional[TrialSession]:
    session = load_session(token)
    if not session:
        return None
    session.video_sent_at = datetime.now().isoformat(timespec="seconds")
    _save_session(session)
    return session


def save_report(token: str, report_data: dict) -> Optional[TrialSession]:
    session = load_session(token)
    if not session:
        return None
    session.report_data = report_data
    session.report_generated_at = datetime.now().isoformat(timespec="seconds")
    _save_session(session)
    return session


def mark_report_sent(token: str) -> Optional[TrialSession]:
    session = load_session(token)
    if not session:
        return None
    session.report_sent_at = datetime.now().isoformat(timespec="seconds")
    _save_session(session)
    return session


# --- Паспорт разработчика ----------------------------------------

def _next_serial_number(filial_code: str, year: int) -> int:
    """Атомарный инкремент счётчика паспортов на филиал-год.

    Хранилище: passports/counter.json формата {"2026:NCK": 42, "2026:KZN": 5}.
    Под высокой нагрузкой не атомарно (нет lock), но для пары пробных
    в день в одном филиале это не проблема.
    """
    PASSPORTS_DIR.mkdir(parents=True, exist_ok=True)
    key = f"{year}:{filial_code}"
    data: dict[str, int] = {}
    if COUNTER_FILE.exists():
        try:
            data = json.loads(COUNTER_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    data[key] = int(data.get(key, 0)) + 1
    COUNTER_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data[key]


def issue_passport(token: str, filial_code: str) -> Optional[TrialSession]:
    """Выдаёт серийник паспорта. Если уже выдан — возвращает сессию без изменений."""
    session = load_session(token)
    if not session:
        return None
    if session.passport_serial:
        return session
    now = datetime.now()
    n = _next_serial_number(filial_code, now.year)
    session.passport_serial = f"KBR-{now.year}-{filial_code}-{n:04d}"
    session.passport_created_at = now.isoformat(timespec="seconds")
    _save_session(session)
    return session


def attach_passport_photo(token: str, filename: str) -> Optional[TrialSession]:
    session = load_session(token)
    if not session:
        return None
    session.passport_photo = filename
    _save_session(session)
    return session
