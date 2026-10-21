"""
Download Rimi e-receipt PDFs from a mailbox over IMAP.

Rimi sends every e-receipt the same way: an e-mail from ``noreply@rimibaltic.com``
with the subject "Tavs pirkuma čeks" and the receipt attached as a PDF. This module
searches a folder for such e-mails and saves the attachments:

    <out>/YYYY-MM/<attachment name>.pdf   receipts, by e-mail date
    <out>/manifest.jsonl                  one line per e-mail (UID, Message-ID, date, files)
    <out>/.fetch_state.json               processed UIDs, for incremental runs

The mailbox is never modified: the folder is opened read-only and messages are
fetched with ``BODY.PEEK`` (they stay unread).
"""

from __future__ import annotations

import base64
import contextlib
import email
import imaplib
import json
import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from email import policy
from email.utils import parsedate_to_datetime
from pathlib import Path

DEFAULT_SENDER = "noreply@rimibaltic.com"
DEFAULT_SUBJECT = "Tavs pirkuma čeks"
STATE_FILE = ".fetch_state.json"
MANIFEST_FILE = "manifest.jsonl"
STATE_FLUSH_EVERY = 25


@dataclass
class FetchConfig:
    host: str
    user: str
    password: str
    port: int = 993
    folder: str = "INBOX"
    sender: str = DEFAULT_SENDER
    subject: str = DEFAULT_SUBJECT
    out_dir: Path = Path("rimi-receipts")
    since: date | None = None
    limit: int | None = None


@dataclass
class FetchStats:
    messages_found: int = 0
    already_done: int = 0
    processed: int = 0
    saved: int = 0
    duplicates: int = 0
    other_subject: int = 0
    without_pdf: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)


def imap_utf7_encode(name: str) -> str:
    """Encode a folder name in IMAP modified UTF-7 (RFC 3501), e.g. ``Rimi čeki`` → ``Rimi &AQ0-eki``."""
    result: list[str] = []
    buffer: list[str] = []

    def flush() -> None:
        if buffer:
            raw = "".join(buffer).encode("utf-16-be")
            result.append("&" + base64.b64encode(raw).decode("ascii").rstrip("=").replace("/", ",") + "-")
            buffer.clear()

    for ch in name:
        if 0x20 <= ord(ch) <= 0x7E:
            flush()
            result.append("&-" if ch == "&" else ch)
        else:
            buffer.append(ch)
    flush()
    return "".join(result)


def imap_utf7_decode(name: str) -> str:
    """Decode an IMAP modified UTF-7 folder name."""

    def repl(match: re.Match[str]) -> str:
        chunk = match.group(1)
        if not chunk:
            return "&"
        chunk = chunk.replace(",", "/")
        chunk += "=" * (-len(chunk) % 4)
        return base64.b64decode(chunk).decode("utf-16-be")

    return re.sub(r"&([^-]*)-", repl, name)


def _normalise(text: str) -> str:
    return unicodedata.normalize("NFC", text).casefold().strip()


def _safe_filename(name: str) -> str:
    return re.sub(r'[\\/*?:"<>|\r\n]', "_", Path(name).name).strip() or "receipt.pdf"


def list_folders(mail: imaplib.IMAP4) -> list[tuple[str, str | None]]:
    """Return ``(decoded name, hierarchy delimiter)`` for every folder."""
    status, data = mail.list()
    if status != "OK":
        raise RuntimeError("cannot list IMAP folders")
    folders: list[tuple[str, str | None]] = []
    for raw in data:
        if not isinstance(raw, bytes):
            continue
        line = raw.decode("ascii", errors="replace")
        match = re.match(r'\((?P<flags>[^)]*)\) (?P<delim>"[^"]*"|NIL) (?P<name>.+)$', line)
        if not match:
            continue
        delim = match["delim"]
        folders.append(
            (imap_utf7_decode(match["name"].strip('"')), None if delim == "NIL" else delim.strip('"'))
        )
    return folders


def resolve_folder(mail: imaplib.IMAP4, folder: str) -> str:
    """Find a folder by full name or by its last path segment (``Rimi čeki`` → ``INBOX/Rimi čeki``)."""
    folders = list_folders(mail)
    names = [name for name, _ in folders]
    if folder in names:
        return folder
    target = _normalise(folder)
    candidates = [n for n, d in folders if d and _normalise(n.split(d)[-1]) == target]
    if len(candidates) == 1:
        return candidates[0]
    if candidates:
        raise RuntimeError(f"folder name {folder!r} is ambiguous: {candidates}")
    raise RuntimeError(f"folder {folder!r} not found; available: {names}")


def connect(config: FetchConfig) -> imaplib.IMAP4_SSL:
    mail = imaplib.IMAP4_SSL(config.host, config.port)
    mail.login(config.user, config.password)
    return mail


def _load_state(path: Path) -> tuple[str | None, set[str]]:
    if not path.exists():
        return None, set()
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("uidvalidity"), set(data.get("done_uids", []))


def _save_state(path: Path, uidvalidity: str | None, done: set[str]) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps({"uidvalidity": uidvalidity, "done_uids": sorted(done, key=int)}), encoding="utf-8"
    )
    tmp.replace(path)


def _save_pdf(target_dir: Path, filename: str, payload: bytes, uid: str) -> tuple[Path, bool]:
    """Save a PDF; returns ``(path, written)``. Identical files are not written twice."""
    target_dir.mkdir(parents=True, exist_ok=True)
    out = target_dir / filename
    if out.exists():
        if out.read_bytes() == payload:
            return out, False
        out = target_dir / f"{out.stem}_uid{uid}{out.suffix}"
        if out.exists():
            return out, False
    out.write_bytes(payload)
    return out, True


def fetch_receipts(
    config: FetchConfig,
    dry_run: bool = False,
    progress: Callable[[str], None] | None = None,
) -> FetchStats:
    """Download new receipt PDFs according to ``config``."""
    say = progress or (lambda _msg: None)
    stats = FetchStats()
    out = config.out_dir
    mail = connect(config)
    state_path = out / STATE_FILE
    uidvalidity: str | None = None
    done: set[str] = set()
    started = False
    try:
        folder = resolve_folder(mail, config.folder)
        status, data = mail.select(f'"{imap_utf7_encode(folder)}"', readonly=True)
        if status != "OK":
            raise RuntimeError(f"cannot open folder {folder!r}: {data}")
        _, uv = mail.response("UIDVALIDITY")
        uidvalidity = uv[0].decode() if uv and uv[0] else None

        # Not every server supports non-ASCII SEARCH, so only the sender is filtered
        # on the server; the subject is checked locally.
        criteria = ["FROM", f'"{config.sender}"']
        if config.since:
            criteria += ["SINCE", config.since.strftime("%d-%b-%Y")]
        status, data = mail.uid("SEARCH", None, *criteria)
        if status != "OK":
            raise RuntimeError(f"IMAP SEARCH failed: {data}")
        uids = [u.decode() for u in (data[0].split() if data and data[0] else [])]
        stats.messages_found = len(uids)

        out.mkdir(parents=True, exist_ok=True)
        saved_uv, done = _load_state(state_path)
        if saved_uv is not None and saved_uv != uidvalidity:
            say("folder UIDVALIDITY changed: re-scanning all messages (duplicates are not re-saved)")
            done = set()
        stats.already_done = len(done & set(uids))
        pending = [u for u in uids if u not in done][: config.limit]
        say(f"folder {folder!r}: {len(uids)} messages from {config.sender}, {len(pending)} to process")
        if dry_run or not pending:
            return stats

        started = True
        subject = _normalise(config.subject)
        with (out / MANIFEST_FILE).open("a", encoding="utf-8") as manifest:
            for n, uid in enumerate(pending, 1):
                status, msg_data = mail.uid("FETCH", uid, "(BODY.PEEK[])")
                raw = next(
                    (p[1] for p in msg_data or [] if isinstance(p, tuple) and isinstance(p[1], bytes)),
                    None,
                )
                if status != "OK" or raw is None:
                    stats.failed.append(uid)  # retried on the next run
                    continue
                stats.processed += 1
                msg = email.message_from_bytes(raw, policy=policy.default)
                msg_subject = str(msg.get("Subject", ""))
                if subject not in _normalise(msg_subject):
                    stats.other_subject += 1
                    done.add(uid)
                    continue
                try:
                    sent = parsedate_to_datetime(str(msg.get("Date")))
                except (TypeError, ValueError):
                    sent = None
                month = sent.strftime("%Y-%m") if sent else "unknown-date"

                files: list[str] = []
                for part in msg.walk():
                    if part.is_multipart():
                        continue
                    filename = part.get_filename() or ""
                    if part.get_content_type() != "application/pdf" and not filename.lower().endswith(".pdf"):
                        continue
                    payload = part.get_payload(decode=True)
                    if not isinstance(payload, bytes) or not payload:
                        continue
                    name = _safe_filename(filename or f"uid{uid}.pdf")
                    if not name.lower().endswith(".pdf"):
                        name += ".pdf"
                    path, written = _save_pdf(out / month, name, payload, uid)
                    if written:
                        stats.saved += 1
                    else:
                        stats.duplicates += 1
                    files.append(path.relative_to(out).as_posix())
                if not files:
                    stats.without_pdf.append(uid)

                record = {
                    "uid": uid,
                    "uidvalidity": uidvalidity,
                    "message_id": str(msg.get("Message-ID", "")),
                    "date": sent.isoformat() if sent else None,
                    "subject": msg_subject,
                    "files": files,
                }
                manifest.write(json.dumps(record, ensure_ascii=False) + "\n")
                done.add(uid)
                if n % STATE_FLUSH_EVERY == 0:
                    manifest.flush()
                    _save_state(state_path, uidvalidity, done)
                    say(f"  {n}/{len(pending)}")
    finally:
        if started:
            _save_state(state_path, uidvalidity, done)
        with contextlib.suppress(imaplib.IMAP4.error, OSError):
            mail.logout()
    return stats


def read_env_file(path: Path) -> dict[str, str]:
    """Minimal ``KEY=VALUE`` reader for ``.env`` files (comments and quotes supported)."""
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        values[key.strip()] = value
    return values
