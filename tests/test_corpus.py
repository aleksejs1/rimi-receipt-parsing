"""
Regression test against a private archive of real receipts.

Real receipts contain personal data and are never committed. Point
``RIMI_CORPUS_DIR`` at a folder of downloaded PDFs (e.g. the output of
``rimi-receipts fetch``) to run it:

    RIMI_CORPUS_DIR=~/rimi-receipts pytest tests/test_corpus.py
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from rimi_receipts import parse_pdf

CORPUS = os.environ.get("RIMI_CORPUS_DIR")
PDFS = sorted(Path(CORPUS).expanduser().rglob("*.pdf")) if CORPUS else []


@pytest.mark.skipif(not CORPUS, reason="set RIMI_CORPUS_DIR to run against real receipts")
@pytest.mark.parametrize("pdf", PDFS, ids=lambda p: p.name)
def test_real_receipt_adds_up(pdf: Path) -> None:
    assert parse_pdf(pdf).validate() == []
