from pathlib import Path
from unittest.mock import patch

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


if __name__ == "__main__":
    pytest.main([__file__])
