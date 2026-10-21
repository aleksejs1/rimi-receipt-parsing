# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## 0.1.1 — 2026-10-21

First release published on PyPI. No changes to recognition or parsing.

- Release workflow: tag → build → test the built wheel → publish to PyPI (trusted publishing)
  → GitHub Release with the wheel and sdist attached.
- CI builds the distribution and runs the test suite against the built wheel.
- README links and images are absolute, so they work on PyPI.
- The version is defined once, in `rimi_receipts.__version__`.

## 0.1.0 — 2026-10-21

First public release (GitHub only).

- Recognition of Rimi Latvia e-receipt PDFs by template matching on the character grid
  (line finding by dynamic programming, two-pass decoding of overlapping accents).
- Parser for items (pieces and weight), item and receipt-level discounts, corrections, coupons,
  deposits, VAT table, payments (card, cash with change, deposit coupons) and the Mans Rimi block.
- Validation of every receipt against its own sums.
- `rimi-receipts` CLI: `parse`, `check`, `fetch` (IMAP download), `synth` (synthetic receipts),
  `glyphs` (template maintenance).
- Synthetic samples and a test suite; optional regression test against a local archive.
