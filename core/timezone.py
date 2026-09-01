"""
Application timezone helpers.

All user-facing timestamps use US Pacific (America/Los_Angeles), including
when the app runs on UTC cloud hosts (e.g. Render).
"""

from __future__ import annotations

import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo

APP_TZ = ZoneInfo("America/Los_Angeles")
APP_TZ_NAME = "America/Los_Angeles"


def configure_app_timezone() -> None:
    """Set process timezone so naive datetime helpers also use Pacific."""
    os.environ["TZ"] = APP_TZ_NAME
    try:
        time.tzset()
    except AttributeError:
        pass


def now() -> datetime:
    return datetime.now(APP_TZ)


def now_iso(timespec: str = "seconds") -> str:
    return now().isoformat(timespec=timespec)


def now_formatted(fmt: str) -> str:
    return now().strftime(fmt)


def from_timestamp(ts: int | float) -> datetime:
    return datetime.fromtimestamp(ts, tz=APP_TZ)


def format_timestamp(ts: int | float, fmt: str = "%Y-%m-%d %H:%M") -> str:
    return from_timestamp(ts).strftime(fmt)


configure_app_timezone()
