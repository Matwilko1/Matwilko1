import json
import threading
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from http.server import ThreadingHTTPServer

import pytest

from coffee_reminders import scheduler, web
from coffee_reminders.addon import Store
from coffee_reminders.sms import ConsoleSender, HomeAssistantNotifySender, SmsError

OPTIONS = {
    "sms_provider": "twilio", "twilio_account_sid": "", "twilio_auth_token": "",
    "twilio_from": "", "notify_service": "", "payee": "Coffee Fund",
    "payment_details": "BLIK 500 000 000", "currency": "PLN",
    "message_template": "Hi {name}, you owe {amount} to {payee} ({payment_details})",
    "min_amount": 0.01, "schedule_enabled": True, "reminder_days": ["mon"],
    "reminder_time": "09:00",
}


@pytest.fixture
def store(tmp_path, monkeypatch):
    (tmp_path / "options.json").write_text(json.dumps(OPTIONS))
    s = Store(tmp_path)
    sender = ConsoleSender()
    monkeypatch.setattr(s, "sender", lambda: sender)
    s.test_sender = sender
    web.handle_action(s, "add", {"name": "Anna", "phone": "+48500000001", "owes": "12"})
    web.handle_action(s, "add", {"name": "Piotr", "phone": "+48500000002"})
    return s


def test_ledger_actions_persist(store):
    web.handle_action(store, "charge", {"amount": "5"})
    web.handle_action(store, "paid", {"name": "anna", "amount": "7"})
    web.handle_action(store, "toggle", {"name": "Piotr"})
    web.handle_action(store, "charge", {"amount": "5"})  # Piotr paused -> skipped
    cfg = Store(store.dir).config()
    assert cfg.find("Anna").owes == 15.0
    assert cfg.find("Piotr").owes == 5.0 and not cfg.find("Piotr").active
    web.handle_action(store, "paid", {"name": "Anna"})
    assert store.config().find("Anna").owes == 0
    assert "Anna paid" in store.history()[0]["text"]


def test_duplicate_and_bad_input(store):
    with pytest.raises(Exception, match="already exists"):
        web.handle_action(store, "add", {"name": "anna", "phone": "+48500000009"})
    with pytest.raises(Exception, match="valid amount"):
        web.handle_action(store, "charge", {"amount": "abc"})


def test_preview_and_remind(store):
    _, preview = web.handle_action(store, "preview", {})
    assert preview == [("Anna", "Hi Anna, you owe 12.00 PLN to Coffee Fund (BLIK 500 000 000)")]
    msg, _ = web.handle_action(store, "remind", {})
    assert "Anna ✓" in msg
    assert store.test_sender.sent == [("+48500000001", preview[0][1])]


def test_missing_twilio_settings_logged(tmp_path):
    (tmp_path / "options.json").write_text(json.dumps(OPTIONS))
    s = Store(tmp_path)
    web.handle_action(s, "add", {"name": "Anna", "phone": "+48500000001", "owes": "3"})
    msg, _ = web.handle_action(s, "remind", {})
    assert "not sent" in msg and "Twilio" in msg


@pytest.mark.parametrize("now,last,due", [
    (datetime(2026, 11, 23, 9, 0), None, True),          # Monday 09:00
    (datetime(2026, 11, 23, 8, 59), None, False),        # too early
    (datetime(2026, 11, 23, 15, 0), "2026-11-23", False),  # already ran today
    (datetime(2026, 11, 24, 9, 0), None, False),         # Tuesday
])
def test_is_due(now, last, due):
    assert scheduler.is_due(now, ["mon"], "09:00", last) is due


def test_tick_sends_once(store):
    monday = datetime(2026, 11, 23, 9, 1)
    assert scheduler.tick(store, monday) is True
    assert scheduler.tick(store, monday) is False
    assert len(store.test_sender.sent) == 1


def test_homeassistant_sender(monkeypatch):
    captured = {}

    class Resp:
        def __enter__(self): return self
        def __exit__(self, *a): pass

    def fake_urlopen(req, timeout):
        captured.update(url=req.full_url, body=json.loads(req.data),
                        auth=req.headers["Authorization"])
        return Resp()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    HomeAssistantNotifySender("notify.sms", token="t").send("+48500000001", "hi")
    assert captured["url"] == "http://supervisor/core/api/services/notify/sms"
    assert captured["body"] == {"message": "hi", "target": ["+48500000001"]}
    assert captured["auth"] == "Bearer t"
    with pytest.raises(SmsError):
        HomeAssistantNotifySender("", token="t")


def test_http_server_end_to_end(store):
    handler = type("H", (web.Handler,), {"store": store})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}/"
    try:
        page = urllib.request.urlopen(base).read().decode()
        assert "Anna" in page and "12.00 PLN" in page
        data = urllib.parse.urlencode({"name": "Anna"}).encode()
        page = urllib.request.urlopen(base + "paid", data=data).read().decode()  # follows 303
        assert "Anna paid 12.00 PLN" in page
        page = urllib.request.urlopen(base + "preview", data=b"").read().decode()
        assert "Nobody owes anything" in page
        # html is escaped
        web.handle_action(store, "add", {"name": "<b>x</b>", "phone": "+48500000003"})
        assert "<b>x</b>" not in urllib.request.urlopen(base).read().decode()
    finally:
        server.shutdown()


def test_rejects_non_ingress_clients(store, monkeypatch):
    monkeypatch.setattr(web, "ALLOWED", {"172.30.32.2"})
    handler = type("H", (web.Handler,), {"store": store})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(f"http://127.0.0.1:{server.server_address[1]}/")
        assert exc.value.code == 403
    finally:
        server.shutdown()
