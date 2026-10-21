"""
Turning recognised receipt text into structured data, and validating it.

All money amounts are integers in euro cents, so every check is exact.
"""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from .ocr import UNKNOWN_CHAR

MONEY = r"-?\d+,\d{2}"
LETTER = r"A-Za-zĀ-žÀ-ÿ"

RE_QTY = re.compile(
    rf"^ (?P<qty>\d+(?:,\d+)?) (?P<unit>gab|kg) X (?P<price>{MONEY}) EUR(?:/kg)?"
    rf"\s+(?P<amount>{MONEY}) (?P<vat>[A-Z])$"
)
RE_ITEM_DISCOUNT = re.compile(rf"^ Atl\. (?P<disc>{MONEY})\s+Gala cena (?P<final>{MONEY})$")
RE_TRAILING_MONEY = re.compile(rf"^(?P<label>.*?)\s+(?P<amount>{MONEY})$")
RE_CARD_TOTAL = re.compile(rf"^K[0O]PĀ:\s+(?P<total>{MONEY}) EUR$")
RE_VAT = re.compile(
    rf"^(?P<cls>[A-Z])\s+(?P<rate>\d+,\d{{2}}) %\s+(?P<gross>{MONEY})\s+(?P<net>{MONEY})\s+(?P<vat>{MONEY})$"
)
RE_RECEIPT_NO = re.compile(r"^\s*#(?P<no>\d+)$")
RE_DATETIME = re.compile(r"^\s*(?P<dt>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})$")
RE_REGISTER = re.compile(r"^\s*Kase Nr\. (?P<no>\d+)$")
RE_DOCUMENT = re.compile(r"^Dok\. Nr\.: (?P<doc>\S+) Kase (?P<register>\d+)$")
RE_LOYALTY_CARD = re.compile(r"^KLIENTS:\s+(?P<card>\S+)$")
RE_SEPARATOR = re.compile(r"^\s*-{10,}$|^-+ (?:Čeks|Elektroniska izdruka) -+$")
RE_CORRECTION = re.compile(r"^-+Korekcija-+$")
RE_COUPON_QTY = re.compile(r"^ \d+ gab\.$")
RE_MULTIBUY = re.compile(r"^MM \d+\+ ")
# Discounts that are not tied to items: paying with Mans Rimi money, euro coupons.
RE_RECEIPT_LEVEL_DISCOUNT = re.compile(r"^Izmantot")
# In the receipt font "0" and "O" are identical; inside a word with no digit
# neighbours it is the letter.
RE_LETTER_O = re.compile(rf"(?<![\d,.])0(?![\d,.])(?=[{LETTER}])|(?<=[{LETTER}])0(?![\d,.])")

CHANGE_LABEL = "Atlikums"  # cash change, subtracted from payments
CARD_LABEL = "Bankas karte"


def to_cents(text: str) -> int:
    """``'-1,23'`` → ``-123``."""
    sign = -1 if text.startswith("-") else 1
    whole, frac = text.lstrip("-").split(",")
    return sign * (int(whole) * 100 + int(frac))


def restore_letter_o(text: str) -> str:
    """Replace ``0`` with ``O`` where it is clearly a letter (``K0PĀ`` → ``KOPĀ``)."""
    return RE_LETTER_O.sub("O", text)


@dataclass
class Item:
    name: str
    quantity: Decimal  # pieces for "gab", kilograms for "kg"
    unit: str  # "gab" or "kg"
    unit_price_cents: int
    amount_cents: int  # as printed; negative for corrections
    vat_class: str
    discount_cents: int = 0  # negative for a discount
    final_price_cents: int | None = None  # "Gala cena", printed only when discounted
    is_correction: bool = False  # cancels a previously scanned item

    @property
    def paid_cents(self) -> int:
        """What the item finally cost (after its own discount)."""
        return self.amount_cents + self.discount_cents


@dataclass
class Discount:
    label: str
    amount_cents: int  # negative
    receipt_level: bool  # True for Mans Rimi money / coupons, False for item promotions


@dataclass
class VatLine:
    vat_class: str
    rate: Decimal  # percent
    gross_cents: int
    net_cents: int
    vat_cents: int


@dataclass
class Payment:
    method: str  # "Bankas karte", "Skaidra nauda", "Depozīta kupons", "Atlikums" (change) ...
    amount_cents: int


@dataclass
class LoyaltyLine:
    label: str  # e.g. "Nopelnītā Mans Rimi nauda" (Mans Rimi money earned with this purchase)
    amount_cents: int


@dataclass
class Receipt:
    receipt_number: str | None = None  # "#07123456" → "07123456"
    issued_at: dt.datetime | None = None
    register: str | None = None  # "Kase Nr."
    document_number: str | None = None  # "Dok. Nr."
    store: str | None = None
    loyalty_card: str | None = None  # masked, as printed
    items: list[Item] = field(default_factory=list)
    coupons: list[str] = field(default_factory=list)
    discounts: list[Discount] = field(default_factory=list)
    vat: list[VatLine] = field(default_factory=list)
    payments: list[Payment] = field(default_factory=list)
    card_total_cents: int | None = None  # "KOPĀ" on the card slip: the card payment only
    loyalty: list[LoyaltyLine] = field(default_factory=list)  # Mans Rimi summary block
    unparsed_lines: list[str] = field(default_factory=list)
    parse_problems: list[str] = field(default_factory=list)
    # filled by parse_pdf(): body text and characters recognised with a small margin
    raw_lines: list[str] = field(default_factory=list)
    low_confidence: list[str] = field(default_factory=list)

    @property
    def total_cents(self) -> int:
        """Receipt total: items plus all discounts (matches the VAT table and payments)."""
        return sum(i.amount_cents for i in self.items) + sum(d.amount_cents for d in self.discounts)

    def validate(self) -> list[str]:
        """Run all consistency checks; an empty list means the receipt adds up."""
        return validate(self)

    @property
    def is_valid(self) -> bool:
        return not self.validate()

    def to_dict(self) -> dict[str, Any]:
        """JSON-friendly representation."""

        def convert(value: Any) -> Any:
            if isinstance(value, Decimal):
                return str(value)
            if isinstance(value, dt.datetime):
                return value.isoformat()
            if isinstance(value, dict):
                return {k: convert(v) for k, v in value.items()}
            if isinstance(value, (list, tuple)):
                return [convert(v) for v in value]
            return value

        data = convert(asdict(self))
        data["total_cents"] = self.total_cents
        data["validation_errors"] = self.validate()
        return data


def parse_lines(lines: Iterable[str]) -> Receipt:
    """Parse recognised receipt text (one string per line) into a :class:`Receipt`."""
    # Lines with unknown cells come from the logo and the large headings.
    clean = [line for line in lines if UNKNOWN_CHAR not in line and line.strip()]
    r = Receipt()

    for line in clean:
        if m := RE_REGISTER.match(line):
            r.register = m["no"]
        elif m := RE_LOYALTY_CARD.match(line):
            r.loyalty_card = m["card"]
        elif m := RE_RECEIPT_NO.match(line):
            r.receipt_number = m["no"]
        elif m := RE_DATETIME.match(line):
            r.issued_at = dt.datetime.strptime(m["dt"], "%Y-%m-%d %H:%M:%S")
        elif m := RE_DOCUMENT.match(line):
            r.document_number = m["doc"]
        elif m := RE_CARD_TOTAL.match(line):
            r.card_total_cents = to_cents(m["total"])
        elif m := RE_VAT.match(line):
            r.vat.append(
                VatLine(
                    vat_class=m["cls"],
                    rate=Decimal(m["rate"].replace(",", ".")),
                    gross_cents=to_cents(m["gross"]),
                    net_cents=to_cents(m["net"]),
                    vat_cents=to_cents(m["vat"]),
                )
            )

    # The store name is the header line right after the legal address.
    for i, line in enumerate(clean[:-1]):
        if line.strip().startswith("Jur. adrese"):
            r.store = restore_letter_o(clean[i + 1].strip())
            break
    else:
        r.parse_problems.append("header not found")

    blocks = _split_blocks(clean)
    items_at = next((i for i, b in enumerate(blocks) if any(RE_LOYALTY_CARD.match(x) for x in b)), None)
    if items_at is None or items_at + 1 >= len(blocks):
        r.parse_problems.append("item block not found")
        return r
    _parse_items(blocks[items_at + 1], r)

    for block in blocks[items_at + 2 :]:
        if not block:
            continue
        if block[0].strip() == "ATLAIDES:":
            _parse_discounts(block[1:], r)
        elif block[0].startswith("Nodoklis"):
            _parse_payments(block[1:], r)
        elif any("Mans Rimi" in x for x in block) and not any(RE_CARD_TOTAL.match(x) for x in block):
            _parse_loyalty(block, r)
    return r


def _split_blocks(lines: list[str]) -> list[list[str]]:
    blocks: list[list[str]] = [[]]
    for line in lines:
        if RE_SEPARATOR.match(line):
            blocks.append([])
        else:
            blocks[-1].append(line)
    return blocks


def _parse_items(block: list[str], r: Receipt) -> None:
    name_parts: list[str] = []
    correction = False
    for line in block:
        if RE_CORRECTION.match(line):
            correction = True
        elif m := RE_QTY.match(line):
            if not name_parts:
                r.parse_problems.append(f"quantity line without a name: {line.strip()!r}")
            r.items.append(
                Item(
                    name=restore_letter_o(" ".join(p.strip() for p in name_parts)),
                    quantity=Decimal(m["qty"].replace(",", ".")),
                    unit=m["unit"],
                    unit_price_cents=to_cents(m["price"]),
                    amount_cents=to_cents(m["amount"]),
                    vat_class=m["vat"],
                    is_correction=correction,
                )
            )
            name_parts, correction = [], False
        elif m := RE_ITEM_DISCOUNT.match(line):
            if not r.items or name_parts:
                r.parse_problems.append(f"discount line without an item: {line.strip()!r}")
                continue
            item = r.items[-1]
            # A correction repeats the original item's discount line; flip the signs.
            sign = -1 if item.is_correction else 1
            item.discount_cents = sign * to_cents(m["disc"])
            item.final_price_cents = sign * to_cents(m["final"])
        elif RE_COUPON_QTY.match(line) and name_parts:
            r.coupons.append(restore_letter_o(" ".join(p.strip() for p in name_parts)))
            name_parts = []
        else:
            name_parts.append(line)
    if name_parts:
        r.unparsed_lines.extend(name_parts)
        r.parse_problems.append(f"item block ends without a quantity line: {name_parts}")


def _parse_discounts(block: list[str], r: Receipt) -> None:
    name_parts: list[str] = []
    for line in block:
        if m := RE_TRAILING_MONEY.match(line):
            label = restore_letter_o(" ".join([*name_parts, m["label"].strip()]))
            r.discounts.append(
                Discount(
                    label=label,
                    amount_cents=to_cents(m["amount"]),
                    receipt_level=bool(RE_RECEIPT_LEVEL_DISCOUNT.match(label)),
                )
            )
            name_parts = []
        else:
            name_parts.append(line.strip())
    r.unparsed_lines.extend(name_parts)


def _parse_payments(block: list[str], r: Receipt) -> None:
    for line in block:
        if RE_VAT.match(line):
            continue
        if m := RE_TRAILING_MONEY.match(line):
            r.payments.append(
                Payment(method=restore_letter_o(m["label"].strip()), amount_cents=to_cents(m["amount"]))
            )
        else:
            r.unparsed_lines.append(line)


def _parse_loyalty(block: list[str], r: Receipt) -> None:
    pending: list[str] = []
    for line in block:
        if line.startswith("#"):  # promotional message
            continue
        if m := RE_TRAILING_MONEY.match(line):
            label = " ".join([*pending, m["label"].strip()])
            r.loyalty.append(LoyaltyLine(label=label, amount_cents=to_cents(m["amount"])))
            pending = []
        else:
            pending.append(line.strip())


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def validate(r: Receipt) -> list[str]:
    """Consistency checks. An empty list means every checksum on the receipt adds up."""
    errors = list(r.parse_problems)
    if not r.items:
        errors.append("no items")

    for it in r.items:
        expected = int((it.quantity * it.unit_price_cents).quantize(Decimal(1), rounding=ROUND_HALF_UP))
        if it.is_correction:
            expected = -expected
        tolerance = 1 if it.unit == "kg" else 0
        if abs(expected - it.amount_cents) > tolerance:
            errors.append(
                f"quantity × price ≠ amount: {it.name!r} "
                f"{it.quantity}×{it.unit_price_cents}≠{it.amount_cents}"
            )
        if it.final_price_cents is not None and it.paid_cents != it.final_price_cents:
            errors.append(f"amount + discount ≠ final price: {it.name!r}")

    item_discounts = sum(it.discount_cents for it in r.items)
    listed_item_discounts = sum(d.amount_cents for d in r.discounts if not d.receipt_level)
    if item_discounts != listed_item_discounts:
        errors.append(f"item discounts {item_discounts} ≠ ATLAIDES item discounts {listed_item_discounts}")

    total = r.total_cents
    if r.vat:
        vat_gross = sum(v.gross_cents for v in r.vat)
        if vat_gross != total:
            errors.append(f"VAT table gross {vat_gross} ≠ total {total}")
        for v in r.vat:
            if v.gross_cents - v.net_cents != v.vat_cents:
                errors.append(f"VAT {v.vat_class}: gross − net ≠ VAT")
    else:
        errors.append("no VAT table")

    if not r.payments:
        errors.append("no payments")
    else:
        paid = sum(-p.amount_cents if p.method == CHANGE_LABEL else p.amount_cents for p in r.payments)
        if paid != total:
            errors.append(f"payments {paid} ≠ total {total}")
    card = sum(p.amount_cents for p in r.payments if p.method == CARD_LABEL)
    if r.card_total_cents is not None and card != r.card_total_cents:
        errors.append(f"KOPĀ {r.card_total_cents} ≠ card payment {card}")

    # OCR cross-check: a promotion in ATLAIDES usually repeats the item name. Equal
    # ignoring case but not exactly equal is a recognition error (e.g. "č" vs "Č").
    names = {_normalise(it.name) for it in r.items}
    folded = {n.casefold(): n for n in names}
    for d in r.discounts:
        label = RE_MULTIBUY.sub("", _normalise(d.label))
        if label not in names and label.casefold() in folded:
            errors.append(f"OCR mismatch: discount {label!r} vs item {folded[label.casefold()]!r}")

    for name in ("receipt_number", "issued_at", "register"):
        if getattr(r, name) is None:
            errors.append(f"missing {name}")
    return errors
