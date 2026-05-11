from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo


BEIJING_TZ = ZoneInfo("Asia/Shanghai")


def beijing_now_text() -> str:
    return datetime.now(BEIJING_TZ).strftime("%Y-%m-%d %H:%M:%S")
