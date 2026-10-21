# Fetching receipts from e-mail

Rimi delivers e-receipts only by e-mail. Every message looks the same:

| | |
|---|---|
| From | `noreply@rimibaltic.com` |
| Subject | `Tavs pirkuma čeks` |
| Attachment | one PDF, named like `07-7123456.pdf` (register – receipt number) |

`rimi-receipts fetch` searches one IMAP folder for these messages and saves the attachments.

## What it does to your mailbox

Nothing. The folder is opened read-only (`EXAMINE`) and messages are fetched with `BODY.PEEK[]`, so they
are not even marked as read.

## Output

```
<out>/
  2026-10/07-7123456.pdf     receipts, grouped by e-mail month
  manifest.jsonl             one JSON line per processed e-mail: uid, Message-ID, date, subject, files
  .fetch_state.json          processed message UIDs — re-runs only download new e-mails
```

If the folder is recreated (its `UIDVALIDITY` changes) everything is scanned again, but files that are
already present are not written twice.

## Settings

Every option can be given on the command line or as an environment variable:

| Option | Environment | Default |
|---|---|---|
| `--host` | `RIMI_IMAP_HOST` | — |
| `--port` | `RIMI_IMAP_PORT` | `993` (SSL) |
| `--user` | `RIMI_IMAP_USER` | — |
| — | `RIMI_IMAP_PASSWORD` | asked interactively |
| `--folder` | `RIMI_IMAP_FOLDER` | `INBOX` |
| `--sender` | `RIMI_SENDER` | `noreply@rimibaltic.com` |
| `--subject` | `RIMI_SUBJECT` | `Tavs pirkuma čeks` |
| `--out` | `RIMI_OUTPUT_DIR` | `./rimi-receipts` |
| `--since YYYY-MM-DD` | — | all e-mails |
| `--limit N` | — | no limit |

`--env-file path/to/.env` reads the same `RIMI_*` keys from a file (real environment variables win):

```dotenv
RIMI_IMAP_HOST=imap.gmail.com
RIMI_IMAP_USER=you@gmail.com
RIMI_IMAP_PASSWORD=abcd efgh ijkl mnop
RIMI_IMAP_FOLDER=Rimi čeki
RIMI_OUTPUT_DIR=/home/you/rimi-receipts
```

Keep that file out of version control.

**Folders.** `--folder` accepts the full path (`INBOX/Rimi čeki`) or just the last segment (`Rimi čeki`);
non-ASCII names are encoded as IMAP requires. `--list-folders` prints what the server has. If you do not
sort your mail, leave the default `INBOX` — the sender and subject filters find the receipts.

## Provider notes

- **Gmail**: `imap.gmail.com`. With 2-step verification enabled, create an
  [app password](https://myaccount.google.com/apppasswords) and use it instead of your password. Gmail
  labels appear as folders (`Rimi čeki` for a label of that name); `[Gmail]/All Mail` contains everything.
- **Outlook / Hotmail**: Microsoft disabled password (basic) authentication for IMAP on personal
  accounts; this tool does not implement OAuth. Forward receipts to another mailbox, or export them.
- **inbox.lv**: `mail.inbox.lv`, IMAP must be enabled in the settings.
- **Others**: any IMAP server with SSL on port 993 works.

## Automating

Run it on a schedule and feed new files to the parser, e.g. with cron:

```cron
15 * * * *  rimi-receipts fetch --env-file ~/.config/rimi.env && rimi-receipts check ~/rimi-receipts
```

or from Python:

```python
from pathlib import Path
from rimi_receipts import parse_pdf
from rimi_receipts.fetch import FetchConfig, fetch_receipts

stats = fetch_receipts(
    FetchConfig(host="imap.gmail.com", user="you@gmail.com", password="…", out_dir=Path("rimi-receipts"))
)
```
