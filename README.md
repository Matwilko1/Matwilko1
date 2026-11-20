# ☕ Coffee payment SMS reminders

A small tool that texts coworkers who owe money to the coffee fund.
It uses only the Python standard library (3.11+) and sends SMS through [Twilio](https://www.twilio.com/).

## How it works

- `config.json` is the ledger: who your coworkers are, their phone numbers, and how much each one owes.
- `remind` sends an SMS to every **active** coworker who owes at least `min_amount`. People who owe nothing get no message.
- A GitHub Actions workflow runs `remind` on a schedule (every Monday at 08:00 UTC by default).

## Setup

1. Copy the example config and edit it:
   ```bash
   cp config.example.json config.json
   ```
   Phone numbers must be in international format (`+48123456789`).
   `config.json` is git-ignored so phone numbers never end up in the repo.

2. Create a Twilio account and get a phone number (or a Messaging Service).
   On a trial account you can only text numbers you have verified in Twilio.

3. Try it without sending anything:
   ```bash
   python -m coffee_reminders list
   python -m coffee_reminders remind --dry-run
   ```

4. Send for real:
   ```bash
   export TWILIO_ACCOUNT_SID=AC...
   export TWILIO_AUTH_TOKEN=...
   export TWILIO_FROM=+1555...      # or a Messaging Service SID (MG...)
   python -m coffee_reminders remind
   ```

## Keeping the ledger up to date

```bash
python -m coffee_reminders charge 20            # everyone active owes 20 more (e.g. monthly fee)
python -m coffee_reminders charge 8.5 Anna      # one person bought a bag on the fund
python -m coffee_reminders paid Anna            # Anna paid everything
python -m coffee_reminders paid Piotr 10        # Piotr paid part of it
python -m coffee_reminders add Ola +48500000003
python -m coffee_reminders remove Ola
python -m coffee_reminders remind --only Anna   # remind just one person
```

## Message text

Edit `message_template` in `config.json`. Available placeholders:
`{name}`, `{amount}`, `{payee}`, `{payment_details}`.
Keep it under 160 characters (no emoji) to fit in a single SMS segment.

## Automatic reminders with GitHub Actions

`.github/workflows/coffee-reminders.yml` runs the tests and then sends reminders every Monday.
Add these repository secrets (Settings → Secrets and variables → Actions):

| Secret | Value |
| --- | --- |
| `COFFEE_CONFIG_JSON` | the full contents of your `config.json` |
| `TWILIO_ACCOUNT_SID` | your Twilio account SID |
| `TWILIO_AUTH_TOKEN` | your Twilio auth token |
| `TWILIO_FROM` | your Twilio number or Messaging Service SID |

After recording payments locally, paste the updated `config.json` into the
`COFFEE_CONFIG_JSON` secret so the next scheduled run uses current balances.
Use **Run workflow** (dry run is on by default) to preview the messages.

Prefer running it on your own machine? Use cron instead:
```cron
0 9 * * 1  cd /path/to/repo && . ./.env && python3 -m coffee_reminders remind
```

## Be nice

Get your coworkers' OK before texting them. Twilio handles `STOP` replies automatically
for most countries; remove anyone who opts out with `remove` or set `"active": false`.

## Tests

```bash
python -m pytest
```
