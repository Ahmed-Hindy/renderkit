"""Tests for file utilities."""

from pathlib import Path

import pytest

from image_video_processor.io.file_utils import FileUtils


class TestFileUtils:
    """Tests for FileUtils."""

    def test_get_file_extension(self) -> None:
        """Test getting file extension."""
        assert FileUtils.get_file_extension(Path("test.exr")) == "exr"
        assert FileUtils.get_file_extension(Path("test.PNG")) == "png"
        assert FileUtils.get_file_extension(Path("test.file.jpg")) == "jpg"

    def test_is_image_file(self) -> None:
        """Test image file detection."""
        assert FileUtils.is_image_file(Path("test.exr")) is True
        assert FileUtils.is_image_file(Path("test.png")) is True
        assert FileUtils.is_image_file(Path("test.jpg")) is True
        assert FileUtils.is_image_file(Path("test.jpeg")) is True
        assert FileUtils.is_image_file(Path("test.txt")) is False

    def test_ensure_directory(self, tmp_path: Path) -> None:
        """Test directory creation."""
        new_dir = tmp_path / "new" / "nested" / "directory"
        FileUtils.ensure_directory(new_dir)

        assert new_dir.exists()
        assert new_dir.is_dir()

    def test_get_file_size(self, tmp_path: Path) -> None:
        """Test getting file size."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")

        size = FileUtils.get_file_size(test_file)
        assert size > 0

        # Non-existent file
        non_existent = tmp_path / "nonexistent.txt"
        assert FileUtils.get_file_size(non_existent) == 0

    def test_validate_output_path(self, tmp_path: Path) -> None:
        """Test output path validation."""
        output_file = tmp_path / "output" / "test.mp4"

        # Should create directory and return True
        assert FileUtils.validate_output_path(output_file, overwrite=False) is True
        assert output_file.parent.exists()

        # Create file and test overwrite
        output_file.write_text("test")
        assert FileUtils.validate_output_path(output_file, overwrite=True) is True
        assert FileUtils.validate_output_path(output_file, overwrite=False) is False

