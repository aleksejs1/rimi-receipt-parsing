"""
Text recognition by matching grid cells against glyph templates.

1. **Line finding.** For every vertical position ``y`` and horizontal phase the
   cost of "a text line starts here" is the sum of distances between its 40 cells
   and their nearest templates, computed on the glyph core (rows 0..9, which no
   neighbouring line touches). Dynamic programming then picks non-overlapping lines
   (at least 12 px apart) that minimise line costs plus a penalty for ink left
   uncovered. The logo and the large headings stay uncovered: they do not match the
   body font, and every number printed in them is repeated in the body text.
2. **Decoding, pass 1 (top-down).** In rows -2..-1 of a cell the already decoded
   line above is subtracted; in rows 10..11 only missing ink is penalised, because
   the accents of the next line's capitals may live there.
3. **Decoding, pass 2+.** Both neighbours are now known. Adjacent lines always have
   different parity, so their contribution is read from a page rendered with lines
   of the opposite parity, subtracted, and the full 14 rows are compared.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .glyphs import Glyphs, default_glyphs
from .grid import BOTTOM, CELL_H, CELL_W, COLS, CORE, TOP, X0, X_PHASES, line_cells, paint_glyph

UNKNOWN_CHAR = "�"
BLANK_MAX = 0.5  # a cell is blank when no core pixel is darker than this
UNKNOWN_COST = 6.0  # L1 distance above which a cell is reported as unknown
UNCOVERED_PENALTY = 0.6  # DP penalty per unit of ink not covered by any line
CELL_COST_CAP = 8.0  # one unknown character must not make the DP drop a whole line


@dataclass
class RecognizedLine:
    """One text line of the receipt body."""

    top: int  # y of the line's cell row 0 in the image
    dx: int  # horizontal phase, 0..7 px
    chars: list[str] = field(default_factory=list)  # always 40 entries
    costs: list[float] = field(default_factory=list)  # L1 distance to the chosen template
    # distance gap to the best template of a *different* character; small = uncertain
    margins: list[float] = field(default_factory=list)
    cells: np.ndarray | None = field(default=None, repr=False)

    @property
    def text(self) -> str:
        return "".join(self.chars).rstrip()

    @property
    def unknown_cols(self) -> list[int]:
        return [i for i, c in enumerate(self.chars) if c == UNKNOWN_CHAR]


def _sq_distances(cells: np.ndarray, templates: np.ndarray) -> np.ndarray:
    """Squared L2 distances between cells (M, D) and templates (N, D)."""
    a2 = (cells**2).sum(1)[:, None]
    b2 = (templates**2).sum(1)[None, :]
    return np.maximum(a2 + b2 - 2 * cells @ templates.T, 0.0)


def find_lines(ink: np.ndarray, glyphs: Glyphs) -> list[tuple[int, int]]:
    """Return ``(top, dx)`` for every body-font text line, top to bottom."""
    h = ink.shape[0]
    core = glyphs.images[:, CORE].reshape(len(glyphs.chars), -1)
    core = np.vstack([core, np.zeros((1, core.shape[1]), dtype=np.float32)])  # space
    row_ink = ink[:, X0 : X0 + COLS * CELL_W + X_PHASES[-1]].sum(1)

    line_cost = np.full(h, np.inf)
    line_dx = np.zeros(h, dtype=np.int64)
    for y in range(h - 2):
        if row_ink[y : y + CELL_H].sum() < 1.0:
            continue
        for dx in X_PHASES:
            cells = line_cells(ink, y, dx)[:, CORE].reshape(COLS, -1)
            cost = float(np.minimum(_sq_distances(cells, core).min(1), CELL_COST_CAP).sum())
            if cost < line_cost[y]:
                line_cost[y], line_dx[y] = cost, dx

    # dp[y]: minimal cost of explaining pixel rows [0, y)
    dp = np.full(h + CELL_H + 1, np.inf)
    back: list[tuple[int, int] | None] = [None] * (h + CELL_H + 1)
    dp[0] = 0.0
    for y in range(h):
        if not np.isfinite(dp[y]):
            continue
        skip = dp[y] + UNCOVERED_PENALTY * row_ink[y]
        if skip < dp[y + 1]:
            dp[y + 1], back[y + 1] = skip, (y, -1)
        if np.isfinite(line_cost[y]):
            take = dp[y] + line_cost[y]
            if take < dp[y + CELL_H]:
                dp[y + CELL_H], back[y + CELL_H] = take, (y, int(line_dx[y]))

    lines: list[tuple[int, int]] = []
    y = int(np.argmin(dp[h : h + CELL_H + 1])) + h
    while y > 0 and back[y] is not None:
        prev, dx = back[y]  # type: ignore[misc]
        if dx >= 0:
            lines.append((prev, dx))
        y = prev
    lines.reverse()
    return lines


def decode_lines(
    ink: np.ndarray, glyphs: Glyphs, lines: list[tuple[int, int]], passes: int = 2
) -> list[RecognizedLine]:
    """Decode the characters of the given lines (see the module docstring)."""
    imgs = glyphs.images
    char_arr = np.array(glyphs.chars)
    out = [RecognizedLine(top=top, dx=dx, cells=line_cells(ink, top, dx)) for top, dx in lines]
    picks = [[-1] * COLS for _ in out]  # template index; -1 blank, -2 unknown
    costs = [[0.0] * COLS for _ in out]
    margins = [[float("inf")] * COLS for _ in out]

    def choose(cost: np.ndarray) -> tuple[int, float, float]:
        k = int(cost.argmin())
        if cost[k] > UNKNOWN_COST:
            return -2, float(cost[k]), 0.0
        other = cost[char_arr != glyphs.chars[k]]
        margin = float(other.min() - cost[k]) if len(other) else float("inf")
        return k, float(cost[k]), margin

    # pass 1: top-down
    predicted = np.zeros_like(ink)
    for i, line in enumerate(out):
        assert line.cells is not None
        above = line_cells(predicted, line.top, line.dx)
        for col in range(COLS):
            c = line.cells[col]
            if c[CORE].max() < BLANK_MAX:
                continue
            residual_top = np.clip(c[TOP] - above[col][TOP], 0, 1)
            cost = (
                np.abs(imgs[:, CORE] - c[CORE]).sum((1, 2))
                + np.abs(imgs[:, TOP] - residual_top).sum((1, 2))
                + np.clip(imgs[:, BOTTOM] - c[BOTTOM], 0, None).sum((1, 2))
            )
            picks[i][col], costs[i][col], margins[i][col] = choose(cost)
            if picks[i][col] >= 0:
                paint_glyph(predicted, imgs[picks[i][col]], line.top, line.dx, col)

    # pass 2+: both neighbours known
    for _ in range(passes - 1):
        pages = [np.zeros_like(ink), np.zeros_like(ink)]
        for i, line in enumerate(out):
            for col, k in enumerate(picks[i]):
                if k >= 0:
                    paint_glyph(pages[i % 2], imgs[k], line.top, line.dx, col)
        for i, line in enumerate(out):
            assert line.cells is not None
            neighbours = line_cells(pages[1 - i % 2], line.top, line.dx)
            for col in range(COLS):
                c = line.cells[col]
                if c[CORE].max() < BLANK_MAX:
                    continue
                residual = c.copy()
                residual[TOP] = np.clip(c[TOP] - neighbours[col][TOP], 0, 1)
                residual[BOTTOM] = np.clip(c[BOTTOM] - neighbours[col][BOTTOM], 0, 1)
                cost = np.abs(imgs - residual).sum((1, 2))
                picks[i][col], costs[i][col], margins[i][col] = choose(cost)

    for i, line in enumerate(out):
        line.chars = [" " if k == -1 else UNKNOWN_CHAR if k == -2 else glyphs.chars[k] for k in picks[i]]
        line.costs = costs[i]
        line.margins = margins[i]
    return out


def recognize(ink: np.ndarray, glyphs: Glyphs | None = None) -> list[RecognizedLine]:
    """Find and decode all body-font lines of a receipt image."""
    glyphs = glyphs or default_glyphs()
    return decode_lines(ink, glyphs, find_lines(ink, glyphs))
