"""Shared 'send reminders and record what happened' logic."""

from __future__ import annotations

from .addon import Store
from .config import ConfigError
from .sms import Sender, SmsError


def send_reminders(cfg, sender: Sender, only: list[str] | None = None) -> list[tuple[str, bool, str]]:
    """Text every active coworker who owes money.
    Returns (name, ok, detail) per attempted message."""
    targets = cfg.debtors()
    if only:
        wanted = {n.lower() for n in only}
        targets = [c for c in targets if c.name.lower() in wanted]
    results = []
    for c in targets:
        try:
            ref = sender.send(c.phone, cfg.render(c))
            results.append((c.name, True, f"{cfg.format_amount(c.owes)} {ref}".strip()))
        except (SmsError, ConfigError) as exc:
            results.append((c.name, False, str(exc)))
    return results


def remind_and_log(store: Store, only: list[str] | None = None, reason: str = "manual") -> str:
    try:
        results = send_reminders(store.config(), store.sender(), only)
    except (SmsError, ConfigError) as exc:
        summary = f"Reminders ({reason}) not sent: {exc}"
        store.log(summary)
        return summary
    if not results:
        summary = f"Reminders ({reason}): nobody owes anything."
    else:
        parts = [f"{n} {'✓' if ok else '✗ ' + d}" for n, ok, d in results]
        summary = f"Reminders ({reason}): " + ", ".join(parts)
    store.log(summary)
    return summary
