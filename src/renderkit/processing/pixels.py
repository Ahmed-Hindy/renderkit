"""Pixel array conversion helpers."""

from __future__ import annotations

import numpy as np


def float_pixels_to_uint8(pixels: np.ndarray) -> np.ndarray:
    """Clamp float-like pixels to display-range uint8."""
    pixels_f32 = pixels.astype(np.float32, copy=False)
    clipped = np.clip(pixels_f32, 0.0, 1.0)
    return (clipped * np.float32(255.0)).astype(np.uint8)
