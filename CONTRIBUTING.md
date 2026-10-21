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

## Releasing (maintainers)

1. Make sure CI is green on `main` and, if the recogniser, the parser or the glyph set changed, that
   `rimi-receipts check` passes on a real archive.
2. Bump `__version__` in `src/rimi_receipts/__init__.py` (semantic versioning: a change in the
   `Receipt` data model or the CLI output is a minor version while below 1.0).
3. Add a `## X.Y.Z — YYYY-MM-DD` section to `CHANGELOG.md`; it becomes the release notes.
4. Commit, then tag and push:

   ```bash
   git tag -a vX.Y.Z -m "vX.Y.Z" && git push origin main vX.Y.Z
   ```

The [release workflow](.github/workflows/release.yml) checks that the tag matches the version and the
changelog, builds the sdist and wheel, runs the tests against the built wheel, publishes to PyPI and
creates a GitHub Release with both files attached.

PyPI publishing uses [trusted publishing](https://docs.pypi.org/trusted-publishers/): no API token is
stored anywhere. It is configured once on PyPI for the project `rimi-receipt-parsing` with owner
`aleksejs1`, repository `rimi-receipt-parsing`, workflow `release.yml` and environment `pypi`.
