"""Home Assistant add-on glue: settings come from /data/options.json (the add-on's
Configuration tab), the ledger lives in /data/ledger.json and survives restarts."""

from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from . import config as cfgmod
from .sms import HomeAssistantNotifySender, Sender, SmsError, TwilioSender

DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
SETTING_KEYS = ["payee", "payment_details", "currency", "message_template", "min_amount"]
LOG_LIMIT = 100


def data_dir() -> Path:
    return Path(os.environ.get("COFFEE_DATA_DIR", "/data"))


class Store:
    """Thread-safe access to options + ledger."""

    def __init__(self, directory: Path | None = None):
        self.dir = directory or data_dir()
        self.lock = threading.RLock()

    # --- files -------------------------------------------------------------
    @property
    def options_path(self) -> Path:
        return self.dir / "options.json"

    @property
    def ledger_path(self) -> Path:
        return self.dir / "ledger.json"

    def options(self) -> dict:
        try:
            return json.loads(self.options_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}

    def _ledger(self) -> dict:
        try:
            data = json.loads(self.ledger_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            data = {}
        data.setdefault("coworkers", [])
        data.setdefault("log", [])
        data.setdefault("last_scheduled_run", None)
        return data

    def _write(self, data: dict) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        tmp = self.ledger_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.ledger_path)

    # --- public API --------------------------------------------------------
    def config(self) -> cfgmod.Config:
        with self.lock:
            opts = self.options()
            settings = {k: opts[k] for k in SETTING_KEYS if opts.get(k) not in (None, "")}
            settings.setdefault("payee", "Coffee Fund")
            return cfgmod.from_dict({**settings, "coworkers": self._ledger()["coworkers"]})

    def save_coworkers(self, cfg: cfgmod.Config, log: str | None = None) -> None:
        with self.lock:
            data = self._ledger()
            data["coworkers"] = [asdict(c) for c in cfg.coworkers]
            self._write(data)
            if log:
                self.log(log)

    def log(self, text: str) -> None:
        with self.lock:
            data = self._ledger()
            data["log"] = ([{"time": datetime.now().isoformat(timespec="seconds"),
                             "text": text}] + data["log"])[:LOG_LIMIT]
            self._write(data)

    def history(self) -> list[dict]:
        return self._ledger()["log"]

    def last_scheduled_run(self) -> str | None:
        return self._ledger()["last_scheduled_run"]

    def set_last_scheduled_run(self, day: str) -> None:
        with self.lock:
            data = self._ledger()
            data["last_scheduled_run"] = day
            self._write(data)

    def sender(self) -> Sender:
        opts = self.options()
        if opts.get("sms_provider", "twilio") == "homeassistant":
            return HomeAssistantNotifySender(opts.get("notify_service", ""))
        sid, token, frm = (opts.get("twilio_account_sid"), opts.get("twilio_auth_token"),
                           opts.get("twilio_from"))
        if not (sid and token and frm):
            raise SmsError("Twilio is selected but account SID, auth token or "
                           "'from' number is missing in the add-on configuration")
        return TwilioSender(sid, token, frm)
