"""
Geometry of a Rimi e-receipt image.

The PDF attached to a Rimi e-receipt e-mail contains a single JPEG, 346 px wide,
rendered by the cash register (it is not a scan). The body text uses a monospaced
font laid out on a fixed grid:

* 40 columns, 8 px each, starting at ``x = 5``. The first and last pixel column of
  every cell is the inter-character gap.
* Lines are 12 px apart. Inside a cell, row 0 holds dots and small accents, rows
  1..8 hold capitals down to the baseline (row 8), rows 9..11 hold descenders.
* Accents above capitals (``Š``, ``Ā``, ``Č`` ...) reach rows -2..-1, so a glyph is
  14 px tall and overlaps the neighbouring lines by two rows on each side.
* Large headings (logo, "Tavs ietaupījums", "Samaksai EUR") break the vertical
  phase of the grid, and centred lines are centred by pixel, so every line has its
  own vertical position and a horizontal phase of 0..7 px.
"""

from __future__ import annotations

import numpy as np

COLS = 40
CELL_W = 8
CELL_H = 12
GLYPH_TOP = -2  # first glyph row relative to the line top (accents above capitals)
GLYPH_H = 14  # glyph rows -2..11
X0 = 5
X_PHASES = tuple(range(CELL_W))

# Glyph row ranges in array coordinates (array row 0 == glyph row -2).
CORE = slice(2, 12)  # rows 0..9: never touched by neighbouring lines
TOP = slice(0, 2)  # rows -2..-1: shared with the descenders of the line above
BOTTOM = slice(12, 14)  # rows 10..11: shared with the capital accents of the line below


def line_cells(ink: np.ndarray, top: int, dx: int = 0) -> np.ndarray:
    """
    Cut the line whose top is at ``top`` with horizontal phase ``dx`` into 40 glyph
    cells. Returns an array of shape ``(40, 14, 8)``; cells beyond the page are blank.
    """
    h, w = ink.shape
    start = top + GLYPH_TOP
    x_start = X0 + dx
    band = np.zeros((GLYPH_H, COLS * CELL_W), dtype=np.float32)
    y0, y1 = max(start, 0), min(start + GLYPH_H, h)
    x1 = min(x_start + COLS * CELL_W, w)
    if y1 > y0 and x1 > x_start:
        band[y0 - start : y1 - start, : x1 - x_start] = ink[y0:y1, x_start:x1]
    return band.reshape(GLYPH_H, COLS, CELL_W).transpose(1, 0, 2)


def paint_glyph(page: np.ndarray, glyph: np.ndarray, top: int, dx: int, col: int) -> None:
    """Draw a glyph onto ``page`` in place (pixel-wise maximum)."""
    h, w = page.shape
    y0 = top + GLYPH_TOP
    x0 = X0 + dx + col * CELL_W
    ys, ye = max(y0, 0), min(y0 + GLYPH_H, h)
    xe = min(x0 + CELL_W, w)
    if ye > ys and xe > x0:
        region = page[ys:ye, x0:xe]
        np.maximum(region, glyph[ys - y0 : ye - y0, : xe - x0], out=region)
