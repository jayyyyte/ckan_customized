"""Locale-aware formatting (Vietnamese: 1.204 and 99,97%).

Kept free of CKAN request state except for the current language, so the functions
are easy to unit-test by passing `locale` explicitly.
"""
from __future__ import annotations

import datetime as dt
from typing import Any

from babel.dates import format_date, format_timedelta
from babel.numbers import format_decimal
from dateutil.parser import isoparse

import ckan.plugins.toolkit as tk


def current_locale() -> str:
    try:
        return tk.h.lang() or "en"
    except (RuntimeError, AttributeError):  # outside a request
        return "en"


def number(value: Any, decimals: int = 0, locale: str | None = None) -> str:
    """1204 -> '1.204' (vi); 99.974 with decimals=2 -> '99,97'. Non-numbers come back as-is."""
    try:
        value = float(value)
    except (TypeError, ValueError):
        return "" if value is None else str(value)
    pattern = "#,##0" + ("." + "#" * decimals if decimals else "")
    return format_decimal(round(value, decimals), format=pattern, locale=locale or current_locale())


def percent(value: Any, decimals: int = 1, locale: str | None = None) -> str:
    """98.4 -> '98,4%'; 100 -> '100%'. `value` is already in percent."""
    text = number(value, decimals, locale)
    return f"{text}%" if text else ""


def parse_datetime(value: Any) -> dt.datetime | None:
    """Parse CKAN/Solr timestamps ('2026-09-19T10:00:00.123456', '...00.1Z') into aware UTC datetimes.

    dateutil rather than datetime.fromisoformat: Solr trims trailing zeros of the
    milliseconds, which Python 3.10 (the ckan-base image) cannot parse.
    """
    if isinstance(value, dt.datetime):
        parsed = value
    elif isinstance(value, str) and value:
        try:
            parsed = isoparse(value)
        except ValueError:
            return None
    else:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)


def age(value: Any, now: dt.datetime | None = None) -> dt.timedelta | None:
    parsed = parse_datetime(value)
    if parsed is None:
        return None
    return (now or dt.datetime.now(dt.timezone.utc)) - parsed


# Babel's "short" Vietnamese date is "1/7/26"; official documents write "01/07/2026".
DATE_PATTERNS = {"vi": "dd/MM/y"}


def date(value: dt.date | None, locale: str | None = None) -> str:
    """Localised date: '01/07/2026' (vi), 'Jul 1, 2026' (en). Accepts date or datetime
    (core render_datetime only takes datetime)."""
    if value is None:
        return ""
    locale = locale or current_locale()
    return format_date(value, format=DATE_PATTERNS.get(locale.split("_")[0], "medium"), locale=locale)


def duration(delta: dt.timedelta, locale: str | None = None) -> str:
    """timedelta -> '5 phút', '2 giờ', '3 ngày' (no direction)."""
    return format_timedelta(delta, granularity="minute", threshold=1, locale=locale or current_locale())
