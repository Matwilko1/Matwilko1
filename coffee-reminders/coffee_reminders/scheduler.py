"""Background thread that sends reminders on the configured days and time."""

from __future__ import annotations

import threading
import time
from datetime import datetime

from .addon import DAYS, Store
from .reminders import remind_and_log


def is_due(now: datetime, days: list[str], at: str, last_run: str | None) -> bool:
    if DAYS[now.weekday()] not in days:
        return False
    hour, minute = (int(x) for x in at.split(":"))
    if (now.hour, now.minute) < (hour, minute):
        return False
    return last_run != now.date().isoformat()


def tick(store: Store, now: datetime | None = None) -> bool:
    now = now or datetime.now()
    opts = store.options()
    if not opts.get("schedule_enabled", True):
        return False
    if not is_due(now, opts.get("reminder_days", ["mon"]),
                  opts.get("reminder_time", "09:00"), store.last_scheduled_run()):
        return False
    # Mark first so a crash mid-send can't cause a flood of repeat texts.
    store.set_last_scheduled_run(now.date().isoformat())
    remind_and_log(store, reason="scheduled")
    return True


def start(store: Store, interval: float = 30) -> threading.Thread:
    def loop():
        while True:
            try:
                tick(store)
            except Exception as exc:  # keep the scheduler alive no matter what
                store.log(f"Scheduler error: {exc}")
            time.sleep(interval)

    t = threading.Thread(target=loop, name="coffee-scheduler", daemon=True)
    t.start()
    return t
