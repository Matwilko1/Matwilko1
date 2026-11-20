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
