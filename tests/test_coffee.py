import json
import shutil
from pathlib import Path

import pytest

from coffee_reminders import config as cfgmod
from coffee_reminders.cli import main, send_reminders
from coffee_reminders.sms import ConsoleSender, SmsError, TwilioSender

EXAMPLE = Path(__file__).parent.parent / "coffee-reminders" / "config.example.json"


@pytest.fixture
def cfg_path(tmp_path):
    p = tmp_path / "config.json"
    shutil.copy(EXAMPLE, p)
    return p


def test_only_debtors_are_reminded(cfg_path):
    cfg = cfgmod.load(cfg_path)
    sender = ConsoleSender()
    assert send_reminders(cfg, sender) == 0
    assert len(sender.sent) == 1
    to, body = sender.sent[0]
    assert to == "+48500000001"
    assert "Anna" in body and "25.00 PLN" in body


def test_inactive_people_are_skipped(cfg_path):
    cfg = cfgmod.load(cfg_path)
    cfg.find("anna").active = False
    sender = ConsoleSender()
    send_reminders(cfg, sender)
    assert sender.sent == []


def test_charge_and_paid_update_ledger(cfg_path):
    assert main(["-c", str(cfg_path), "charge", "10"]) == 0
    cfg = cfgmod.load(cfg_path)
    assert cfg.find("Anna").owes == 35.0
    assert cfg.find("Piotr").owes == 10.0

    assert main(["-c", str(cfg_path), "paid", "Anna", "5"]) == 0
    assert main(["-c", str(cfg_path), "paid", "Piotr"]) == 0
    cfg = cfgmod.load(cfg_path)
    assert cfg.find("Anna").owes == 30.0
    assert cfg.find("Piotr").owes == 0.0


def test_add_and_remove(cfg_path):
    assert main(["-c", str(cfg_path), "add", "Ola", "+48 500-000-003", "--owes", "4.5"]) == 0
    cfg = cfgmod.load(cfg_path)
    assert cfg.find("Ola").phone == "+48500000003"
    assert main(["-c", str(cfg_path), "remove", "Ola"]) == 0
    with pytest.raises(cfgmod.ConfigError):
        cfgmod.load(cfg_path).find("Ola")


def test_bad_phone_rejected(cfg_path):
    assert main(["-c", str(cfg_path), "add", "Bob", "500000003"]) == 2


def test_duplicate_names_rejected():
    data = json.loads(EXAMPLE.read_text())
    data["coworkers"].append(dict(data["coworkers"][0]))
    with pytest.raises(cfgmod.ConfigError):
        cfgmod.from_dict(data)


def test_dry_run_cli(cfg_path, capsys):
    assert main(["-c", str(cfg_path), "remind", "--dry-run"]) == 0
    assert "[dry-run] to +48500000001" in capsys.readouterr().out


def test_failures_are_counted(cfg_path):
    class Broken:
        def send(self, to, body):
            raise SmsError("boom")

    cfg = cfgmod.load(cfg_path)
    cfg.find("Piotr").owes = 3
    assert send_reminders(cfg, Broken()) == 2


def test_twilio_requires_env(monkeypatch):
    for v in ["TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM",
              "TWILIO_MESSAGING_SERVICE_SID"]:
        monkeypatch.delenv(v, raising=False)
    with pytest.raises(SmsError, match="TWILIO_ACCOUNT_SID"):
        TwilioSender.from_env()


def test_twilio_request(monkeypatch):
    captured = {}

    class Resp:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def read(self): return b'{"sid": "SM123"}'

    def fake_urlopen(req, timeout):
        captured["url"] = req.full_url
        captured["data"] = req.data.decode()
        captured["auth"] = req.headers["Authorization"]
        return Resp()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    sid = TwilioSender("AC1", "tok", "+15550000000").send("+48500000001", "hi there")
    assert sid == "SM123"
    assert captured["url"].endswith("/Accounts/AC1/Messages.json")
    assert "To=%2B48500000001" in captured["data"] and "From=%2B15550000000" in captured["data"]
    assert captured["auth"].startswith("Basic ")
