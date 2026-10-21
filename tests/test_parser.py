from __future__ import annotations

import datetime as dt
from decimal import Decimal

from rimi_receipts import LoyaltyLine, parse_lines

HEADER = """\
              SIA PARAUGS
 Jur. adrese: Parauga iela 1, Rīga
       Example Store (Rīga)
              Kase Nr. 07
---------------- Čeks ------------------
--------- Elektroniska izdruka ---------
KLIENTS:            XXXXXXXXXXXXXXX1234
----------------------------------------"""

FOOTER = """\
----------------------------------------
Dok. Nr.: 12/34567 Kase 0007
FB numurs: 012345678901234
                               #07123456

  2026-01-02 10:11:12"""


def receipt(body: str) -> list[str]:
    return f"{HEADER}\n{body}\n{FOOTER}".splitlines()


CARD_RECEIPT = receipt("""\
Piens Rimi 2,5% 1l
 2 gab X 1,09 EUR                 2,18 A
 Atl. -0,40   Gala cena 1,78
Banāni kg
 0,996 kg X 0,99 EUR/kg           0,99 F
Sula ābolu 100% 1l
 1 gab X 2,19 EUR                 2,19 A
Depozīta maksa
 1 gab X 0,10 EUR                 0,10 D
----------------------------------------
ATLAIDES:
Citas akcijas                    -0,40
                              ----------
Maksājumu karte
Visa                    ************0000
K0PĀ:                           5,06 EUR
SAGLABĀJIET D0KUMENTU K0NTA PĀRBAUDEI
----------------------------------------
Nopelnītā Mans Rimi nauda           0,05
Ietaupījums ar Mans Rimi karti
šomēnes                             0,40
----------------------------------------
Nodoklis      Ar PVN   Bez PVN PVN summa
A 21,00 %       3,97      3,28      0,69
D  0,00 %       0,10      0,10      0,00
F  5,00 %       0,99      0,94      0,05
Bankas karte                        5,06""")


def test_card_receipt_parses_and_adds_up() -> None:
    r = parse_lines(CARD_RECEIPT)
    assert r.validate() == []
    assert r.receipt_number == "07123456"
    assert r.register == "07"
    assert r.document_number == "12/34567"
    assert r.store == "Example Store (Rīga)"
    assert r.issued_at == dt.datetime(2026, 1, 2, 10, 11, 12)
    assert r.loyalty_card == "XXXXXXXXXXXXXXX1234"
    assert r.total_cents == 506
    assert r.card_total_cents == 506
    assert [i.name for i in r.items] == [
        "Piens Rimi 2,5% 1l",
        "Banāni kg",
        "Sula ābolu 100% 1l",
        "Depozīta maksa",
    ]
    milk = r.items[0]
    assert (milk.quantity, milk.unit_price_cents, milk.amount_cents) == (Decimal(2), 109, 218)
    assert (milk.discount_cents, milk.final_price_cents, milk.paid_cents) == (-40, 178, 178)
    assert r.items[1].quantity == Decimal("0.996") and r.items[1].unit == "kg"
    assert [(v.vat_class, v.rate) for v in r.vat] == [
        ("A", Decimal(21)),
        ("D", Decimal(0)),
        ("F", Decimal(5)),
    ]
    assert LoyaltyLine("Ietaupījums ar Mans Rimi karti šomēnes", 40) in r.loyalty


def test_tampered_amount_is_detected() -> None:
    lines = [line.replace("2,19 A", "2,91 A") for line in CARD_RECEIPT]
    errors = parse_lines(lines).validate()
    assert any("quantity × price" in e for e in errors)
    assert any("VAT table" in e for e in errors)


def test_correction_coupon_cash_and_change() -> None:
    r = parse_lines(
        receipt("""\
Kafija malta 250g
 1 gab X 5,49 EUR                 5,49 A
 Atl. -1,00   Gala cena 4,49
Kupons 9960000012345
 1 gab.
--------------Korekcija-----------------
Kafija malta 250g
 1 gab X 5,49 EUR                -5,49 A
 Atl. -1,00   Gala cena 4,49
Maize rudzu 400g
 1 gab X 1,35 EUR                 1,35 A
----------------------------------------
Nodoklis      Ar PVN   Bez PVN PVN summa
A 21,00 %       1,35      1,12      0,23
Skaidra nauda                       5,00
Atlikums                            3,65""")
    )
    assert r.validate() == []
    assert r.coupons == ["Kupons 9960000012345"]
    voided = r.items[1]
    assert voided.is_correction and voided.amount_cents == -549
    assert (voided.discount_cents, voided.final_price_cents) == (100, -449)
    assert r.total_cents == 135


def test_receipt_level_discount_and_deposit_coupon() -> None:
    r = parse_lines(
        receipt("""\
Gāzēts dzēriens 2l
 1 gab X 1,99 EUR                 1,99 A
Depozīta maksa
 1 gab X 0,10 EUR                 0,10 D
----------------------------------------
ATLAIDES:
Izmantotā Mans Rimi nauda        -0,50
                              ----------
K0PĀ:                           1,49 EUR
----------------------------------------
Nodoklis      Ar PVN   Bez PVN PVN summa
A 21,00 %       1,49      1,23      0,26
D  0,00 %       0,10      0,10      0,00
Depozīta kupons                     0,10
Bankas karte                        1,49""")
    )
    assert r.validate() == []
    assert r.discounts[0].receipt_level
    assert r.total_cents == 159


def test_named_promotion_and_ocr_cross_check() -> None:
    body = """\
Tomātu kečups 500g
 1 gab X 2,50 EUR                 2,50 A
 Atl. -0,50   Gala cena 2,00
----------------------------------------
ATLAIDES:
{label}                -0,50
                              ----------
----------------------------------------
Nodoklis      Ar PVN   Bez PVN PVN summa
A 21,00 %       2,00      1,65      0,35
Bankas karte                        2,00"""
    assert parse_lines(receipt(body.format(label="Tomātu kečups 500g"))).validate() == []
    assert parse_lines(receipt(body.format(label="MM 2+ Tomātu kečups"))).validate() == []
    errors = parse_lines(receipt(body.format(label="Tomātu keČups 500g"))).validate()
    assert any("OCR mismatch" in e for e in errors)


def test_letter_o_is_restored_in_words_only() -> None:
    r = parse_lines(
        receipt("""\
Zobu pasta C0LGATE 75ml
 1 gab X 2,00 EUR                 2,00 A
Ūdens 0,5l 10gab.
 1 gab X 3,00 EUR                 3,00 A
----------------------------------------
Nodoklis      Ar PVN   Bez PVN PVN summa
A 21,00 %       5,00      4,13      0,87
Bankas karte                        5,00""")
    )
    assert r.validate() == []
    assert [i.name for i in r.items] == ["Zobu pasta COLGATE 75ml", "Ūdens 0,5l 10gab."]


def test_garbage_is_reported_not_raised() -> None:
    r = parse_lines(["hello", "world"])
    assert r.validate()
    assert not r.is_valid
