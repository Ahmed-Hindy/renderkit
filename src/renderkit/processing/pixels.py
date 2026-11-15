"""Pixel array conversion helpers."""

from __future__ import annotations

import numpy as np


def float_pixels_to_uint8(pixels: np.ndarray) -> np.ndarray:
    """Clamp float-like pixels to display-range uint8."""
    pixels_f32 = pixels.astype(np.float32, copy=False)
    clipped = np.clip(pixels_f32, 0.0, 1.0)
    return (clipped * np.float32(255.0)).astype(np.uint8)


def float_pixels_to_uint16(pixels: np.ndarray) -> np.ndarray:
    """Clamp float-like pixels to display-range contiguous uint16."""
    sanitized = np.nan_to_num(
        pixels.astype(np.float32, copy=False),
        nan=0.0,
        posinf=1.0,
        neginf=0.0,
    )
    clipped = np.clip(sanitized, 0.0, 1.0)
    scaled = (clipped * np.float32(65535.0) + np.float32(0.5)).astype(np.uint16)
    return np.ascontiguousarray(scaled)
