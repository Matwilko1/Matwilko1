# Coffee Reminders

Keeps track of who owes the coffee fund and texts them a reminder.

## Using it

Open **Coffee** in the Home Assistant sidebar. There you can:

- add coworkers (phone in international format, e.g. `+48123456789`)
- charge everyone a fee, or charge one person
- mark payments (in full or partial)
- pause someone so they are not texted
- preview the messages or send them right now
- see a log of everything that happened

Balances are stored in the add-on's data and survive restarts and updates.
They are included in Home Assistant backups.

## Configuration

**Sending SMS** - choose one:

- `modem`: a USB modem with a SIM card plugged into the Home Assistant machine
  (see [Hardware](#hardware)). Pick its serial port in `modem_device` and set
  `modem_pin` if the SIM has a PIN. Use **Check modem** on the Coffee page to see
  signal and network, and **Send test SMS** to text yourself.
- `twilio`: fill in the Twilio account SID, auth token and sender number.
  A trial Twilio account can only text numbers you have verified.
- `homeassistant`: set `notify_service` to an SMS notify service you already
  have, such as `notify.sms` from the SMS (GSM modem) integration or the Twilio
  SMS integration. The add-on calls it with `target` set to the coworker's number.

## Hardware

You need a USB modem that exposes a **serial AT-command port**, plus a SIM card
that can send SMS (a cheap prepaid one is fine; no data needed).

- **Recommended: a SIM7600-based 4G USB dongle** (for example Waveshare
  SIM7600E-H for Europe; pick the variant for your region's LTE bands). It
  shows up as several `ttyUSB` ports; the AT port is usually `ttyUSB2`
  (`/dev/serial/by-id/...-if02-port0`).
- **Huawei E3372 / similar sticks only in "stick" (serial) firmware.** The
  common "HiLink" versions act as a network card and have no AT port, so they
  won't work.
- **Avoid 2G/3G-only modules (SIM800, SIM900, old 3G sticks)**: 2G and 3G
  networks are being switched off in many countries.

Tips:
- Put the SIM in a phone first: make sure it can send an SMS, and either
  disable the PIN or note it for `modem_pin`.
- Prepaid SIMs can expire if not topped up - check your operator's rules.
- Plug the modem in via a powered USB hub or short cable if it disconnects; LTE
  modems draw a lot of power when transmitting, especially on a Raspberry Pi.
- If you already use Home Assistant's *SMS notifications via GSM-modem*
  integration with this modem, use `sms_provider: homeassistant` with
  `notify_service: notify.sms` instead - two programs can't share the port.

**Schedule** - pick the days and time (Home Assistant's time zone). Each
scheduled day sends at most once, even if the add-on restarts.

**Message** - placeholders `{name}`, `{amount}`, `{payee}`, `{payment_details}`.

Please get your coworkers' OK before texting them.
