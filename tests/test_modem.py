import pytest

from coffee_reminders import modem
from coffee_reminders.sms import SmsError


def decode_gsm7(ud: bytes, septets: int, udh_len: int = 0) -> str:
    bits = [(b >> i) & 1 for b in ud for i in range(8)]
    skip = ((udh_len * 8) + 6) // 7 if udh_len else 0
    out = []
    for n in range(skip, septets):
        v = sum(bits[n * 7 + i] << i for i in range(7))
        out.append(modem.GSM7[v])
    return "".join(out)


def test_reference_pdu_hello():
    # well known example: "hello" -> E8329BFD06
    [(length, pdu)] = modem.build_pdus("+48500000001", "hello")
    assert pdu == "0001000B918405000000F1000005E8329BFD06"
    assert length == len(pdu) // 2 - 1


def test_unicode_uses_ucs2():
    [(_, pdu)] = modem.build_pdus("+48500000001", "Zażółć")
    assert pdu.endswith("00080C005A0061017C00F301420107")


@pytest.mark.parametrize("text", ["A" * 160, "Hi Anna! " * 30, "ą" * 150, "☕" * 80])
def test_long_messages_split_and_roundtrip(text):
    pdus = modem.build_pdus("+48500000001", text, ref=7)
    if len(pdus) == 1:
        return
    decoded = []
    for seq, (length, hexpdu) in enumerate(pdus, 1):
        tpdu = bytes.fromhex(hexpdu)[1:]
        assert len(tpdu) == length and tpdu[0] & 0x40
        addr_len = (tpdu[2] + 1) // 2
        dcs, udl = tpdu[4 + addr_len + 1], tpdu[4 + addr_len + 2]
        ud = tpdu[4 + addr_len + 3:]
        assert ud[:6] == bytes([5, 0, 3, 7, len(pdus), seq])
        if dcs == 0:
            assert udl <= 160
            decoded.append(decode_gsm7(ud, udl, udh_len=6))
        else:
            assert len(ud) == udl <= 140
            decoded.append(ud[6:].decode("utf-16-be"))
    assert "".join(decoded) == text


def test_160_gsm_chars_fit_in_one():
    assert len(modem.build_pdus("+48500000001", "A" * 160)) == 1
    assert len(modem.build_pdus("+48500000001", "A" * 161)) == 2


class FakePort:
    """Pretends to be a modem: answers AT commands."""

    def __init__(self, device, baud, needs_pin=False):
        self.out = b""
        self.written = []
        self.needs_pin = needs_pin
        self.closed = False

    def write(self, data):
        self.written.append(data)
        if data.endswith(b"\x1a"):
            self.out += b"\r\n+CMGS: 12\r\n\r\nOK\r\n"
            return
        cmd = data.decode().strip()
        if cmd.startswith("AT+CMGS="):
            self.out += b"\r\n> "
        elif cmd == "AT+CPIN?":
            state = "SIM PIN" if self.needs_pin else "READY"
            self.out += f"\r\n+CPIN: {state}\r\n\r\nOK\r\n".encode()
        elif cmd.startswith('AT+CPIN="'):
            self.needs_pin = False
            self.out += b"\r\nOK\r\n"
        elif cmd == "AT+CSQ":
            self.out += b"\r\n+CSQ: 20,99\r\n\r\nOK\r\n"
        else:
            self.out += b"\r\nOK\r\n"

    def read(self, timeout):
        data, self.out = self.out, b""
        return data

    def close(self):
        self.closed = True


def test_modem_sender_sends_all_parts(monkeypatch):
    ports = []

    def factory(device, baud):
        ports.append(FakePort(device, baud))
        return ports[-1]

    s = modem.ModemSender("/dev/ttyUSB2", port_factory=factory)
    ref = s.send("+48500000001", "x" * 200)
    assert ref == "via modem (2 SMS)"
    sent = [w for w in ports[0].written if w.endswith(b"\x1a")]
    assert len(sent) == 2
    assert b"AT+CMGF=0\r" in ports[0].written and ports[0].closed


def test_pin_required(monkeypatch):
    monkeypatch.setattr(modem.time, "sleep", lambda s: None)
    no_pin = modem.ModemSender("/dev/x", port_factory=lambda d, b: FakePort(d, b, needs_pin=True))
    with pytest.raises(SmsError, match="PIN"):
        no_pin.send("+48500000001", "hi")
    ports = []
    with_pin = modem.ModemSender("/dev/x", pin="1234",
                                 port_factory=lambda d, b: ports.append(FakePort(d, b, True)) or ports[-1])
    with_pin.send("+48500000001", "hi")
    assert b'AT+CPIN="1234"\r' in ports[0].written


def test_status():
    s = modem.ModemSender("/dev/x", port_factory=FakePort)
    st = s.status()
    assert st["signal"] == "64%" and "READY" in st["sim"]


def test_missing_device_errors():
    with pytest.raises(SmsError, match="cannot open modem"):
        modem.ModemSender("/dev/does-not-exist").send("+48500000001", "hi")
    with pytest.raises(SmsError, match="modem_device"):
        modem.ModemSender("")
