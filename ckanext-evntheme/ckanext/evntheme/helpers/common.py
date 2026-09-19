"""Small utilities shared by the helper modules."""
from __future__ import annotations

import zlib
from typing import Any

from ckanext.evntheme.vocab import TONES


def field(obj: dict[str, Any] | None, key: str) -> Any:
    """Read a custom field from a dataset/org dict: top-level first (ckanext-scheming), then `extras`."""
    if not obj:
        return None
    value = obj.get(key)
    if value not in (None, ""):
        return value
    for extra in obj.get("extras") or []:
        if extra.get("key") == key:
            return extra.get("value")
    return None


def truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on", "có"}


def as_float(value: Any) -> float | None:
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


def tone_for(name: str) -> str:
    """Stable colour for a name (crc32, not hash(): Python salts str hashes per process)."""
    return TONES[zlib.crc32((name or "").encode("utf-8")) % len(TONES)]


def initials(title: str, max_letters: int = 4) -> str:
    """'Ban Quản lý đấu thầu' -> 'BQLĐ'. Fallback when an org has no `abbreviation` extra."""
    words = [w for w in (title or "").split() if w[:1].isalnum()]
    return "".join(w[0] for w in words[:max_letters]).upper() or "?"
