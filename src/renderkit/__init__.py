"""Image and Video Processor package for VFX workflows."""

from __future__ import annotations

__version__ = "0.9.0"

__all__ = ["RenderKit"]


def __getattr__(name: str):
    if name == "RenderKit":
        from renderkit.api.processor import RenderKit

        return RenderKit
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(list(globals().keys()) + ["RenderKit"])
