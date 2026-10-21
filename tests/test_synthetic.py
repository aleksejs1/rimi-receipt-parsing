from __future__ import annotations

from pathlib import Path

import pytest

from rimi_receipts import parse_pdf, recognize_pdf
from rimi_receipts.synth import generate, render, to_pdf

SAMPLES = sorted((Path(__file__).parent.parent / "samples").glob("*.pdf"))


def _normalise(lines: list[str]) -> list[str]:
    # centred lines carry leading spaces; "0" and "O" are the same glyph
    return [line.strip().replace("O", "0") for line in lines if line.strip()]


@pytest.mark.parametrize("seed", range(12))
def test_generated_receipt_round_trip(seed: int) -> None:
    synthetic = generate(seed)
    pdf = to_pdf(render(synthetic))
    lines = [line.text for line in recognize_pdf(pdf) if not line.unknown_cols]
    assert _normalise(lines) == _normalise(synthetic.body_lines)
    receipt = parse_pdf(pdf)
    assert receipt.validate() == []
    assert receipt.total_cents == synthetic.total_cents


def test_samples_are_present() -> None:
    assert len(SAMPLES) >= 3


@pytest.mark.parametrize("pdf", SAMPLES, ids=lambda p: p.name)
def test_committed_samples(pdf: Path) -> None:
    receipt = parse_pdf(pdf)
    assert receipt.validate() == []
    expected = pdf.with_suffix(".txt").read_text(encoding="utf-8").splitlines()
    # the .txt holds every line; large-font lines are not part of the recognised body
    assert set(_normalise(receipt.raw_lines)) <= set(_normalise(expected))
