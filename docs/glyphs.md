# The glyph set

Recognition compares every character cell with reference images in
[`src/rimi_receipts/data/glyphs.npz`](../src/rimi_receipts/data/glyphs.npz): 99 templates of 14 × 8 pixels
(ink 0..1), covering

```
!"#%&'()*+,-./0123456789:ABCDEFGHIJKLMNPQRSTUVWXYZ^abcdefghijklmnopqrstuvwxyz®ĀāČčéēĪīķļņŠšŪūŽž
```

plus space. `O` is missing on purpose — it is identical to `0`. Some characters have more than one
template.

You can inspect the set with:

```python
from rimi_receipts import default_glyphs
g = default_glyphs()
print(len(g.chars), g.alphabet)
img = g.image("ķ")   # numpy array (14, 8)
```

## How the set was built

1. Lines of a few dozen receipts were located with a simple baseline heuristic, cut into cells and
   clustered.
2. Clusters were labelled from one receipt with a known transcription, and the rest by hand.
3. Every receipt was recognised; cells that matched nothing were clustered again and labelled. Two rounds
   were enough to cover ~1,000 receipts from 2021–2026.
4. Templates are the **pixel-wise median** of all cells in a cluster, which removes most leftovers of
   neighbouring lines. What remains is wiped by rule: only capitals with an accent above may have ink in
   rows −2..−1, only descenders and cedillas in rows 10..11.

Labelling mistakes are possible and dangerous (in the first version a lowercase `č` was labelled `Č`). The
validator's "promotion name equals item name" check caught it — keep running `rimi-receipts check` on a
real archive after any change to the set.

## Adding a character

When Rimi prints something new, the cell is returned as `�`, the line keeps the other characters, and the
receipt fails validation. To add the character:

```bash
rimi-receipts glyphs harvest ~/rimi-receipts work/        # collect unknown cells
rimi-receipts glyphs review work/                         # cluster them, draw work/unknown-NN.png
```

Open the PNGs: each row shows an enlarged cluster, its id and size, and a line where it occurred, e.g.

```
cluster 7  ×12
Kafija Caf[?] latte 200ml
```

Ignore clusters that are fragments of large headings (the big digits next to *Samaksai EUR*, the dashed
line under *Tavs ietaupījums*). Label the rest:

```bash
rimi-receipts glyphs add work/ '{"7": "é"}'               # updates src/rimi_receipts/data/glyphs.npz
rimi-receipts check ~/rimi-receipts                       # make sure nothing regressed
```

Please contribute new templates back with a pull request — templates are single characters and contain no
personal data, but **never commit the harvested `work/` folder**: its context lines come from real
receipts.
