"""Small web UI shown in the Home Assistant sidebar (via ingress)."""

from __future__ import annotations

import html
import os
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import config as cfgmod
from .addon import Store
from .reminders import remind_and_log

# Only Home Assistant's ingress proxy (and localhost for testing) may talk to us;
# Home Assistant itself handles login.
ALLOWED = set(os.environ.get("COFFEE_ALLOWED_CLIENTS", "172.30.32.2,127.0.0.1").split(","))

CSS = """
:root{--bg:#fafafa;--fg:#1c1c1c;--card:#fff;--muted:#6b6b6b;--line:#e3e3e3;--accent:#03a9f4;--owe:#c62828;--ok:#2e7d32}
@media (prefers-color-scheme:dark){:root{--bg:#111;--fg:#e6e6e6;--card:#1c1c1c;--muted:#9a9a9a;--line:#333;--owe:#ef9a9a;--ok:#a5d6a7}}
*{box-sizing:border-box}body{margin:0;font:15px/1.45 system-ui,sans-serif;background:var(--bg);color:var(--fg)}
main{max-width:960px;margin:0 auto;padding:16px}
h1{font-size:1.4rem;margin:.2rem 0 1rem}h2{font-size:1.05rem;margin:0 0 .6rem}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px;margin-bottom:14px}
table{width:100%;border-collapse:collapse}td,th{padding:8px 6px;border-bottom:1px solid var(--line);text-align:left;vertical-align:middle}
th{color:var(--muted);font-weight:500;font-size:.85rem}
.owes{white-space:nowrap;font-variant-numeric:tabular-nums;font-weight:600;color:var(--owe)}.zero{color:var(--ok)}
.inactive td{opacity:.5}
form{display:inline-flex;gap:4px;align-items:center;margin:2px 0}
input{font:inherit;padding:5px 7px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--fg)}
input[type=number]{width:6.5em}
button{font:inherit;padding:5px 10px;border-radius:6px;border:1px solid var(--line);background:var(--card);color:var(--fg);cursor:pointer}
button.primary{background:var(--accent);border-color:var(--accent);color:#fff}
button.danger{color:var(--owe)}
.msg{padding:10px 14px;border-radius:8px;background:color-mix(in srgb,var(--accent) 15%,transparent);margin-bottom:14px}
.muted{color:var(--muted);font-size:.85rem}ul{margin:0;padding-left:1.2em}
.row{display:flex;flex-wrap:wrap;gap:10px;align-items:center}
.table-wrap{overflow-x:auto}
"""


def money(cfg, amount):
    cls = "owes" if amount >= cfg.min_amount else "owes zero"
    return f'<span class="{cls}">{html.escape(cfg.format_amount(amount))}</span>'


def form(action, fields="", button="", cls="", confirm=None):
    onsubmit = f' onsubmit="return confirm({html.escape(repr(confirm))})"' if confirm else ""
    return (f'<form method="post" action="{action}"{onsubmit}>{fields}'
            f'<button class="{cls}">{button}</button></form>')


def hidden(name, value):
    return f'<input type="hidden" name="{name}" value="{html.escape(str(value))}">'


def render_page(store: Store, msg: str = "", preview: list[tuple[str, str]] | None = None) -> str:
    e = html.escape
    try:
        cfg = store.config()
        error = ""
    except cfgmod.ConfigError as exc:
        cfg, error = None, str(exc)

    parts = ['<main><h1>☕ Coffee reminders</h1>']
    if msg:
        parts.append(f'<div class="msg">{e(msg)}</div>')
    if error:
        parts.append(f'<div class="msg">Configuration problem: {e(error)}</div></main>')
        return page("".join(parts))

    opts = store.options()
    total = sum(c.owes for c in cfg.coworkers)
    rows = []
    for c in cfg.coworkers:
        n = hidden("name", c.name)
        actions = [
            form("paid", n, "Paid in full", "primary") if c.owes > 0 else "",
            form("paid", n + '<input type="number" step="0.01" min="0.01" name="amount" placeholder="amount" required>', "Paid"),
            form("charge", n + '<input type="number" step="0.01" name="amount" placeholder="amount" required>', "Charge"),
            form("remind", n, "Text now") if c.active and c.owes >= cfg.min_amount else "",
            form("toggle", n, "Pause" if c.active else "Resume"),
            form("remove", n, "Remove", "danger", confirm=f"Remove {c.name}?"),
        ]
        rows.append(
            f'<tr class="{"" if c.active else "inactive"}"><td>{e(c.name)}</td>'
            f'<td class="muted">{e(c.phone)}</td><td>{money(cfg, c.owes)}</td>'
            f'<td>{"".join(actions)}</td></tr>')
    if not rows:
        rows.append('<tr><td colspan="4" class="muted">No coworkers yet - add one below.</td></tr>')

    days = ", ".join(opts.get("reminder_days", ["mon"]))
    schedule = (f"Automatic reminders: <b>{e(days)}</b> at <b>{e(opts.get('reminder_time', '09:00'))}</b>"
                if opts.get("schedule_enabled", True) else "Automatic reminders are <b>off</b>")
    provider = opts.get("sms_provider", "twilio")
    provider_txt = (f"notify.{opts.get('notify_service', '').removeprefix('notify.')}"
                    if provider == "homeassistant" else "Twilio")

    parts.append(f'''
<div class="card"><h2>Who owes what</h2><div class="table-wrap"><table>
<tr><th>Name</th><th>Phone</th><th>Owes</th><th></th></tr>{"".join(rows)}
<tr><th colspan="2">Total</th><th>{money(cfg, total)}</th><th></th></tr></table></div></div>

<div class="card"><h2>Send reminders</h2><div class="row">
{form("remind", "", "Text everyone who owes", "primary", confirm="Send SMS reminders now?")}
{form("preview", "", "Preview messages")}
</div><p class="muted">{schedule} · sending via {e(provider_txt)} · change this on the add-on's Configuration tab.</p>''')
    if preview is not None:
        items = "".join(f"<li><b>{e(p)}</b>: {e(m)}</li>" for p, m in preview) or "<li>Nobody owes anything.</li>"
        parts.append(f"<h2>Preview</h2><ul>{items}</ul>")
    parts.append("</div>")

    parts.append(f'''
<div class="card"><h2>Charge everyone</h2>
{form("charge", '<input type="number" step="0.01" name="amount" placeholder="amount" required>', "Add to all active")}
<p class="muted">E.g. the monthly coffee fee. Paused people are skipped.</p></div>

<div class="card"><h2>Add coworker</h2>
{form("add", '<input name="name" placeholder="Name" required>'
             '<input name="phone" placeholder="+48123456789" required>'
             '<input type="number" step="0.01" name="owes" placeholder="owes" value="0">', "Add", "primary")}
</div>''')

    log = "".join(f'<li><span class="muted">{e(x["time"].replace("T", " "))}</span> {e(x["text"])}</li>'
                  for x in store.history()[:30]) or '<li class="muted">Nothing yet.</li>'
    parts.append(f'<div class="card"><h2>Activity</h2><ul>{log}</ul></div></main>')
    return page("".join(parts))


def page(body: str) -> str:
    return (f'<!doctype html><html><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>Coffee reminders</title><style>{CSS}</style></head><body>{body}</body></html>')


def handle_action(store: Store, action: str, form_data: dict[str, str]):
    """Apply a form action. Returns (message, preview_or_None)."""
    if action == "remind":
        name = form_data.get("name")
        return remind_and_log(store, [name] if name else None), None
    if action == "preview":
        cfg = store.config()
        return "", [(c.name, cfg.render(c)) for c in cfg.debtors()]

    with store.lock:
        cfg = store.config()

        def amount(key="amount"):
            try:
                return round(float(form_data[key]), 2)
            except (KeyError, ValueError):
                raise cfgmod.ConfigError("please enter a valid amount")

        if action == "add":
            name = form_data.get("name", "").strip()
            if any(c.name.lower() == name.lower() for c in cfg.coworkers):
                raise cfgmod.ConfigError(f"{name} already exists")
            c = cfgmod.Coworker(name, form_data.get("phone", ""), amount("owes") if form_data.get("owes") else 0)
            cfg.coworkers.append(c)
            text = f"Added {c.name}"
        elif action == "charge" and form_data.get("name"):
            c = cfg.find(form_data["name"])
            c.owes = round(c.owes + amount(), 2)
            text = f"Charged {c.name} {cfg.format_amount(amount())}, now owes {cfg.format_amount(c.owes)}"
        elif action == "charge":
            a = amount()
            people = [c for c in cfg.coworkers if c.active]
            for c in people:
                c.owes = round(c.owes + a, 2)
            text = f"Charged {len(people)} people {cfg.format_amount(a)} each"
        elif action == "paid":
            c = cfg.find(form_data.get("name", ""))
            a = amount() if form_data.get("amount") else c.owes
            c.owes = round(c.owes - a, 2)
            text = f"{c.name} paid {cfg.format_amount(a)}, now owes {cfg.format_amount(c.owes)}"
        elif action == "toggle":
            c = cfg.find(form_data.get("name", ""))
            c.active = not c.active
            text = f"{'Resumed' if c.active else 'Paused'} reminders for {c.name}"
        elif action == "remove":
            c = cfg.find(form_data.get("name", ""))
            cfg.coworkers.remove(c)
            text = f"Removed {c.name}"
        else:
            raise cfgmod.ConfigError(f"unknown action {action!r}")
        store.save_coworkers(cfg, log=text)
        return text, None


class Handler(BaseHTTPRequestHandler):
    store: Store

    def _allowed(self) -> bool:
        if self.client_address[0] in ALLOWED:
            return True
        self.send_error(403)
        return False

    def _send_html(self, body: str, status: int = 200) -> None:
        data = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if not self._allowed():
            return
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
        self._send_html(render_page(self.store, query.get("msg", [""])[0]))

    def do_POST(self):
        if not self._allowed():
            return
        action = urllib.parse.urlsplit(self.path).path.rstrip("/").rsplit("/", 1)[-1]
        length = int(self.headers.get("Content-Length") or 0)
        fields = {k: v[0] for k, v in urllib.parse.parse_qs(self.rfile.read(length).decode()).items()}
        try:
            msg, preview = handle_action(self.store, action, fields)
        except cfgmod.ConfigError as exc:
            msg, preview = f"Error: {exc}", None
        if preview is not None:
            self._send_html(render_page(self.store, msg, preview))
            return
        # Relative redirect keeps us inside the ingress path.
        self.send_response(303)
        self.send_header("Location", "./?" + urllib.parse.urlencode({"msg": msg}))
        self.end_headers()

    def log_message(self, fmt, *args):
        pass


def serve(store: Store, host: str = "0.0.0.0", port: int = 8099) -> None:
    handler = type("BoundHandler", (Handler,), {"store": store})
    server = ThreadingHTTPServer((host, port), handler)
    print(f"Coffee reminders UI listening on {host}:{port}", flush=True)
    server.serve_forever()
