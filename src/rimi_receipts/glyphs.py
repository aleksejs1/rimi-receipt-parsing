"""Reference glyph images ("templates") used for recognition."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from pathlib import Path

import numpy as np

from .grid import BOTTOM, GLYPH_H, TOP

# Only capitals with an accent above may have ink in rows -2..-1, and only glyphs
# with a descender or a cedilla may have ink in rows 10..11. Anything else there is
# a leftover of a neighbouring line and is wiped when templates are built.
TOP_ROWS_ALLOWED = frozenset("ĀČĒĢĪŠŪŽ")
BOTTOM_ROWS_ALLOWED = frozenset(",;/Qgjpqyķļņģ()_")


@dataclass
class Glyphs:
    """A set of glyph templates: ``images[i]`` (14×8, ink 0..1) is the glyph for ``chars[i]``.

    A character may have several templates (variants rendered with slightly different
    neighbours). ``0`` and ``O`` are pixel-identical in the receipt font, so there is a
    single ``0`` template; the parser restores ``O`` from context.
    """

    chars: list[str]
    images: np.ndarray

    def __post_init__(self) -> None:
        self.images = np.asarray(self.images, dtype=np.float32)
        if self.images.shape[1:] != (GLYPH_H, 8) or len(self.chars) != len(self.images):
            raise ValueError("glyph images must have shape (N, 14, 8) and match chars")

    @classmethod
    def load(cls, path: str | Path | None = None) -> Glyphs:
        """Load a glyph set; without ``path`` the bundled set is used."""
        if path is None:
            with resources.as_file(resources.files("rimi_receipts") / "data" / "glyphs.npz") as p:
                data = np.load(p, allow_pickle=False)
                return cls(chars=[str(c) for c in data["chars"]], images=data["images"])
        data = np.load(path, allow_pickle=False)
        return cls(chars=[str(c) for c in data["chars"]], images=data["images"])

    def save(self, path: str | Path) -> None:
        np.savez_compressed(path, chars=np.array(self.chars), images=self.images.astype(np.float32))

    @property
    def alphabet(self) -> str:
        return "".join(sorted(set(self.chars)))

    def image(self, char: str) -> np.ndarray:
        """The first template for ``char``."""
        return self.images[self.chars.index(char)]

    def add(self, char: str, image: np.ndarray) -> None:
        """Add a template, wiping ink that cannot belong to ``char`` from the overlap rows."""
        image = np.array(image, dtype=np.float32)
        image[image < 0.2] = 0
        if char not in TOP_ROWS_ALLOWED:
            image[TOP] = 0
        if char not in BOTTOM_ROWS_ALLOWED:
            image[BOTTOM] = 0
        self.chars.append(char)
        self.images = np.concatenate([self.images, image[None]])


@lru_cache(maxsize=1)
def default_glyphs() -> Glyphs:
    """The bundled glyph set (cached)."""
    return Glyphs.load()
