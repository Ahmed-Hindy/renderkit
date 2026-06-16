"""Shared OpenImageIO import and buffer helpers."""

from __future__ import annotations

from typing import Any


def require_oiio(
    error_type: type[Exception] = RuntimeError,
    message: str = "OpenImageIO library not available.",
) -> Any:
    """Import OpenImageIO or raise the caller's domain error."""
    try:
        import OpenImageIO as oiio
    except ImportError as exc:
        raise error_type(message) from exc
    return oiio


def ensure_float_imagebuf(
    oiio: Any,
    buf: Any,
    *,
    error_type: type[Exception] = RuntimeError,
    error_message: str = "OIIO copy to float failed",
) -> Any:
    """Return ``buf`` as an OIIO FLOAT ImageBuf."""
    spec = buf.spec()
    if spec.format == oiio.FLOAT:
        return buf

    float_spec = oiio.ImageSpec(spec.width, spec.height, spec.nchannels, oiio.FLOAT)
    float_buf = oiio.ImageBuf(float_spec)
    if not oiio.ImageBufAlgo.copy(float_buf, buf):
        details = oiio.geterror() or buf.geterror()
        raise error_type(f"{error_message}: {details}")
    return float_buf
