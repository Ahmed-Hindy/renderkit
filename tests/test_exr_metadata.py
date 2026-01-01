from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from renderkit.io.image_reader import EXRReader


def test_exr_metadata_fps_detection():
    """Test that EXRReader correctly extracts FPS from various metadata keys."""
    reader = EXRReader()
    mock_path = Path("test.exr")

    with patch("pathlib.Path.exists", return_value=True):
        with patch("OpenEXR.InputFile") as mock_exr:
            # Case 1: Standard framesPerSecond (Rational)
            mock_val = MagicMock()
            mock_val.n = 24
            mock_val.d = 1
            mock_exr.return_value.header.return_value = {"framesPerSecond": mock_val}

            fps = reader.get_metadata_fps(mock_path)
            assert fps == 24.0

            # Case 2: Arnold-style fps (Float)
            mock_exr.return_value.header.return_value = {"arnold/fps": 23.976}
            fps = reader.get_metadata_fps(mock_path)
            assert fps == 23.976

            # Case 3: Karma-style fps (Float)
            mock_exr.return_value.header.return_value = {"exr/FramesPerSecond": 24.0}
            fps = reader.get_metadata_fps(mock_path)
            assert fps == 24.0

            # Case 4: Rational as tuple
            mock_exr.return_value.header.return_value = {"fps": (30000, 1001)}
            fps = reader.get_metadata_fps(mock_path)
            assert abs(fps - 29.97) < 0.01

            # Case 5: String metadata (float)
            mock_exr.return_value.header.return_value = {"exr/FramesPerSecond": "24.0"}
            fps = reader.get_metadata_fps(mock_path)
            assert fps == 24.0

            # Case 6: Bytes metadata
            mock_exr.return_value.header.return_value = {"fps": b"23.976fps"}
            fps = reader.get_metadata_fps(mock_path)
            assert fps == 23.976

            # Case 7: Case-insensitive match
            mock_exr.return_value.header.return_value = {"EXR/framespersecond": 24.0}
            fps = reader.get_metadata_fps(mock_path)
            assert fps == 24.0

            # Case 8: Rational string
            mock_exr.return_value.header.return_value = {"framesPerSecond": "24000/1001"}
            fps = reader.get_metadata_fps(mock_path)
            assert abs(fps - 23.976) < 0.001

            # Case 9: Invalid string
            mock_exr.return_value.header.return_value = {"fps": "invalid"}
            fps = reader.get_metadata_fps(mock_path)
            assert fps is None


def test_exr_metadata_color_space_detection():
    """Test that EXRReader correctly extracts Color Space from various metadata keys."""
    reader = EXRReader()
    mock_path = Path("test.exr")

    with patch("pathlib.Path.exists", return_value=True):
        with patch("OpenEXR.InputFile") as mock_exr:
            # Case 1: Standard exr/oiio:ColorSpace
            mock_exr.return_value.header.return_value = {"exr/oiio:ColorSpace": "ACES - ACEScg"}
            cs = reader.get_metadata_color_space(mock_path)
            assert cs == "ACES - ACEScg"

            # Case 2: colorSpace
            mock_exr.return_value.header.return_value = {"colorSpace": "Linear"}
            cs = reader.get_metadata_color_space(mock_path)
            assert cs == "Linear"

            # Case 3: interchange/color_space
            mock_exr.return_value.header.return_value = {"interchange/color_space": "Rec.709"}
            cs = reader.get_metadata_color_space(mock_path)
            assert cs == "Rec.709"

            # Case 4: Case-insensitive
            mock_exr.return_value.header.return_value = {"EXR/OIIO:COLORSPACE": "ACEScg"}
            cs = reader.get_metadata_color_space(mock_path)
            assert cs == "ACEScg"

            # Case 5: Bytes
            mock_exr.return_value.header.return_value = {"colorSpace": b"sRGB"}
            cs = reader.get_metadata_color_space(mock_path)
            assert cs == "sRGB"


if __name__ == "__main__":
    pytest.main([__file__])
