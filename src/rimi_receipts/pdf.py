"""Extracting the receipt image from a Rimi e-receipt PDF."""

from __future__ import annotations

import io
from pathlib import Path
from typing import BinaryIO

import numpy as np
from PIL import Image
from pypdf import PdfReader


class NotARimiReceiptError(ValueError):
    """The PDF does not look like a Rimi e-receipt (one page with one raster image)."""


def load_image(source: str | Path | bytes | BinaryIO) -> Image.Image:
    """Return the receipt raster embedded in the PDF."""
    if isinstance(source, bytes):
        source = io.BytesIO(source)
    reader = PdfReader(source)
    if len(reader.pages) != 1:
        raise NotARimiReceiptError(f"expected a single page, got {len(reader.pages)}")
    page = reader.pages[0]
    xobjects = page.get("/Resources", {}).get("/XObject", {})
    images = [o.get_object() for o in xobjects.values() if o.get_object().get("/Subtype") == "/Image"]
    if len(images) != 1:
        raise NotARimiReceiptError(f"expected a single image on the page, got {len(images)}")
    image = images[0]
    if image.get("/Filter") == "/DCTDecode":
        # Decode the original JPEG bytes ourselves: generic PDF image extraction may
        # re-encode the picture, and the recogniser is sensitive to pixel values.
        return Image.open(io.BytesIO(image.get_data()))
    return page.images[0].image


def image_to_ink(image: Image.Image) -> np.ndarray:
    """Convert an image to an "ink" array: float32 in 0..1, where 1 is a black pixel."""
    gray = np.asarray(image.convert("L"), dtype=np.float32)
    return 1.0 - gray / 255.0


def load_ink(source: str | Path | bytes | BinaryIO) -> np.ndarray:
    """Load the receipt PDF and return its ink array."""
    return image_to_ink(load_image(source))
