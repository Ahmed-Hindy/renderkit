"""Image scaling utilities using OpenImageIO (OIIO)."""

from renderkit.io.oiio_utils import ensure_float_imagebuf, require_oiio


class ImageScaler:
    """Utility class for image scaling using OpenImageIO."""

    @staticmethod
    def scale_buf(
        buf,
        width: int,
        height: int,
        filter_name: str = "lanczos3",
    ):
        """Scale an OIIO ImageBuf without converting to NumPy."""
        oiio = require_oiio()

        spec = buf.spec()
        src_buf = ensure_float_imagebuf(oiio, buf)

        dst_buf = oiio.ImageBuf(oiio.ImageSpec(width, height, spec.nchannels, oiio.FLOAT))
        if not oiio.ImageBufAlgo.resize(dst_buf, src_buf, filtername=filter_name):
            raise RuntimeError(f"OIIO resize failed: {oiio.geterror()}")

        return dst_buf
