"""Image scaling utilities using OpenImageIO (OIIO)."""


class ImageScaler:
    """Utility class for image scaling using OpenImageIO."""

    @staticmethod
    @staticmethod
    def scale_buf(
        buf,
        width: int,
        height: int,
        filter_name: str = "lanczos3",
    ):
        """Scale an OIIO ImageBuf without converting to NumPy."""
        try:
            import OpenImageIO as oiio
        except ImportError as e:
            raise RuntimeError("OpenImageIO library not available.") from e

        spec = buf.spec()
        src_buf = buf
        if spec.format != oiio.FLOAT:
            float_spec = oiio.ImageSpec(spec.width, spec.height, spec.nchannels, oiio.FLOAT)
            float_buf = oiio.ImageBuf(float_spec)
            if not oiio.ImageBufAlgo.copy(float_buf, buf):
                raise RuntimeError(f"OIIO copy to float failed: {oiio.geterror()}")
            src_buf = float_buf

        dst_buf = oiio.ImageBuf(oiio.ImageSpec(width, height, spec.nchannels, oiio.FLOAT))
        if not oiio.ImageBufAlgo.resize(dst_buf, src_buf, filtername=filter_name):
            raise RuntimeError(f"OIIO resize failed: {oiio.geterror()}")

        return dst_buf
