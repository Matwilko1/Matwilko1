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

- `twilio`: fill in the Twilio account SID, auth token and sender number.
  A trial Twilio account can only text numbers you have verified.
- `homeassistant`: set `notify_service` to an SMS notify service you already
  have, such as `notify.sms` from the SMS (GSM modem) integration or the Twilio
  SMS integration. The add-on calls it with `target` set to the coworker's number.

**Schedule** - pick the days and time (Home Assistant's time zone). Each
scheduled day sends at most once, even if the add-on restarts.

**Message** - placeholders `{name}`, `{amount}`, `{payee}`, `{payment_details}`.

Please get your coworkers' OK before texting them.
