"""Command line interface: python -m coffee_reminders <command>."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import config as cfgmod
from .reminders import send_reminders as _send
from .sms import ConsoleSender, Sender, SmsError, TwilioSender


def send_reminders(cfg: cfgmod.Config, sender: Sender, only: list[str] | None = None) -> int:
    """Text everyone who owes money. Returns the number of failures."""
    results = _send(cfg, sender, only)
    if not results:
        print("Nobody owes anything - no reminders sent.")
    for name, ok, detail in results:
        if ok:
            print(f"Reminded {name} ({detail})")
        else:
            print(f"FAILED to remind {name}: {detail}", file=sys.stderr)
    return sum(1 for _, ok, _ in results if not ok)


def cmd_list(cfg, args):
    total = 0.0
    for c in cfg.coworkers:
        flag = "" if c.active else "  (inactive)"
        print(f"{c.name:<20} {c.phone:<16} {cfg.format_amount(c.owes):>12}{flag}")
        total += c.owes
    print(f"{'TOTAL':<37} {cfg.format_amount(total):>12}")


def cmd_remind(cfg, args):
    sender = ConsoleSender() if args.dry_run else TwilioSender.from_env()
    return 1 if send_reminders(cfg, sender, args.only) else 0


def cmd_charge(cfg, args):
    people = [cfg.find(n) for n in args.names] if args.names else [
        c for c in cfg.coworkers if c.active
    ]
    for c in people:
        c.owes = round(c.owes + args.amount, 2)
        print(f"{c.name} now owes {cfg.format_amount(c.owes)}")
    cfgmod.save(cfg, args.config)


def cmd_paid(cfg, args):
    c = cfg.find(args.name)
    amount = c.owes if args.amount is None else args.amount
    c.owes = round(c.owes - amount, 2)
    print(f"{c.name} paid {cfg.format_amount(amount)}, now owes {cfg.format_amount(c.owes)}")
    cfgmod.save(cfg, args.config)


def cmd_add(cfg, args):
    if any(c.name.lower() == args.name.lower() for c in cfg.coworkers):
        raise cfgmod.ConfigError(f"{args.name} already exists")
    cfg.coworkers.append(cfgmod.Coworker(args.name, args.phone, args.owes))
    print(f"Added {args.name}")
    cfgmod.save(cfg, args.config)


def cmd_remove(cfg, args):
    cfg.coworkers.remove(cfg.find(args.name))
    print(f"Removed {args.name}")
    cfgmod.save(cfg, args.config)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="coffee_reminders", description=__doc__)
    p.add_argument("-c", "--config", type=Path, default=None,
                   help="path to config.json (default: $COFFEE_CONFIG or ./config.json)")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="show who owes what").set_defaults(func=cmd_list)

    r = sub.add_parser("remind", help="text everyone who owes money")
    r.add_argument("--dry-run", action="store_true", help="print messages instead of sending")
    r.add_argument("--only", nargs="+", metavar="NAME", help="remind only these people")
    r.set_defaults(func=cmd_remind)

    ch = sub.add_parser("charge", help="add an amount to people's balance (default: all active)")
    ch.add_argument("amount", type=float)
    ch.add_argument("names", nargs="*")
    ch.set_defaults(func=cmd_charge)

    pd = sub.add_parser("paid", help="record a payment (default: the full balance)")
    pd.add_argument("name")
    pd.add_argument("amount", type=float, nargs="?")
    pd.set_defaults(func=cmd_paid)

    a = sub.add_parser("add", help="add a coworker")
    a.add_argument("name")
    a.add_argument("phone", help="international format, e.g. +48123456789")
    a.add_argument("--owes", type=float, default=0.0)
    a.set_defaults(func=cmd_add)

    rm = sub.add_parser("remove", help="remove a coworker")
    rm.add_argument("name")
    rm.set_defaults(func=cmd_remove)
    sub.add_parser("serve", help="run the Home Assistant add-on (web UI + scheduler)")
    return p


def serve() -> int:
    from . import scheduler, web
    from .addon import Store

    store = Store()
    store.log("Add-on started")
    scheduler.start(store)
    web.serve(store)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "serve":
        return serve()
    try:
        cfg = cfgmod.load(args.config)
        return args.func(cfg, args) or 0
    except (cfgmod.ConfigError, SmsError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
