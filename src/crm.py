"""s20.online (AlfaCRM) — поиск клиента по телефону.

Адаптировано из progress-report-bot/src/crm.py: нам нужен только один
метод — поиск клиента по номеру телефона, чтобы на пробном уроке наставник
ввёл только телефон родителя и получил предзаполненную форму (имя ребёнка,
возраст, родитель).

Если переменные S20_EMAIL / S20_API_KEY / S20_HOSTNAME не заданы —
клиент работает в dry-run: всегда возвращает None (как будто клиент
не найден). Это позволяет тестировать UI без боевого CRM.

Branch ID (филиал) у каждого города свой, маппинг — в S20_BRANCHES
(формат: 'Naberezhnye Chelny=1,Kazan=2,...').
"""

from __future__ import annotations

import logging
import os
import time
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from src.wazzup import WazzupClient  # переиспользуем normalize_phone


logger = logging.getLogger(__name__)


def parse_branches_env(raw: str) -> dict[str, int]:
    """'Chelny=1,Kazan=2' → {'Chelny': 1, 'Kazan': 2}."""
    out: dict[str, int] = {}
    if not raw:
        return out
    for pair in raw.split(","):
        pair = pair.strip()
        if "=" not in pair:
            continue
        name, _, value = pair.partition("=")
        try:
            out[name.strip()] = int(value.strip())
        except ValueError:
            continue
    return out


class S20Client:
    """Минимальный клиент AlfaCRM/s20.online для поиска клиента по телефону."""

    def __init__(
        self,
        email: Optional[str] = None,
        api_key: Optional[str] = None,
        hostname: Optional[str] = None,
        branches: Optional[dict[str, int]] = None,
    ):
        self.email = email or os.getenv("S20_EMAIL")
        self.api_key = api_key or os.getenv("S20_API_KEY")
        self.hostname = hostname or os.getenv("S20_HOSTNAME")
        self.branches = branches or parse_branches_env(os.getenv("S20_BRANCHES", ""))
        self.dry_run = not (self.email and self.api_key and self.hostname)

        self._token: Optional[str] = None
        self._token_expires: float = 0

        if self.dry_run:
            logger.warning(
                "S20Client в dry-run — не заданы S20_EMAIL / S20_API_KEY / S20_HOSTNAME."
            )
            return

        self.base_url = f"https://{self.hostname}/v2api"
        self._session = requests.Session()
        retries = Retry(
            total=4,
            backoff_factor=1.5,
            status_forcelist=[500, 502, 503, 504, 429],
            allowed_methods=["POST"],
            raise_on_status=False,
        )
        self._session.mount("https://", HTTPAdapter(max_retries=retries))

    def _authenticate(self) -> None:
        resp = self._session.post(
            f"{self.base_url}/auth/login",
            json={"email": self.email, "api_key": self.api_key},
            timeout=15,
        )
        resp.raise_for_status()
        self._token = resp.json()["token"]
        self._token_expires = time.time() + 3500

    def _headers(self) -> dict:
        if not self._token or time.time() > self._token_expires:
            self._authenticate()
        return {"X-ALFACRM-TOKEN": self._token}  # type: ignore[dict-item]

    def _post(self, branch_id: int, endpoint: str, payload: dict) -> dict:
        url = f"{self.base_url}/{branch_id}/{endpoint}"
        resp = self._session.post(url, headers=self._headers(), json=payload, timeout=20)
        if resp.status_code == 401:
            self._token = None
            resp = self._session.post(url, headers=self._headers(), json=payload, timeout=20)
        resp.raise_for_status()
        return resp.json()

    def branch_id_for_filial(self, filial: str) -> Optional[int]:
        """Подбирает branch_id по названию филиала. Возвращает None если не найден."""
        if not filial:
            return None
        # Точное совпадение
        if filial in self.branches:
            return self.branches[filial]
        # Регистронезависимое
        lower_map = {k.lower(): v for k, v in self.branches.items()}
        return lower_map.get(filial.lower())

    @staticmethod
    def _age_from_dob(dob: Optional[str]) -> Optional[int]:
        """'2017-04-15' → 8 (текущий возраст)."""
        if not dob:
            return None
        try:
            from datetime import date
            y, m, d = map(int, dob.split("-")[:3])
            today = date.today()
            age = today.year - y - ((today.month, today.day) < (m, d))
            return max(0, age)
        except (ValueError, IndexError):
            return None

    def find_by_phone(self, branch_id: int, phone: str) -> Optional[dict]:
        """Ищет клиента в CRM по телефону.

        Возвращает {parent_name, parent_phone, child_name, child_age}
        или None если не найден / dry-run.
        """
        if self.dry_run:
            return None

        phone_norm = WazzupClient.normalize_phone(phone)
        # AlfaCRM ищет по подстроке в телефоне — фильтр phone=число.
        try:
            data = self._post(branch_id, "customer/index", {"phone": phone_norm, "page": 0})
        except requests.RequestException as e:
            logger.exception("CRM lookup failed: %s", e)
            return None

        items = data.get("items", [])
        if not items:
            return None

        c = items[0]
        # AlfaCRM-поля: name (ученик), legal_name / parent / company_name — родитель.
        # Точные имена зависят от настроек CRM франчайзи KIBERone; пробуем стандартные.
        parent_name = (
            c.get("legal_name")
            or c.get("parent_name")
            or c.get("company_name")
            or ""
        )
        return {
            "parent_name": parent_name.strip() if parent_name else "",
            "parent_phone": phone_norm,
            "child_name": (c.get("name") or "").strip(),
            "child_age": self._age_from_dob(c.get("dob")),
            "crm_id": c.get("id"),
        }
