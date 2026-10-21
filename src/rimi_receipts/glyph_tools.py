"""
Maintainer tools for extending the glyph set.

If Rimi starts printing a character the bundled set does not know, recognition
marks it as ``\\ufffd`` and the receipt fails validation. To teach it:

1. ``rimi-receipts glyphs harvest <receipts-dir> <work-dir>`` collects unknown cells
   from lines that are otherwise recognised (logo and large headings are skipped);
2. ``rimi-receipts glyphs review <work-dir>`` clusters them and draws contact sheets
   (``unknown-NN.png``): each cluster as an enlarged tile, its id, size and a sample
   of the line it came from;
3. ``rimi-receipts glyphs add <work-dir> '{"<cluster id>": "<char>", ...}'`` adds the
   labelled clusters (median image) to a glyph file.

Leave clusters that are parts of large headings unlabelled.
"""

from __future__ import annotations

import json
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .glyphs import Glyphs, default_glyphs
from .grid import CORE
from .ocr import recognize
from .pdf import load_ink


def _harvest_one(pdf: Path) -> list[tuple[np.ndarray, str]]:
    found = []
    for line in recognize(load_ink(pdf), default_glyphs()):
        filled = [c for c in line.chars if c != " "]
        if not filled or len(line.unknown_cols) > len(filled) / 2:
            continue  # logo or a large heading
        text = "".join(line.chars)
        for col in line.unknown_cols:
            assert line.cells is not None
            context = (text[:col] + "[?]" + text[col + 1 :]).rstrip()
            found.append((line.cells[col], f"{pdf.name}: {context}"))
    return found


def harvest(receipts_dir: Path, work_dir: Path, jobs: int | None = None) -> int:
    work_dir.mkdir(parents=True, exist_ok=True)
    pdfs = sorted(receipts_dir.rglob("*.pdf"))
    cells, contexts = [], []
    with ProcessPoolExecutor(max_workers=jobs) as pool:
        for found in pool.map(_harvest_one, pdfs, chunksize=4):
            for cell, ctx in found:
                cells.append(cell)
                contexts.append(ctx)
    np.save(work_dir / "unknown_cells.npy", np.array(cells, dtype=np.float32).reshape(-1, 14, 8))
    (work_dir / "unknown_context.json").write_text(json.dumps(contexts, ensure_ascii=False), encoding="utf-8")
    return len(cells)


def review(work_dir: Path, threshold: float = 3.0, per_sheet: int = 30) -> int:
    cells = np.load(work_dir / "unknown_cells.npy")
    contexts = json.loads((work_dir / "unknown_context.json").read_text(encoding="utf-8"))
    core = cells[:, CORE].reshape(len(cells), -1)
    reps: list[np.ndarray] = []
    members: list[list[int]] = []
    for i, v in enumerate(core):  # leader clustering on the glyph core
        if reps:
            d = np.abs(np.array(reps) - v).sum(1)
            j = int(d.argmin())
            if d[j] < threshold:
                members[j].append(i)
                continue
        reps.append(v)
        members.append([i])
    order = sorted(range(len(reps)), key=lambda k: -len(members[k]))
    (work_dir / "clusters.json").write_text(json.dumps(members), encoding="utf-8")

    font = ImageFont.load_default(size=13)
    scale, row_h = 3, 14 * 3 + 6
    for sheet, start in enumerate(range(0, len(order), per_sheet)):
        ids = order[start : start + per_sheet]
        img = Image.new("RGB", (900, len(ids) * row_h), "white")
        draw = ImageDraw.Draw(img)
        for n, k in enumerate(ids):
            tile = np.median(cells[members[k]], 0)
            y = n * row_h
            img.paste(
                Image.fromarray((255 - tile * 255).astype(np.uint8)).resize(
                    (8 * scale, 14 * scale), Image.NEAREST
                ),
                (0, y),
            )
            draw.text((32, y + 2), f"cluster {k}  ×{len(members[k])}", fill=(0, 0, 200), font=font)
            draw.text((32, y + 20), contexts[members[k][0]][:100], fill=(0, 0, 0), font=font)
        img.save(work_dir / f"unknown-{sheet:02d}.png")
    return len(order)


def add(work_dir: Path, labels: dict[str, str], glyph_file: Path) -> Glyphs:
    cells = np.load(work_dir / "unknown_cells.npy")
    members = json.loads((work_dir / "clusters.json").read_text(encoding="utf-8"))
    glyphs = Glyphs.load(glyph_file) if glyph_file.exists() else Glyphs.load()
    for cluster, char in labels.items():
        glyphs.add(char, np.median(cells[members[int(cluster)]], 0))
    glyphs.save(glyph_file)
    return glyphs
