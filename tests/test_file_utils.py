"""Tests for file utilities."""

from pathlib import Path

from renderkit.io.file_utils import FileUtils


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

    def test_convert_path_to_pattern(self, tmp_path: Path) -> None:
        """Test converting a file path into a sequence pattern."""
        file_path = tmp_path / "render.0001.exr"
        converted = FileUtils.convert_path_to_pattern(str(file_path))
        converted_path = Path(converted)

        assert converted_path.parent == tmp_path
        assert converted_path.name == "render.####.exr"

        no_digits = tmp_path / "render.exr"
        no_digits_converted = FileUtils.convert_path_to_pattern(str(no_digits))
        assert Path(no_digits_converted) == no_digits

    def test_detect_sequence_and_sample_frame(self, tmp_path: Path) -> None:
        """Test sequence detection and sample frame selection."""
        (tmp_path / "render.0001.exr").write_text("one")
        (tmp_path / "render.0002.exr").write_text("two")

        pattern = str(tmp_path / "render.####.exr")
        frames = FileUtils.detect_sequence(pattern)
        assert frames == [1, 2]

        sample_path = FileUtils.get_sample_frame_from_pattern(pattern)
        assert sample_path is not None
        assert sample_path.name == "render.0001.exr"

        missing_pattern = str(tmp_path / "missing.####.exr")
        assert FileUtils.get_sample_frame_from_pattern(missing_pattern) is None
