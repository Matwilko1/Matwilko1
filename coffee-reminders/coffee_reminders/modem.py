"""Send SMS straight through a USB GSM/LTE modem with a SIM card, using AT
commands in PDU mode (works with any text length and with non-Latin characters).

Standard library only: the serial port is driven with termios."""

from __future__ import annotations

import os
import re
import select
import threading
import time

from .sms import SmsError

# GSM 03.38 default alphabet (index = septet value). \x1b (escape) is never emitted.
GSM7 = ("@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞ\x1bÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?"
        "¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà")
assert len(GSM7) == 128
GSM7_INDEX = {ch: i for i, ch in enumerate(GSM7) if ch != "\x1b"}

FINAL = re.compile(r"^(OK|ERROR|\+CMS ERROR:.*|\+CME ERROR:.*)$", re.M)


# --- PDU encoding ------------------------------------------------------------

def is_gsm7(text: str) -> bool:
    return all(ch in GSM7_INDEX for ch in text)


def _pack_bits(bits: list[int]) -> bytes:
    bits = bits + [0] * (-len(bits) % 8)
    return bytes(sum(bits[i + j] << j for j in range(8)) for i in range(0, len(bits), 8))


def _bits(value: int, width: int) -> list[int]:
    return [(value >> i) & 1 for i in range(width)]


def encode_gsm7(text: str, udh: bytes = b"") -> tuple[int, bytes]:
    """Returns (UDL in septets, user data bytes) with the UDH septet-aligned."""
    bits: list[int] = []
    for b in udh:
        bits += _bits(b, 8)
    bits += [0] * (-len(bits) % 7)  # fill bits
    header_septets = len(bits) // 7
    for ch in text:
        bits += _bits(GSM7_INDEX[ch], 7)
    return header_septets + len(text), _pack_bits(bits)


def _address(number: str) -> bytes:
    digits = number.lstrip("+")
    if not digits.isdigit():
        raise SmsError(f"invalid phone number {number!r}")
    kind = 0x91 if number.startswith("+") else 0x81
    padded = digits + ("F" if len(digits) % 2 else "")
    swapped = "".join(padded[i + 1] + padded[i] for i in range(0, len(padded), 2))
    return bytes([len(digits), kind]) + bytes.fromhex(swapped)


def split_parts(text: str) -> tuple[bool, list[str]]:
    """Returns (is_gsm7, parts) using single/concatenated SMS limits."""
    gsm = is_gsm7(text)
    if gsm:
        single, multi, units = 160, 153, list(text)
    else:
        utf16 = text.encode("utf-16-be")
        units = [utf16[i:i + 2] for i in range(0, len(utf16), 2)]
        single, multi = 70, 67
    if len(units) <= single:
        return gsm, [text]
    parts, i = [], 0
    while i < len(units):
        end = min(i + multi, len(units))
        if not gsm and end < len(units) and 0xD8 <= units[end - 1][0] <= 0xDB:
            end -= 1  # don't split a surrogate pair
        chunk = units[i:end]
        parts.append("".join(chunk) if gsm else b"".join(chunk).decode("utf-16-be"))
        i = end
    return gsm, parts


def build_pdus(number: str, text: str, ref: int = 0) -> list[tuple[int, str]]:
    """Returns [(TPDU length for AT+CMGS, full PDU hex)] - one per SMS part."""
    gsm, parts = split_parts(text)
    pdus = []
    for seq, part in enumerate(parts, 1):
        udh = b"" if len(parts) == 1 else bytes([5, 0, 3, ref & 0xFF, len(parts), seq])
        first = 0x01 | (0x40 if udh else 0)  # SMS-SUBMIT (+ UDH indicator)
        if gsm:
            udl, ud = encode_gsm7(part, udh)
        else:
            ud = udh + part.encode("utf-16-be")
            udl = len(ud)
        tpdu = (bytes([first, 0]) + _address(number) + bytes([0, 0 if gsm else 8, udl]) + ud)
        pdus.append((len(tpdu), "00" + tpdu.hex().upper()))  # 00 = use SIM's SMSC
    return pdus


# --- serial port + AT commands ---------------------------------------------

class SerialPort:
    def __init__(self, device: str, baud: int = 115200):
        import termios

        try:
            self.fd = os.open(device, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        except OSError as exc:
            raise SmsError(f"cannot open modem {device}: {exc.strerror}") from exc
        speed = getattr(termios, f"B{baud}", None)
        if speed is None:
            raise SmsError(f"unsupported baud rate {baud}")
        attrs = termios.tcgetattr(self.fd)
        attrs[0] = 0                                     # iflag: raw
        attrs[1] = 0                                     # oflag: raw
        attrs[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
        attrs[3] = 0                                     # lflag: no echo/canonical
        attrs[4] = attrs[5] = speed
        termios.tcsetattr(self.fd, termios.TCSANOW, attrs)
        termios.tcflush(self.fd, termios.TCIOFLUSH)

    def write(self, data: bytes) -> None:
        os.write(self.fd, data)

    def read(self, timeout: float) -> bytes:
        ready, _, _ = select.select([self.fd], [], [], timeout)
        return os.read(self.fd, 4096) if ready else b""

    def close(self) -> None:
        os.close(self.fd)


class Modem:
    def __init__(self, port):
        self.port = port

    def command(self, cmd: str, timeout: float = 10, prompt: bool = False) -> str:
        self.port.write(cmd.encode() + b"\r")
        return self.wait(timeout, prompt, cmd)

    def wait(self, timeout: float, prompt: bool = False, what: str = "") -> str:
        buf, deadline = "", time.monotonic() + timeout
        while time.monotonic() < deadline:
            buf += self.port.read(min(0.5, max(0.0, deadline - time.monotonic()))).decode(errors="replace")
            if prompt and ">" in buf:
                return buf
            m = FINAL.search(buf.replace("\r", ""))
            if m:
                if m.group(1) != "OK":
                    raise SmsError(f"modem said {m.group(1)!r} to {what}")
                return buf
        raise SmsError(f"modem did not answer {what or 'in time'}")

    def setup(self, pin: str = "") -> None:
        for _ in range(3):  # first AT may be eaten while the modem wakes up
            try:
                self.command("AT", timeout=3)
                break
            except SmsError:
                continue
        else:
            raise SmsError("no answer to AT - wrong device path? (try another ttyUSB port)")
        self.command("ATE0")
        status = self.command("AT+CPIN?")
        if "SIM PIN" in status:
            if not pin:
                raise SmsError("SIM card needs a PIN - set modem_pin in the configuration")
            self.command(f'AT+CPIN="{pin}"', timeout=15)
            time.sleep(5)  # SIM needs a moment to register after unlocking
        elif "SIM PUK" in status:
            raise SmsError("SIM card is PUK-locked - unlock it in a phone first")
        self.command("AT+CMGF=0")

    def send_pdu(self, length: int, pdu: str) -> None:
        self.port.write(f"AT+CMGS={length}\r".encode())
        self.wait(10, prompt=True, what="AT+CMGS")
        self.port.write(pdu.encode() + b"\x1a")
        self.wait(90, what="sending SMS")

    def status(self) -> dict[str, str]:
        def ask(cmd):
            try:
                lines = [l.strip() for l in self.command(cmd).splitlines()]
                return " ".join(l for l in lines if l and l != "OK")
            except SmsError as exc:
                return str(exc)
        csq = ask("AT+CSQ")
        m = re.search(r"\+CSQ:\s*(\d+)", csq)
        signal = "unknown" if not m or m.group(1) == "99" else f"{min(100, int(m.group(1)) * 100 // 31)}%"
        return {
            "model": ask("AT+CGMM"),
            "sim": ask("AT+CPIN?"),
            "network": ask("AT+COPS?"),
            "registration": ask("AT+CREG?"),
            "signal": signal,
        }


class ModemSender:
    _lock = threading.Lock()  # one conversation with the modem at a time

    def __init__(self, device: str, pin: str = "", baud: int = 115200, port_factory=SerialPort):
        if not device:
            raise SmsError("modem_device is not set in the configuration")
        self.device, self.pin, self.baud = device, pin, baud
        self.port_factory = port_factory
        self._ref = int(time.time()) & 0xFF

    def _session(self, fn):
        with self._lock:
            port = self.port_factory(self.device, self.baud)
            try:
                modem = Modem(port)
                modem.setup(self.pin)
                return fn(modem)
            finally:
                port.close()

    def send(self, to: str, body: str) -> str:
        self._ref = (self._ref + 1) & 0xFF
        pdus = build_pdus(to, body, self._ref)

        def go(modem):
            for length, pdu in pdus:
                modem.send_pdu(length, pdu)
        self._session(go)
        return f"via modem ({len(pdus)} SMS)"

    def status(self) -> dict[str, str]:
        return self._session(lambda m: m.status())
