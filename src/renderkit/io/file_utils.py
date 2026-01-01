"""File I/O utilities."""

import logging
from pathlib import Path

from renderkit import constants

logger = logging.getLogger(__name__)


class FileUtils:
    """Utility class for file operations."""

    @staticmethod
    def ensure_directory(path: Path) -> None:
        """Ensure a directory exists, creating it if necessary.

        Args:
            path: Path to the directory
        """
        path.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def get_file_extension(path: Path) -> str:
        """Get the file extension (lowercase, without dot).

        Args:
            path: Path to the file

        Returns:
            File extension
        """
        return path.suffix.lower().lstrip(".")

    @staticmethod
    def is_image_file(path: Path) -> bool:
        """Check if a file is a supported image format.

        Args:
            path: Path to the file

        Returns:
            True if file is a supported image format
        """
        return FileUtils.get_file_extension(path) in constants.OIIO_SUPPORTED_EXTENSIONS

    @staticmethod
    def find_files_by_pattern(directory: Path, pattern: str, recursive: bool = False) -> list[Path]:
        """Find files matching a pattern.

        Args:
            directory: Directory to search
            pattern: Filename pattern (supports wildcards)
            recursive: Whether to search recursively

        Returns:
            List of matching file paths
        """
        if not directory.exists():
            logger.warning(f"Directory does not exist: {directory}")
            return []

        if recursive:
            return list(directory.rglob(pattern))
        return list(directory.glob(pattern))

    @staticmethod
    def get_file_size(path: Path) -> int:
        """Get file size in bytes.

        Args:
            path: Path to the file

        Returns:
            File size in bytes, or 0 if file doesn't exist
        """
        if path.exists():
            return path.stat().st_size
        return 0

    @staticmethod
    def validate_output_path(path: Path, overwrite: bool = False) -> bool:
        """Validate that output path can be written to.

        Args:
            path: Output file path
            overwrite: Whether to allow overwriting existing files

        Returns:
            True if path is valid for writing
        """
        if path.exists() and not overwrite:
            logger.warning(f"Output file already exists: {path}")
            return False

        # Ensure parent directory exists
        FileUtils.ensure_directory(path.parent)
        return True

    @staticmethod
    def validate_output_filename(path_str: str) -> tuple[bool, str]:
        """Check if the output filename is valid for video encoding.

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not path_str.strip():
            return False, "Output path is empty."

        path = Path(path_str.strip())

        # Check extension
        ext = path.suffix.lower().lstrip(".")
        if not ext:
            return False, "Output path must have a file extension (e.g., .mp4)."

        if ext not in constants.SUPPORTED_VIDEO_EXTENSIONS:
            return (
                False,
                f"Unsupported video extension: .{ext}. Supported: {', '.join(constants.SUPPORTED_VIDEO_EXTENSIONS)}",
            )

        # Check for invalid characters in filename (basic check)
        invalid_chars = '<>:"|?*'
        if any(c in path.name for c in invalid_chars):
            return False, f"Filename contains invalid characters: {invalid_chars}"

        return True, ""
