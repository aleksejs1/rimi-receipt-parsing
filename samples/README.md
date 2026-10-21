# Synthetic samples

These receipts are **not real**. They were generated with

```bash
rimi-receipts synth --out samples --count 5 --seed 1
```

which lays out a receipt in the Rimi e-receipt format and renders it with the library's own glyph templates
into a JPEG-in-PDF, like the cash register does. The "logo" is the word SAMPLE, the company and store are
fictional, products and prices are random, and all card, terminal and document numbers are random.

Each `sample-NN.pdf` has a matching `sample-NN.txt` with the text that was rendered. The generated receipts
are internally consistent (VAT, discounts and payments add up), and they exercise the hard parts of the
real format: centred header lines, large headings that shift the line grid, overlapping accents,
weighted items, discounts, deposits, coupons, corrections and cash payments with change.

They are used by the test suite and are safe to share in bug reports.
