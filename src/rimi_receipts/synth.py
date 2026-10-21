"""
Synthetic receipts for tests, demos and documentation.

The generator lays out a receipt in the same format as a real Rimi e-receipt and
renders it with the bundled glyph templates into a JPEG-in-PDF, so the whole
pipeline (line finding, centred lines, overlapping accents, large headings that
break the grid) is exercised without any real — and therefore personal — data.

Everything that could identify a person or a shop is fictional: the "logo" is the
word SAMPLE, the store and company are made up, and all card numbers, terminal
IDs and document numbers are random.
"""

from __future__ import annotations

import io
import random
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import numpy as np
from PIL import Image

from .glyphs import Glyphs, default_glyphs
from .grid import CELL_H, CELL_W, COLS, GLYPH_TOP, X0

PAGE_W = 346
WIDTH = COLS
NAME_WIDTH = 30  # item names are wrapped at 30 characters on real receipts

# (name, price in cents, VAT class, unit). Classes: A 21 %, B 21 % (alcohol), C 12 %, F 5 %.
CATALOGUE: list[tuple[str, int, str, str]] = [
    ("Piens Rimi 2,5% 1l", 109, "A", "gab"),
    ("Maize rudzu Rimi 400g", 135, "A", "gab"),
    ("Biezpiens Rimi 9% 180g", 119, "A", "gab"),
    ("Jogurts ar zemenēm 2% 380g", 159, "A", "gab"),
    ("Siers Holandes šķēlēs 150g", 249, "A", "gab"),
    ("Sviests 82% 200g", 329, "A", "gab"),
    ("Olas M izmēra 10gab.", 279, "A", "gab"),
    ("Vistas fileja atdzesēta 500g", 489, "A", "gab"),
    ("Cūkgaļa maltā Rimi 400g", 349, "A", "gab"),
    ("Makaroni spirālītes 500g", 99, "A", "gab"),
    ("Rīsi garengraudu 1kg", 189, "A", "gab"),
    ("Sula ābolu 100% 1l", 219, "A", "gab"),
    ("Čipsi ar sāli 130g", 189, "A", "gab"),
    ("Žāvētas aprikozes 200g", 299, "A", "gab"),
    ("Zaļā tēja 20x1,5g", 159, "A", "gab"),
    ("Cepumi auzu ar rozīnēm 300g", 149, "A", "gab"),
    ("Ievārījums upeņu 400g", 229, "A", "gab"),
    ("Kafija malta Brazīlija 250g", 549, "A", "gab"),
    ("Šokolāde piena ar riekstiem 100g", 179, "A", "gab"),
    ("Konservēti zirnīši ar burkāniem Rimi 400g", 115, "A", "gab"),
    ("Tualetes papīrs 3 kārtas 8gab.", 329, "A", "gab"),
    ("Zobu pasta Mint 75ml", 199, "A", "gab"),
    ("Alus gaišais 4,5% 0,5l", 139, "B", "gab"),
    ("Sidrs ābolu 4,7% 0,5l", 169, "B", "gab"),
    ("Banāni kg", 139, "F", "kg"),
    ("Āboli Gala 1. šķira kg", 199, "F", "kg"),
    ("Tomāti ķekaros kg", 399, "F", "kg"),
    ("Gurķi garie kg", 299, "F", "kg"),
    ("Kartupeļi jaunie kg", 89, "F", "kg"),
    ("Burkāni kg", 79, "F", "kg"),
    ("Mandarīni kg", 249, "F", "kg"),
    ("Grieķu jogurts 10% 150g", 99, "C", "gab"),
]
DEPOSIT_ITEMS = {"Alus gaišais 4,5% 0,5l", "Sidrs ābolu 4,7% 0,5l", "Sula ābolu 100% 1l"}
VAT_RATES = {"A": Decimal(21), "B": Decimal(21), "C": Decimal(12), "D": Decimal(0), "F": Decimal(5)}


def money(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    return f"{sign}{abs(cents) // 100},{abs(cents) % 100:02d}"


def right(left: str, value: str, width: int = WIDTH) -> str:
    return left + value.rjust(width - len(left))


@dataclass
class Block:
    """One element of the layout."""

    kind: str  # "text", "big", "gap"
    text: str = ""
    align: str = "left"  # left / center
    scale: tuple[int, int] = (1, 1)  # (vertical, horizontal) for "big"
    height: int = 0  # for "gap"
    big_right: str = ""  # "text" only: a large (2×) value at the right end, e.g. "Samaksai EUR  16,06"

    @property
    def line_height(self) -> int:
        if self.kind == "gap":
            return self.height
        if self.kind == "big":
            return CELL_H * self.scale[0]
        return CELL_H * (2 if self.big_right else 1)


@dataclass
class SyntheticReceipt:
    blocks: list[Block] = field(default_factory=list)
    total_cents: int = 0

    @property
    def body_lines(self) -> list[str]:
        """The body-font lines a perfect recogniser would return (empty lines dropped)."""
        # a line with a large value is not readable as body text (just like on real receipts)
        return [
            b.text.rstrip() for b in self.blocks if b.kind == "text" and b.text.strip() and not b.big_right
        ]

    def text(self) -> str:
        return "\n".join(b.text for b in self.blocks if b.kind != "gap")


def _wrap(name: str, width: int = NAME_WIDTH) -> list[str]:
    lines, current = [], ""
    for word in name.split():
        if current and len(current) + 1 + len(word) > width:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    lines.append(current)
    return lines


def generate(seed: int = 0) -> SyntheticReceipt:
    """Generate a random, internally consistent receipt layout."""
    rnd = random.Random(seed)
    r = SyntheticReceipt()
    t = r.blocks.append

    def line(text: str = "", align: str = "left") -> None:
        if len(text) > WIDTH:
            raise ValueError(f"line longer than {WIDTH}: {text!r}")
        t(Block("text", text, align))

    register = rnd.randint(1, 9)
    issued = f"20{rnd.randint(24, 26)}-{rnd.randint(1, 12):02d}-{rnd.randint(1, 28):02d}"
    clock = f"{rnd.randint(8, 21):02d}:{rnd.randint(0, 59):02d}:{rnd.randint(0, 59):02d}"
    receipt_no = f"0{register:02d}{rnd.randint(10000, 99999)}"

    # header
    t(Block("gap", height=6))
    t(Block("big", "SAMPLE", "center", scale=(3, 2)))
    t(Block("gap", height=10))
    line("SIA PARAUGS", "center")
    line("Jur. adrese: Parauga iela 1, Rīga", "center")
    line("Example Store (Rīga)", "center")
    line(f"Kase Nr. {register:02d}", "center")
    line("PVN maksātāja numurs: LV00000000000", "center")
    line("Šasijas numurs: SP-LV00000", "center")
    line("---------------- Čeks ------------------")
    line("--------- Elektroniska izdruka ---------")
    line(right("KLIENTS:", "X" * 15 + f"{rnd.randint(0, 9999):04d}", 39))
    line("-" * WIDTH)

    # items
    totals: dict[str, int] = {}
    item_discounts: list[tuple[str, int]] = []
    items_total = 0
    chosen = rnd.sample(CATALOGUE, rnd.randint(4, 9))
    for idx, (name, price, vat, unit) in enumerate(chosen):
        if unit == "kg":
            qty = Decimal(rnd.randint(150, 2200)) / 1000
            amount = int((qty * price).quantize(Decimal(1), rounding=ROUND_HALF_UP))
            qty_line = f" {qty:.3f} kg X {money(price)} EUR/kg".replace(".", ",", 1)
        else:
            pieces = rnd.choice([1, 1, 1, 2, 3])
            amount = pieces * price
            qty_line = f" {pieces} gab X {money(price)} EUR"
        for part in _wrap(name):
            line(part)
        line(right(qty_line, f"{money(amount)} {vat}"))
        discount = 0
        if rnd.random() < 0.4:
            discount = -max(5, (amount * rnd.choice([10, 20, 25, 30])) // 100)
            line(f" Atl. {money(discount)}   Gala cena {money(amount + discount)}")
            item_discounts.append((name, discount))
        totals[vat] = totals.get(vat, 0) + amount + discount
        items_total += amount + discount
        if name in DEPOSIT_ITEMS:
            line("Depozīta maksa")
            line(right(" 1 gab X 0,10 EUR", "0,10 D"))
            totals["D"] = totals.get("D", 0) + 10
            items_total += 10
        if idx == 1 and rnd.random() < 0.3:  # a scanned coupon
            line(f"Kupons 99600000{rnd.randint(10000, 99999)}")
            line(" 1 gab.")
        if idx == 2 and unit == "gab" and discount == 0 and rnd.random() < 0.3:  # scanned twice, then voided
            for part in _wrap(name):
                line(part)
            line(right(qty_line, f"{money(amount)} {vat}"))
            line("--------------Korekcija-----------------")
            for part in _wrap(name):
                line(part)
            line(right(qty_line, f"{money(-amount)} {vat}"))
    line("-" * WIDTH)

    # discounts: some listed by item name, the rest summed as "Citas akcijas"
    receipt_level = -min(rnd.choice([0, 0, 30, 50, 120]), items_total // 2)
    if item_discounts or receipt_level:
        line("ATLAIDES:")
        named = [d for d in item_discounts if rnd.random() < 0.5 and len(d[0]) <= 31]
        other = sum(a for d, a in item_discounts if (d, a) not in named)
        if other:
            line(right("Citas akcijas", money(other), 38))
        for name, amount in named:
            line(right(name, money(amount), 38))
        if receipt_level:
            line(right("Izmantotā Mans Rimi nauda", money(receipt_level), 38))
        line(" " * 30 + "-" * 10)
        saved = -sum(a for _, a in item_discounts) - receipt_level
        t(Block("gap", height=2))
        t(Block("big", right("Tavs ietaupījums", money(saved), 38), "left", scale=(2, 1)))
        t(Block("gap", height=3))
        line("-" * WIDTH)
    total = items_total + receipt_level
    r.total_cents = total
    if receipt_level:  # receipt-level discounts reduce the VAT base of the largest class
        biggest = max(totals, key=lambda k: totals[k])
        totals[biggest] += receipt_level

    # payment
    method = rnd.choice(["card", "card", "cash"])
    payments: list[tuple[str, int]] = []
    if method == "card":
        payments.append(("Bankas karte", total))
        line("Maksājumu karte")
        line("Apmaksa")
        line("BEZKONTAKTA KARTE")
        line("VISA BEZKONTAKTA")
        line(right("BANKAS KVĪTS NR.", f"{rnd.randint(100000, 999999)}"))
        line(right("TERMINĀLA ID", "00000000"))
        line(right("TIRGOTĀJA ID", "0000000"))
        line(right("LAIKS", f"{issued} {clock}"))
        line(right("Visa", "*" * 12 + "0000"))
        line(right("KOPĀ:", f"{money(total)} EUR"))
        line(right("Autorizācijas Nr", f"{rnd.randint(100000, 999999)}        T:1"))
        line("SAGLABĀJIET DOKUMENTU KONTA PĀRBAUDEI")
        line("-" * WIDTH)
    else:
        given = next(n for n in (500, 1000, 2000, 5000, 10000, 20000) if n >= total)
        payments += [("Skaidra nauda", given), ("Atlikums", given - total)]

    line(right("Nopelnītā Mans Rimi nauda", money(max(1, total // 100)), 40))
    line(right("Mans Rimi naudas uzkrājums", money(rnd.randint(10, 900)), 40))
    line("Ietaupījums ar Mans Rimi karti")
    line(right("šomēnes", money(rnd.randint(50, 4000)), 40))
    line("-" * WIDTH)
    t(Block("gap", height=4))
    t(Block("text", "Samaksai EUR", big_right=money(total)))
    t(Block("gap", height=5))
    line("-" * WIDTH)

    line("Nodoklis      Ar PVN   Bez PVN PVN summa")
    for cls in sorted(totals):
        gross = totals[cls]
        net = int(
            (Decimal(gross) * 100 / (100 + VAT_RATES[cls])).quantize(Decimal(1), rounding=ROUND_HALF_UP)
        )
        rate = f"{VAT_RATES[cls]},00".rjust(5)
        line(f"{cls} {rate} %" + money(gross).rjust(11) + money(net).rjust(10) + money(gross - net).rjust(10))
    for label, amount in payments:
        line(right(label, money(amount)))
    line("-" * WIDTH)
    line(f"Dok. Nr.: {rnd.randint(1, 200)}/{rnd.randint(10000, 299999)} Kase {register:04d}")
    line(f"FB numurs: 0{rnd.randint(10**13, 10**14 - 1)}")
    line(f"#{receipt_no}".rjust(WIDTH))
    line()
    line(f"  {issued} {clock}")
    line("".join(rnd.choice("0123456789abcdef") for _ in range(WIDTH)))
    line("".join(rnd.choice("0123456789abcdef") for _ in range(WIDTH)))
    t(Block("gap", height=8))
    return r


def _glyph_for(char: str, glyphs: Glyphs) -> np.ndarray:
    key = "0" if char == "O" else char  # 0 and O share one template
    if key not in glyphs.chars:
        raise ValueError(f"no glyph template for {char!r}")
    return glyphs.image(key)


def render(receipt: SyntheticReceipt, glyphs: Glyphs | None = None) -> Image.Image:
    """Render a layout into a receipt image (RGB, 346 px wide)."""
    glyphs = glyphs or default_glyphs()
    height = sum(b.line_height for b in receipt.blocks)
    ink = np.zeros((height + 4, PAGE_W), dtype=np.float32)

    def draw(text: str, x: int, y: int, sy: int, sx: int) -> None:
        for i, ch in enumerate(text):
            if ch == " ":
                continue
            glyph = np.kron(_glyph_for(ch, glyphs), np.ones((sy, sx), dtype=np.float32))
            gy, gx = y + GLYPH_TOP * sy, x + i * CELL_W * sx
            ys, ye = max(gy, 0), min(gy + glyph.shape[0], ink.shape[0])
            xe = min(gx + glyph.shape[1], PAGE_W)
            region = ink[ys:ye, gx:xe]
            np.maximum(region, glyph[ys - gy : ye - gy, : xe - gx], out=region)

    y = 2
    for b in receipt.blocks:
        if b.kind == "gap":
            y += b.height
            continue
        sy, sx = b.scale if b.kind == "big" else (1, 1)
        text = b.text.rstrip()
        x = X0 if b.align == "left" else (PAGE_W - len(text) * CELL_W * sx) // 2
        if b.big_right:
            # label in the body font on the lower half, the value 2× tall and wide above it
            draw(text, x, y + CELL_H, 1, 1)
            draw(b.big_right, X0 + (COLS - 1 - 2 * len(b.big_right)) * CELL_W, y, 2, 2)
        else:
            draw(text, x, y, sy, sx)
        y += b.line_height
    gray = (255 * (1 - np.clip(ink, 0, 1))).round().astype(np.uint8)
    return Image.fromarray(gray).convert("RGB")


def to_pdf(image: Image.Image, quality: int = 75) -> bytes:
    """Wrap the image into a one-page PDF the same way the cash register does (JPEG, 72 dpi)."""
    buf = io.BytesIO()
    image.save(buf, "PDF", resolution=72.0, quality=quality)
    return buf.getvalue()


def write_samples(out_dir: str | Path, count: int = 5, seed: int = 1) -> list[Path]:
    """Write ``count`` synthetic receipts as ``sample-NN.pdf`` plus their text as ``sample-NN.txt``."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    for n in range(count):
        receipt = generate(seed + n)
        pdf = out / f"sample-{n + 1:02d}.pdf"
        pdf.write_bytes(to_pdf(render(receipt)))
        (out / f"sample-{n + 1:02d}.txt").write_text(receipt.text() + "\n", encoding="utf-8")
        paths.append(pdf)
    return paths
