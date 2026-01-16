import pytest

from renderkit.io.image_reader import ImageReaderFactory, OIIOReader
from renderkit.io.oiio_cache import get_shared_image_cache, set_shared_image_cache


def test_shared_image_cache_singleton():
    """Shared ImageCache should be a singleton."""
    try:
        import OpenImageIO  # noqa: F401
    except ImportError:
        pytest.skip("OpenImageIO not available")

    cache1 = get_shared_image_cache()
    cache2 = get_shared_image_cache()
    assert cache1 is cache2


def test_reader_uses_injected_cache():
    """Reader should honor an injected ImageCache."""
    fake_cache = object()
    reader = OIIOReader(image_cache=fake_cache)
    assert reader._get_image_cache() is fake_cache


def test_factory_passes_cache(tmp_path):
    """Factory should pass cache when creating readers."""
    fake_cache = object()
    reader = ImageReaderFactory.create_reader(tmp_path / "sample.exr", image_cache=fake_cache)
    assert isinstance(reader, OIIOReader)
    assert reader._get_image_cache() is fake_cache


def test_shared_cache_override():
    """Allow overriding shared cache (for tests)."""
    try:
        import OpenImageIO  # noqa: F401
    except ImportError:
        pytest.skip("OpenImageIO not available")

    original = get_shared_image_cache()
    fake_cache = object()
    set_shared_image_cache(fake_cache)
    try:
        assert get_shared_image_cache() is fake_cache
    finally:
        set_shared_image_cache(original)
