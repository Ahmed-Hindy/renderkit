"""Shared OpenImageIO ImageCache helpers."""

from __future__ import annotations

import threading
from typing import Any, Optional

_CACHE_LOCK = threading.Lock()
_SHARED_CACHE: Optional[Any] = None


def get_shared_image_cache() -> Any:
    """Return a process-wide OIIO ImageCache singleton."""
    global _SHARED_CACHE
    if _SHARED_CACHE is not None:
        return _SHARED_CACHE

    with _CACHE_LOCK:
        if _SHARED_CACHE is None:
            import OpenImageIO as oiio

            _SHARED_CACHE = oiio.ImageCache()

    return _SHARED_CACHE


def set_shared_image_cache(cache: Optional[Any]) -> None:
    """Override the shared ImageCache (used for tests)."""
    global _SHARED_CACHE
    with _CACHE_LOCK:
        _SHARED_CACHE = cache
