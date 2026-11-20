"""SMS senders. Twilio is used for real messages; Console for dry runs."""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Protocol


class SmsError(RuntimeError):
    pass


class Sender(Protocol):
    def send(self, to: str, body: str) -> str: ...


class ConsoleSender:
    """Prints messages instead of sending them."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    def send(self, to: str, body: str) -> str:
        self.sent.append((to, body))
        print(f"[dry-run] to {to}: {body}")
        return "dry-run"


class TwilioSender:
    """Sends SMS through the Twilio REST API using only the standard library."""

    API = "https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"

    def __init__(self, account_sid: str, auth_token: str, sender: str, timeout: float = 15):
        self.account_sid = account_sid
        self.auth_token = auth_token
        self.sender = sender  # a phone number (+...) or a Messaging Service SID (MG...)
        self.timeout = timeout

    @classmethod
    def from_env(cls) -> "TwilioSender":
        sid = os.environ.get("TWILIO_ACCOUNT_SID")
        token = os.environ.get("TWILIO_AUTH_TOKEN")
        sender = os.environ.get("TWILIO_FROM") or os.environ.get("TWILIO_MESSAGING_SERVICE_SID")
        missing = [
            n for n, v in [("TWILIO_ACCOUNT_SID", sid), ("TWILIO_AUTH_TOKEN", token),
                           ("TWILIO_FROM", sender)] if not v
        ]
        if missing:
            raise SmsError("missing environment variables: " + ", ".join(missing))
        return cls(sid, token, sender)

    def send(self, to: str, body: str) -> str:
        fields = {"To": to, "Body": body}
        if self.sender.startswith("MG"):
            fields["MessagingServiceSid"] = self.sender
        else:
            fields["From"] = self.sender
        auth = base64.b64encode(f"{self.account_sid}:{self.auth_token}".encode()).decode()
        req = urllib.request.Request(
            self.API.format(sid=self.account_sid),
            data=urllib.parse.urlencode(fields).encode(),
            headers={"Authorization": f"Basic {auth}"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.load(resp).get("sid", "")
        except urllib.error.HTTPError as exc:
            try:
                detail = json.load(exc).get("message", "")
            except Exception:
                detail = ""
            raise SmsError(f"Twilio HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise SmsError(f"could not reach Twilio: {exc.reason}") from exc


class HomeAssistantNotifySender:
    """Sends through a Home Assistant notify service (e.g. a GSM modem or Twilio SMS
    integration) using the Supervisor API, available inside an add-on."""

    def __init__(self, service: str, token: str | None = None,
                 base_url: str = "http://supervisor/core/api", timeout: float = 30):
        service = service.strip()
        if service.startswith("notify."):
            service = service[len("notify."):]
        if not service:
            raise SmsError("notify_service is not set in the add-on configuration")
        self.service = service
        self.token = token or os.environ.get("SUPERVISOR_TOKEN", "")
        if not self.token:
            raise SmsError("SUPERVISOR_TOKEN missing - is this running as an add-on?")
        self.base_url = base_url
        self.timeout = timeout

    def send(self, to: str, body: str) -> str:
        req = urllib.request.Request(
            f"{self.base_url}/services/notify/{self.service}",
            data=json.dumps({"message": body, "target": [to]}).encode(),
            headers={"Authorization": f"Bearer {self.token}",
                     "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout):
                return f"via notify.{self.service}"
        except urllib.error.HTTPError as exc:
            raise SmsError(f"Home Assistant HTTP {exc.code}: {exc.read()[:200]!r}") from exc
        except urllib.error.URLError as exc:
            raise SmsError(f"could not reach Home Assistant: {exc.reason}") from exc
