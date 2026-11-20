# ☕ Coffee payment SMS reminders

A small tool that texts coworkers who owe money to the coffee fund.
It uses only the Python standard library (3.11+) and sends SMS through [Twilio](https://www.twilio.com/).

## Two ways to run it

1. **Home Assistant add-on (recommended)** - a sidebar page for tracking balances
   and a built-in schedule. See [Install on Home Assistant](#install-on-home-assistant).
2. **Command line / GitHub Actions** - described below. Run commands from the
   `coffee-reminders/` folder.

## Install on Home Assistant

Needs Home Assistant OS or Supervised (the editions that support add-ons).

**Option A - add this repository (needs the repo to be public on GitHub):**
Settings → Add-ons → Add-on Store → ⋮ → Repositories → add
`https://github.com/Matwilko1/Matwilko1`, then install **Coffee Reminders**.

**Option B - local add-on (works with a private repo):**
1. Install the *Samba share* or *Advanced SSH & Web Terminal* add-on.
2. Copy the `coffee-reminders` folder into the `addons` share, so you have
   `/addons/coffee-reminders/config.yaml`.
3. Settings → Add-ons → Add-on Store → ⋮ → **Check for updates**. It appears
   under *Local add-ons*. Install it. Home Assistant builds it on your machine,
   which can take a few minutes.

Then on the add-on's **Configuration** tab choose how to send SMS
(a USB modem with a SIM card, Twilio, or an SMS notify service you already have in Home Assistant), your payment
details and the reminder days/time. Start it and open **Coffee** in the sidebar.
Full details: [coffee-reminders/DOCS.md](coffee-reminders/DOCS.md).

## How it works (command line)

- `config.json` is the ledger: who your coworkers are, their phone numbers, and how much each one owes.
- `remind` sends an SMS to every **active** coworker who owes at least `min_amount`. People who owe nothing get no message.
- A GitHub Actions workflow runs `remind` on a schedule (every Monday at 08:00 UTC by default).

## Setup

1. In the `coffee-reminders/` folder, copy the example config and edit it:
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
