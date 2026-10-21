"""Command-line interface: ``rimi-receipts {parse,check,fetch,synth,glyphs}``."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from datetime import date
from pathlib import Path

from . import __version__, parse_pdf


def _pdfs(paths: list[Path]) -> list[Path]:
    out: list[Path] = []
    for p in paths:
        out.extend(sorted(p.rglob("*.pdf")) if p.is_dir() else [p])
    return out


def cmd_parse(args: argparse.Namespace) -> int:
    failed = 0
    for pdf in _pdfs(args.paths):
        receipt = parse_pdf(pdf)
        errors = receipt.validate()
        failed += bool(errors)
        if args.format == "text":
            status = "OK" if not errors else "INVALID: " + "; ".join(errors)
            print(f"===== {pdf.name}  {status}")
            print("\n".join(receipt.raw_lines))
        else:
            data = {"file": str(pdf), **receipt.to_dict()}
            if args.format == "jsonl":
                print(json.dumps(data, ensure_ascii=False))
            else:
                print(json.dumps(data, ensure_ascii=False, indent=2))
    return 1 if failed else 0


def _check_one(pdf: Path) -> tuple[str, list[str], int]:
    try:
        receipt = parse_pdf(pdf)
        return str(pdf), receipt.validate(), len(receipt.low_confidence)
    except Exception as exc:  # report and continue with the rest
        return str(pdf), [f"{type(exc).__name__}: {exc}"], 0


def cmd_check(args: argparse.Namespace) -> int:
    pdfs = _pdfs(args.paths)
    bad = 0
    uncertain = 0
    with ProcessPoolExecutor(max_workers=args.jobs) as pool:
        for name, errors, low in pool.map(_check_one, pdfs, chunksize=4):
            uncertain += low
            if errors:
                bad += 1
                print(f"{name}: " + "; ".join(errors))
    print(f"{len(pdfs) - bad}/{len(pdfs)} receipts add up; {uncertain} low-confidence characters")
    return 1 if bad else 0


def cmd_fetch(args: argparse.Namespace) -> int:
    from .fetch import FetchConfig, connect, fetch_receipts, list_folders, read_env_file

    env = dict(os.environ)
    if args.env_file:
        env = {
            **read_env_file(args.env_file),
            **{k: v for k, v in os.environ.items() if k.startswith("RIMI_")},
        }

    def setting(value: str | None, key: str, default: str | None = None) -> str | None:
        return value if value is not None else env.get(key, default)

    host = setting(args.host, "RIMI_IMAP_HOST")
    user = setting(args.user, "RIMI_IMAP_USER")
    if not host or not user:
        print(
            "IMAP host and user are required (--host/--user or RIMI_IMAP_HOST/RIMI_IMAP_USER)",
            file=sys.stderr,
        )
        return 2
    password = env.get("RIMI_IMAP_PASSWORD") or getpass.getpass(f"IMAP password for {user}: ")
    config = FetchConfig(
        host=host,
        user=user,
        password=password,
        port=int(setting(args.port, "RIMI_IMAP_PORT", "993") or 993),
        folder=setting(args.folder, "RIMI_IMAP_FOLDER", "INBOX") or "INBOX",
        sender=setting(args.sender, "RIMI_SENDER", "noreply@rimibaltic.com") or "",
        subject=setting(args.subject, "RIMI_SUBJECT", "Tavs pirkuma čeks") or "",
        out_dir=Path(setting(args.out, "RIMI_OUTPUT_DIR", "rimi-receipts") or "rimi-receipts"),
        since=date.fromisoformat(args.since) if args.since else None,
        limit=args.limit,
    )
    if args.list_folders:
        mail = connect(config)
        try:
            for name, _ in list_folders(mail):
                print(name)
        finally:
            mail.logout()
        return 0
    stats = fetch_receipts(config, dry_run=args.dry_run, progress=print)
    if args.dry_run:
        return 0
    print(
        f"saved {stats.saved} new PDFs ({stats.duplicates} already present), "
        f"{stats.other_subject} e-mails with another subject, {len(stats.without_pdf)} without a PDF"
    )
    if stats.without_pdf:
        print("UIDs without a PDF attachment: " + ", ".join(stats.without_pdf[:20]))
    if stats.failed:
        print(f"{len(stats.failed)} messages could not be downloaded; they will be retried next time")
    print(f"receipts are in {config.out_dir.resolve()}")
    return 0


def cmd_synth(args: argparse.Namespace) -> int:
    from .synth import write_samples

    for path in write_samples(args.out, count=args.count, seed=args.seed):
        print(path)
    return 0


def cmd_glyphs(args: argparse.Namespace) -> int:
    from . import glyph_tools

    if args.action == "harvest":
        n = glyph_tools.harvest(args.receipts, args.work_dir, jobs=args.jobs)
        print(f"{n} unknown cells saved to {args.work_dir}")
    elif args.action == "review":
        n = glyph_tools.review(args.work_dir)
        print(f"{n} clusters; see {args.work_dir}/unknown-*.png")
    elif args.action == "add":
        glyphs = glyph_tools.add(args.work_dir, json.loads(args.labels), args.glyph_file)
        print(f"{len(glyphs.chars)} templates in {args.glyph_file}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="rimi-receipts", description="Parse Rimi Latvia e-receipt PDFs offline."
    )
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("parse", help="parse receipts and print them as JSON or text")
    p.add_argument("paths", nargs="+", type=Path, help="PDF files or directories")
    p.add_argument("--format", choices=["json", "jsonl", "text"], default="json")
    p.set_defaults(func=cmd_parse)

    p = sub.add_parser("check", help="validate many receipts and report the ones that do not add up")
    p.add_argument("paths", nargs="+", type=Path, help="PDF files or directories")
    p.add_argument("--jobs", type=int, default=None, help="worker processes (default: CPU count)")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("fetch", help="download receipt PDFs from a mailbox over IMAP")
    p.add_argument("--env-file", type=Path, help="read RIMI_* settings from a .env file")
    p.add_argument("--host", help="IMAP server (env RIMI_IMAP_HOST)")
    p.add_argument("--port", help="IMAP SSL port (env RIMI_IMAP_PORT, default 993)")
    p.add_argument("--user", help="login (env RIMI_IMAP_USER); password: env RIMI_IMAP_PASSWORD or prompt")
    p.add_argument("--folder", help="folder, full path or last segment (env RIMI_IMAP_FOLDER, default INBOX)")
    p.add_argument("--sender", help="sender filter (default noreply@rimibaltic.com)")
    p.add_argument("--subject", help='subject filter (default "Tavs pirkuma čeks")')
    p.add_argument("--out", help="output directory (env RIMI_OUTPUT_DIR, default ./rimi-receipts)")
    p.add_argument("--since", help="only e-mails since YYYY-MM-DD")
    p.add_argument("--limit", type=int, help="process at most N new e-mails")
    p.add_argument("--dry-run", action="store_true", help="only count matching e-mails")
    p.add_argument("--list-folders", action="store_true", help="list mailbox folders and exit")
    p.set_defaults(func=cmd_fetch)

    p = sub.add_parser("synth", help="generate synthetic sample receipts")
    p.add_argument("--out", type=Path, default=Path("samples"))
    p.add_argument("--count", type=int, default=5)
    p.add_argument("--seed", type=int, default=1)
    p.set_defaults(func=cmd_synth)

    p = sub.add_parser("glyphs", help="maintainer tools for extending the glyph set")
    gsub = p.add_subparsers(dest="action", required=True)
    g = gsub.add_parser("harvest", help="collect unrecognised cells from receipts")
    g.add_argument("receipts", type=Path)
    g.add_argument("work_dir", type=Path)
    g.add_argument("--jobs", type=int, default=None)
    g = gsub.add_parser("review", help="cluster unknown cells and draw contact sheets")
    g.add_argument("work_dir", type=Path)
    g = gsub.add_parser("add", help="add labelled clusters to a glyph file")
    g.add_argument("work_dir", type=Path)
    g.add_argument("labels", help='JSON object {"<cluster id>": "<char>"}')
    g.add_argument("--glyph-file", type=Path, default=Path("src/rimi_receipts/data/glyphs.npz"))
    p.set_defaults(func=cmd_glyphs)
    return ap


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):  # Windows consoles default to a legacy code page
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
