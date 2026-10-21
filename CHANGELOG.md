# Changelog

## 0.1.0 — 2026-10-21

First public release.

- Recognition of Rimi Latvia e-receipt PDFs by template matching on the character grid
  (line finding by dynamic programming, two-pass decoding of overlapping accents).
- Parser for items (pieces and weight), item and receipt-level discounts, corrections, coupons,
  deposits, VAT table, payments (card, cash with change, deposit coupons) and the Mans Rimi block.
- Validation of every receipt against its own sums.
- `rimi-receipts` CLI: `parse`, `check`, `fetch` (IMAP download), `synth` (synthetic receipts),
  `glyphs` (template maintenance).
- Synthetic samples and a test suite; optional regression test against a local archive.
