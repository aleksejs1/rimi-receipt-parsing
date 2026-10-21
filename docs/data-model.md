# Data model

`parse_pdf()` and `parse_lines()` return a `Receipt`. All dataclasses live in `rimi_receipts.parser` and
are re-exported from `rimi_receipts`. Money is always **integer euro cents**; signs follow the receipt
(discounts and corrections are negative).

## `Receipt`

| Field | Type | Source on the receipt |
|---|---|---|
| `receipt_number` | `str` | `#07123456` in the footer, without `#`; unique per store chain, a good primary key |
| `issued_at` | `datetime` | the timestamp in the footer (local time, no timezone) |
| `register` | `str` | `Kase Nr. 31` |
| `document_number` | `str` | `Dok. Nr.: 12/34567` |
| `store` | `str` | header line after the legal address, e.g. `Rimi Hyper <name> (Rīga)` |
| `loyalty_card` | `str` | masked Mans Rimi card, as printed (`XXXXXXXXXXXXXXX1234`) |
| `items` | `list[Item]` | the item block |
| `coupons` | `list[str]` | scanned coupons (`Kupons 9960000012345`) — they carry no amount themselves |
| `discounts` | `list[Discount]` | the *ATLAIDES* block |
| `vat` | `list[VatLine]` | the VAT table |
| `payments` | `list[Payment]` | payment lines under the VAT table |
| `card_total_cents` | `int \| None` | *KOPĀ* on the card slip (card payment only) |
| `loyalty` | `list[LoyaltyLine]` | the Mans Rimi block |
| `total_cents` | `int` (property) | Σ item amounts + Σ discounts |
| `unparsed_lines` | `list[str]` | lines the parser did not understand |
| `parse_problems` | `list[str]` | structural problems found while parsing |
| `raw_lines` | `list[str]` | recognised body text (`parse_pdf` only) |
| `low_confidence` | `list[str]` | characters recognised with a small margin (`parse_pdf` only) |

Methods: `validate() -> list[str]` (empty = all checks pass), `is_valid`, `to_dict()` (JSON-friendly;
includes `total_cents` and `validation_errors`).

## `Item`

| Field | Type | Notes |
|---|---|---|
| `name` | `str` | wrapped name lines joined with spaces |
| `quantity` | `Decimal` | pieces (`gab`) or kilograms (`kg`, three decimals) |
| `unit` | `str` | `"gab"` or `"kg"` |
| `unit_price_cents` | `int` | price per piece or per kg |
| `amount_cents` | `int` | line amount as printed; negative for a correction |
| `vat_class` | `str` | letter referring to the VAT table (`A` 21 %, `C` 12 %, `F` 5 %, `D` 0 % deposit, …) |
| `discount_cents` | `int` | from the `Atl.` line, negative; `0` if none |
| `final_price_cents` | `int \| None` | *Gala cena*, printed only for discounted items |
| `is_correction` | `bool` | the line cancels a previously scanned item (`--Korekcija--`) |
| `paid_cents` | `int` (property) | `amount_cents + discount_cents` |

Deposit (*Depozīta maksa*) and shopping bags are ordinary items.

## `Discount`

| Field | Type | Notes |
|---|---|---|
| `label` | `str` | item name, promotion name (`MM 2+ …`, `Pēdējās dienas cena gaļai`) or `Citas akcijas` |
| `amount_cents` | `int` | negative |
| `receipt_level` | `bool` | `True` for *Izmantotā Mans Rimi nauda* / *Izmantots … kupons*: not tied to items |

Item-level discounts (`receipt_level == False`) always sum to the item discounts; receipt-level ones are
paid with loyalty money or coupons and reduce the VAT base.

## `VatLine`

`vat_class`, `rate` (`Decimal`, percent), `gross_cents`, `net_cents`, `vat_cents`.

## `Payment`

`method` (as printed: `Bankas karte`, `Skaidra nauda`, `Depozīta kupons`, `Atlikums` = change returned …)
and `amount_cents`.

## `LoyaltyLine`

`label` and `amount_cents`, e.g. `Nopelnītā Mans Rimi nauda` (earned), `Mans Rimi naudas uzkrājums`
(balance), `Atlaide ar Mans Rimi karti`, `Ietaupījums ar Mans Rimi karti šomēnes` (saved this month).
