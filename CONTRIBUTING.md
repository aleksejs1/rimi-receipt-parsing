# Contributing

Thanks for helping! Bug reports, new glyph templates, support for other receipt variants and
documentation fixes are all welcome.

## Never share real receipts

Real receipts contain personal data (masked card numbers, terminal and transaction IDs, where and when
someone shopped). Do not attach them to issues or pull requests, and do not commit them or anything
derived from them (recognised text, harvested cells from `rimi-receipts glyphs harvest`).

To report a problem, either

- reproduce it with a synthetic receipt (`rimi-receipts synth`, or `rimi_receipts.synth` in Python), or
- paste only the relevant recognised lines (`rimi-receipts parse --format text`) with personal fields
  replaced, together with the validation errors.

## Development setup

```bash
python -m venv .venv && . .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest
ruff check . && ruff format --check .
```

If you have a local archive of real receipts, run the regression test before submitting changes to the
recogniser, the parser or the glyph set:

```bash
RIMI_CORPUS_DIR=~/rimi-receipts pytest tests/test_corpus.py
# or, faster and with a summary:
rimi-receipts check ~/rimi-receipts
```

Please mention the result (e.g. "1 204/1 204 receipts add up") in the pull request.

## Adding glyphs

See [docs/glyphs.md](docs/glyphs.md). Commit only the updated `src/rimi_receipts/data/glyphs.npz`.

## Style

- Code, comments and documentation in English.
- `ruff` for linting and formatting (configured in `pyproject.toml`).
- Money is integer cents; never use floats for amounts.
- New receipt features need a test — a text fixture in `tests/test_parser.py` and, if the layout is
  involved, support in `rimi_receipts.synth`.
