from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import OpenImageIO as oiio
import pytest

from renderkit.io.image_reader import OIIOReader


def test_exr_metadata_fps_detection():
    """Test that OIIOReader correctly extracts FPS from various metadata keys."""
    reader = OIIOReader()
    mock_path = Path("test.exr")

    with patch("pathlib.Path.exists", return_value=True):
        with patch("OpenImageIO.ImageBuf") as mock_buf_class:
            mock_buf = mock_buf_class.return_value
            mock_buf.has_error = False
            mock_spec = mock_buf.spec.return_value

            # Dictionary to store our mock metadata
            metadata = {}
            mock_spec.getattribute.side_effect = lambda key: metadata.get(key)

            # Case 1: Standard framesPerSecond (Rational)
            metadata.clear()
            metadata["framesPerSecond"] = (24, 1)

            fps = reader.get_metadata_fps(mock_path)
            assert fps == 24.0

            # Case 2: Arnold-style fps (Float)
            reader._file_info_cache.clear()
            metadata.clear()
            metadata["arnold/fps"] = 23.976
            fps = reader.get_metadata_fps(mock_path)
            assert fps == 23.976

            # Case 3: Karma-style fps (Float)
            reader._file_info_cache.clear()
            metadata.clear()
            metadata["exr/FramesPerSecond"] = 24.0
            fps = reader.get_metadata_fps(mock_path)
            assert fps == 24.0

            # Case 4: Rational as tuple
            reader._file_info_cache.clear()
            metadata.clear()
            metadata["fps"] = (30000, 1001)
            fps = reader.get_metadata_fps(mock_path)
            assert abs(fps - 29.97) < 0.01

            # Case 5: String metadata (float)
            reader._file_info_cache.clear()
            metadata.clear()
            metadata["exr/FramesPerSecond"] = "24.0"
            fps = reader.get_metadata_fps(mock_path)
            assert fps == 24.0

            # Case 6: Bytes metadata
            reader._file_info_cache.clear()
            metadata.clear()
            metadata["fps"] = b"23.976"
            fps = reader.get_metadata_fps(mock_path)
            assert fps == 23.976

            # Case 7: Case-insensitive match (Note: OIIO keys are case sensitive in implementation,
            # but our Reader uses constants which should match the typical case)
            reader._file_info_cache.clear()
            metadata.clear()
            metadata["exr/FramesPerSecond"] = 24.0
            fps = reader.get_metadata_fps(mock_path)
            assert fps == 24.0

            # Case 8: Rational string
            reader._file_info_cache.clear()
            metadata.clear()
            metadata["framesPerSecond"] = "24000/1001"
            fps = reader.get_metadata_fps(mock_path)
            assert abs(fps - 23.976) < 0.001

            # Case 9: Invalid string
            reader._file_info_cache.clear()
            metadata.clear()
            metadata["fps"] = "invalid"
            fps = reader.get_metadata_fps(mock_path)
            assert fps is None


def test_exr_metadata_color_space_detection():
    """Test that OIIOReader correctly extracts Color Space from various metadata keys."""
    reader = OIIOReader()
    mock_path = Path("test.exr")

    with patch("pathlib.Path.exists", return_value=True):
        with patch("OpenImageIO.ImageBuf") as mock_buf_class:
            mock_buf = mock_buf_class.return_value
            mock_buf.has_error = False
            mock_spec = mock_buf.spec.return_value

            metadata = {}
            mock_spec.getattribute.side_effect = lambda key: metadata.get(key)

            # Case 1: Standard exr/oiio:ColorSpace
            metadata.clear()
            metadata["exr/oiio:ColorSpace"] = "ACES - ACEScg"
            cs = reader.get_metadata_color_space(mock_path)
            assert cs == "ACES - ACEScg"

            # Case 2: colorSpace
            reader._file_info_cache.clear()
            metadata.clear()
            metadata["colorSpace"] = "Linear"
            cs = reader.get_metadata_color_space(mock_path)
            assert cs == "Linear"

            # Case 3: interchange/color_space
            reader._file_info_cache.clear()
            metadata.clear()
            metadata["interchange/color_space"] = "Rec.709"
            cs = reader.get_metadata_color_space(mock_path)
            assert cs == "Rec.709"

            # Case 4: OIIO key match
            reader._file_info_cache.clear()
            metadata.clear()
            metadata["oiio:ColorSpace"] = "ACEScg"
            cs = reader.get_metadata_color_space(mock_path)
            assert cs == "ACEScg"

            # Case 5: Bytes
            reader._file_info_cache.clear()
            metadata.clear()
            metadata["colorSpace"] = b"sRGB"
            cs = reader.get_metadata_color_space(mock_path)
            assert cs == "sRGB"


def test_exr_metadata_pixel_aspect_and_attributes():
    """OIIOReader extracts pixel_aspect, windows, and scalar extra_attribs."""
    reader = OIIOReader()
    mock_path = Path("test_attrs.exr")

    with patch("pathlib.Path.exists", return_value=True):
        with patch("OpenImageIO.ImageBuf") as mock_buf_class:
            mock_buf = mock_buf_class.return_value
            mock_buf.has_error = False
            mock_buf.nsubimages = 1
            mock_spec = mock_buf.spec.return_value
            mock_spec.x = -10
            mock_spec.y = -5
            mock_spec.width = 1940
            mock_spec.height = 1090
            mock_spec.full_x = 0
            mock_spec.full_y = 0
            mock_spec.full_width = 1920
            mock_spec.full_height = 1080
            mock_spec.nchannels = 4
            mock_spec.channelnames = ("R", "G", "B", "A")
            mock_spec.extra_attribs = [
                SimpleNamespace(name="artist", value="alice"),
                SimpleNamespace(name="version", value=7),
                SimpleNamespace(name="shutter", value=0.5),
                SimpleNamespace(name="is_proxy", value=False),
                SimpleNamespace(name="ignored_tuple", value=(1, 2)),
            ]

            metadata = {"PixelAspectRatio": 2.0}
            mock_spec.getattribute.side_effect = lambda key: metadata.get(key)

            info = reader.get_file_info(mock_path)
            assert info.pixel_aspect == 2.0
            assert info.data_window == (-10, -5, 1940, 1090)
            assert info.display_window == (0, 0, 1920, 1080)
            assert info.width == 1920
            assert info.height == 1080
            assert info.attributes == {
                "artist": "alice",
                "version": 7,
                "shutter": 0.5,
                "is_proxy": False,
            }

            # Fallback to pixelAspectRatio and default 1.0 on invalid values
            reader._file_info_cache.clear()
            metadata.clear()
            metadata["pixelAspectRatio"] = 1.5
            assert reader.get_file_info(mock_path).pixel_aspect == 1.5

            reader._file_info_cache.clear()
            metadata.clear()
            metadata["PixelAspectRatio"] = -1.0
            assert reader.get_file_info(mock_path).pixel_aspect == 1.0


def test_exr_display_window_overscan_and_crop_normalization(tmp_path: Path):
    """OIIOReader.read_imagebuf normalizes overscan and cropped data windows to display window."""
    # Overscan EXR: dataWindow (-2, -2, 8, 8) -> displayWindow (0, 0, 4, 4)
    overscan_path = tmp_path / "overscan.exr"
    overscan_spec = oiio.ImageSpec(8, 8, 3, oiio.FLOAT)
    overscan_spec.x = -2
    overscan_spec.y = -2
    overscan_spec.full_x = 0
    overscan_spec.full_y = 0
    overscan_spec.full_width = 4
    overscan_spec.full_height = 4
    overscan_spec.attribute("PixelAspectRatio", 1.25)
    overscan_spec.attribute("shot", "sh010")

    overscan_pixels = np.zeros((8, 8, 3), dtype=np.float32)
    overscan_pixels[2:6, 2:6, :] = [0.25, 0.5, 0.75]
    overscan_buf = oiio.ImageBuf(overscan_spec)
    overscan_buf.set_pixels(overscan_buf.roi, overscan_pixels)
    assert overscan_buf.write(str(overscan_path))

    # Cropped EXR: dataWindow (1, 1, 2, 2) -> displayWindow (0, 0, 4, 4)
    cropped_path = tmp_path / "cropped.exr"
    cropped_spec = oiio.ImageSpec(2, 2, 3, oiio.FLOAT)
    cropped_spec.x = 1
    cropped_spec.y = 1
    cropped_spec.full_x = 0
    cropped_spec.full_y = 0
    cropped_spec.full_width = 4
    cropped_spec.full_height = 4

    cropped_pixels = np.ones((2, 2, 3), dtype=np.float32) * 0.8
    cropped_buf = oiio.ImageBuf(cropped_spec)
    cropped_buf.set_pixels(cropped_buf.roi, cropped_pixels)
    assert cropped_buf.write(str(cropped_path))

    reader = OIIOReader()

    overscan_info = reader.get_file_info(overscan_path)
    assert overscan_info.width == 4
    assert overscan_info.height == 4
    assert overscan_info.data_window == (-2, -2, 8, 8)
    assert overscan_info.display_window == (0, 0, 4, 4)
    assert overscan_info.pixel_aspect == pytest.approx(1.25)
    assert overscan_info.attributes.get("shot") == "sh010"

    norm_overscan = reader.read_imagebuf(overscan_path)
    assert norm_overscan.spec().x == 0
    assert norm_overscan.spec().y == 0
    assert norm_overscan.spec().width == 4
    assert norm_overscan.spec().height == 4
    norm_overscan_px = norm_overscan.get_pixels(oiio.FLOAT)
    assert np.allclose(norm_overscan_px, [0.25, 0.5, 0.75], atol=1e-5)

    norm_cropped = reader.read_imagebuf(cropped_path)
    assert norm_cropped.spec().x == 0
    assert norm_cropped.spec().y == 0
    assert norm_cropped.spec().width == 4
    assert norm_cropped.spec().height == 4
    norm_cropped_px = norm_cropped.get_pixels(oiio.FLOAT)
    assert np.allclose(norm_cropped_px[1:3, 1:3], 0.8, atol=1e-5)
    assert np.allclose(norm_cropped_px[0, 0], 0.0, atol=1e-5)


if __name__ == "__main__":
    pytest.main([__file__])
