"""Loading, validating and saving the coffee ledger (config.json)."""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

E164 = re.compile(r"^\+[1-9]\d{6,14}$")

DEFAULT_TEMPLATE = (
    "Hi {name}! Friendly coffee reminder: you owe {amount}. "
    "Please pay {payee} ({payment_details}). Thanks!"
)


class ConfigError(ValueError):
    pass


@dataclass
class Coworker:
    name: str
    phone: str
    owes: float = 0.0
    active: bool = True

    def __post_init__(self) -> None:
        self.name = self.name.strip()
        self.phone = re.sub(r"[\s\-()]", "", self.phone)
        if not self.name:
            raise ConfigError("coworker name must not be empty")
        if not E164.match(self.phone):
            raise ConfigError(
                f"{self.name}: phone {self.phone!r} must be in international "
                "format, e.g. +48123456789"
            )
        self.owes = round(float(self.owes), 2)


@dataclass
class Config:
    payee: str
    payment_details: str = ""
    currency: str = "€"
    message_template: str = DEFAULT_TEMPLATE
    min_amount: float = 0.01
    coworkers: list[Coworker] = field(default_factory=list)

    def find(self, name: str) -> Coworker:
        matches = [c for c in self.coworkers if c.name.lower() == name.lower()]
        if not matches:
            raise ConfigError(f"no coworker named {name!r}")
        return matches[0]

    def format_amount(self, amount: float) -> str:
        return f"{amount:.2f} {self.currency}".strip()

    def render(self, coworker: Coworker) -> str:
        try:
            return self.message_template.format(
                name=coworker.name,
                amount=self.format_amount(coworker.owes),
                payee=self.payee,
                payment_details=self.payment_details,
            )
        except (KeyError, IndexError) as exc:
            raise ConfigError(f"message_template has an unknown placeholder: {exc}")

    def debtors(self) -> list[Coworker]:
        return [c for c in self.coworkers if c.active and c.owes >= self.min_amount]


def default_path() -> Path:
    return Path(os.environ.get("COFFEE_CONFIG", "config.json"))


def from_dict(data: dict) -> Config:
    try:
        people = [Coworker(**c) for c in data.get("coworkers", [])]
        cfg = Config(**{**data, "coworkers": people})
    except TypeError as exc:
        raise ConfigError(f"invalid config: {exc}") from exc
    names = [c.name.lower() for c in people]
    if len(names) != len(set(names)):
        raise ConfigError("coworker names must be unique")
    return cfg


def load(path: Path | None = None) -> Config:
    path = path or default_path()
    if not path.exists():
        raise ConfigError(
            f"{path} not found - copy config.example.json to {path} and edit it"
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{path} is not valid JSON: {exc}") from exc
    return from_dict(data)


def save(cfg: Config, path: Path | None = None) -> None:
    path = path or default_path()
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(asdict(cfg), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    tmp.replace(path)
