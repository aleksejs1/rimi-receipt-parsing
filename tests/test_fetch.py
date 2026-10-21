from __future__ import annotations

import json
from email.message import EmailMessage
from pathlib import Path

import pytest

from rimi_receipts import fetch
from rimi_receipts.fetch import FetchConfig, fetch_receipts, imap_utf7_decode, imap_utf7_encode, read_env_file


def test_folder_name_encoding() -> None:
    assert imap_utf7_encode("Rimi čeki") == "Rimi &AQ0-eki"
    assert imap_utf7_decode("Rimi &AQ0-eki") == "Rimi čeki"
    assert imap_utf7_encode("A&B") == "A&-B"
    assert imap_utf7_decode("A&-B") == "A&B"


def test_env_file(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text(
        '# comment\nRIMI_IMAP_HOST=imap.example.com\nRIMI_IMAP_FOLDER="Rimi čeki"\n', encoding="utf-8"
    )
    assert read_env_file(env) == {"RIMI_IMAP_HOST": "imap.example.com", "RIMI_IMAP_FOLDER": "Rimi čeki"}


def _message(subject: str, date: str, attachment: bytes | None, filename: str = "07-7123456.pdf") -> bytes:
    msg = EmailMessage()
    msg["From"] = "Rimi <noreply@rimibaltic.com>"
    msg["Subject"] = subject
    msg["Date"] = date
    msg["Message-ID"] = f"<{hash((subject, date))}@example.com>"
    msg.set_content("Paldies par pirkumu!")
    if attachment is not None:
        msg.add_attachment(attachment, maintype="application", subtype="pdf", filename=filename)
    return msg.as_bytes()


class FakeIMAP:
    """Just enough of imaplib.IMAP4 for fetch_receipts()."""

    def __init__(self, messages: dict[str, bytes]) -> None:
        self.messages = messages
        self.readonly = None
        self.fetched: list[str] = []

    def list(self):
        return "OK", [b'(\\HasNoChildren) "/" "INBOX"', b'(\\HasNoChildren) "/" "INBOX/Rimi &AQ0-eki"']

    def select(self, mailbox, readonly=False):
        assert mailbox == '"INBOX/Rimi &AQ0-eki"'
        self.readonly = readonly
        return "OK", [str(len(self.messages)).encode()]

    def response(self, code):
        return code, [b"42"]

    def uid(self, command, *args):
        if command == "SEARCH":
            assert args[1:3] == ("FROM", '"noreply@rimibaltic.com"')
            return "OK", [" ".join(self.messages).encode()]
        if command == "FETCH":
            uid, spec = args
            assert spec == "(BODY.PEEK[])"
            self.fetched.append(uid)
            return "OK", [(f"{uid} (BODY[] {{}})".encode(), self.messages[uid]), b")"]
        raise AssertionError(command)

    def logout(self):
        return "BYE", []


@pytest.fixture
def fake_mailbox(monkeypatch: pytest.MonkeyPatch) -> FakeIMAP:
    server = FakeIMAP(
        {
            "1": _message("Tavs pirkuma čeks", "Mon, 05 Jan 2026 10:00:00 +0200", b"%PDF-1 one"),
            "2": _message(
                "Tavs pirkuma čeks", "Sun, 01 Feb 2026 11:00:00 +0200", b"%PDF-1 two", "08-8000001.pdf"
            ),
            "3": _message("Rimi jaunumi", "Sun, 01 Feb 2026 12:00:00 +0200", None),
            "4": _message("Tavs pirkuma čeks", "Sun, 01 Feb 2026 13:00:00 +0200", None),
        }
    )
    monkeypatch.setattr(fetch, "connect", lambda config: server)
    return server


def test_fetch_downloads_receipts_once(tmp_path: Path, fake_mailbox: FakeIMAP) -> None:
    config = FetchConfig(
        host="imap.example.com", user="u", password="p", folder="Rimi čeki", out_dir=tmp_path
    )
    stats = fetch_receipts(config)
    assert fake_mailbox.readonly is True
    assert stats.messages_found == 4
    assert stats.saved == 2
    assert stats.other_subject == 1
    assert stats.without_pdf == ["4"]
    assert (tmp_path / "2026-01" / "07-7123456.pdf").read_bytes() == b"%PDF-1 one"
    assert (tmp_path / "2026-02" / "08-8000001.pdf").read_bytes() == b"%PDF-1 two"
    manifest = [
        json.loads(line) for line in (tmp_path / "manifest.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert [m["uid"] for m in manifest] == ["1", "2", "4"]

    # second run: nothing new is downloaded
    fake_mailbox.fetched.clear()
    stats = fetch_receipts(config)
    assert stats.already_done == 4
    assert fake_mailbox.fetched == []


def test_fetch_dry_run_writes_nothing(tmp_path: Path, fake_mailbox: FakeIMAP) -> None:
    config = FetchConfig(host="h", user="u", password="p", folder="INBOX/Rimi čeki", out_dir=tmp_path / "out")
    stats = fetch_receipts(config, dry_run=True)
    assert stats.messages_found == 4
    assert fake_mailbox.fetched == []
    assert not (tmp_path / "out" / "manifest.jsonl").exists()
