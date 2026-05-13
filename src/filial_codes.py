"""Карта филиалов KIBERone → код для серийников паспортов.

Серийник имеет формат `KBR-{YEAR}-{CODE}-{NNNN}` (пример: KBR-2026-NCK-0042).
Коды трёхбуквенные, латиница, на 7 текущих филиалов франчайзи + общий fallback.
Принимаем кириллицу и латиницу в названии филиала — нормализуем при поиске.
"""

from __future__ import annotations

from slugify import slugify


# slug → код. slug формируется через slugify(name, lowercase=True).
FILIAL_CODES: dict[str, str] = {
    "naberezhnye-chelny":   "NCK",
    "chelny":               "NCK",
    "naberezhnyye-chelny":  "NCK",  # альтернативная транслитерация
    "kazan":                "KZN",
    "nizhnekamsk":          "NKM",
    "yelabuga":             "ELB",
    "elabuga":              "ELB",
    "krasnodar":            "KRD",
    "surgut":               "SGT",
    "perm":                 "PRM",
}

DEFAULT_CODE = "GEN"


def filial_to_code(filial: str) -> str:
    if not filial:
        return DEFAULT_CODE
    slug = slugify(filial, lowercase=True)
    if slug in FILIAL_CODES:
        return FILIAL_CODES[slug]
    # Фоллбэк: первые 3 буквы латиницей в верхнем регистре
    return slug[:3].upper() or DEFAULT_CODE
