"""
Offline parser for Rimi Latvia e-receipts.

    >>> from rimi_receipts import parse_pdf
    >>> receipt = parse_pdf("samples/sample-01.pdf")
    >>> receipt.total_cents, receipt.validate()
    (2294, [])
"""

from __future__ import annotations

from pathlib import Path
from typing import BinaryIO

from .glyphs import Glyphs, default_glyphs
from .ocr import RecognizedLine, recognize
from .parser import Discount, Item, LoyaltyLine, Payment, Receipt, VatLine, parse_lines, validate
from .pdf import NotARimiReceiptError, load_image, load_ink

__version__ = "0.1.0"

# Characters recognised with a smaller margin than this are reported in
# Receipt.low_confidence (on ~1000 real receipts: about 0.04 % of characters).
LOW_CONFIDENCE_MARGIN = 1.0


def recognize_pdf(
    source: str | Path | bytes | BinaryIO, glyphs: Glyphs | None = None
) -> list[RecognizedLine]:
    """Recognise the body text of a receipt PDF, line by line."""
    return recognize(load_ink(source), glyphs)


def parse_pdf(source: str | Path | bytes | BinaryIO, glyphs: Glyphs | None = None) -> Receipt:
    """Recognise and parse a receipt PDF. Call ``receipt.validate()`` to check its sums."""
    lines = recognize_pdf(source, glyphs)
    receipt = parse_lines(line.text for line in lines)
    receipt.raw_lines = [line.text for line in lines if line.text.strip() and not line.unknown_cols]
    receipt.low_confidence = [
        f"{line.text.strip()!r}: {line.chars[col]!r} (column {col + 1})"
        for line in lines
        if not line.unknown_cols
        for col, margin in enumerate(line.margins)
        if margin < LOW_CONFIDENCE_MARGIN
    ]
    return receipt


__all__ = [
    "Discount",
    "Glyphs",
    "Item",
    "LoyaltyLine",
    "NotARimiReceiptError",
    "Payment",
    "Receipt",
    "RecognizedLine",
    "VatLine",
    "default_glyphs",
    "load_image",
    "load_ink",
    "parse_lines",
    "parse_pdf",
    "recognize",
    "recognize_pdf",
    "validate",
]
