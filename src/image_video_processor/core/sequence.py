"""Sequence detection and parsing for frame sequences."""

import re
from pathlib import Path
from typing import Optional

from image_video_processor.exceptions import SequenceDetectionError


class FrameSequence:
    """Represents a detected frame sequence."""

    def __init__(
        self,
        base_path: Path,
        pattern: str,
        frame_numbers: list[int],
        padding: int,
    ) -> None:
        """Initialize frame sequence.

        Args:
            base_path: Base path to the sequence directory
            pattern: The detected pattern (e.g., "render.%04d.exr")
            frame_numbers: List of frame numbers in the sequence
            padding: Number of digits used for padding
        """
        self.base_path = base_path
        self.pattern = pattern
        self.frame_numbers = sorted(frame_numbers)
        self.padding = padding

    def get_file_path(self, frame_number: int) -> Path:
        """Get the file path for a specific frame number.

        Args:
            frame_number: The frame number

        Returns:
            Path to the frame file
        """
        # Replace common patterns with the actual frame number
        frame_str = str(frame_number).zfill(self.padding)
        file_path = self.pattern.replace("%04d", frame_str)
        file_path = file_path.replace("$F4", frame_str)
        file_path = re.sub(r"#+", lambda m: frame_str.zfill(len(m.group())), file_path)

        return self.base_path / file_path

    def __len__(self) -> int:
        """Return the number of frames in the sequence."""
        return len(self.frame_numbers)

    def __repr__(self) -> str:
        """Return string representation."""
        return (
            f"FrameSequence(pattern={self.pattern}, "
            f"frames={len(self.frame_numbers)}, "
            f"range=[{self.frame_numbers[0]}-{self.frame_numbers[-1]}])"
        )


class SequenceDetector:
    """Detects and parses frame sequences from file patterns."""

    # Common VFX frame number patterns
    PATTERNS = [
        (r"%(\d+)d", "%04d"),  # Houdini style: render.%04d.exr
        (r"\$F(\d+)", "$F4"),  # Houdini style: render.$F4.exr
        (r"(#+)", "####"),  # Maya style: render.####.exr
        (r"(\d+)", "0001"),  # Numeric: render.0001.exr
    ]

    @staticmethod
    def detect_sequence(pattern: str) -> FrameSequence:
        """Detect a frame sequence from a pattern string.

        Supports patterns like:
        - render.%04d.exr (Houdini)
        - render.$F4.exr (Houdini)
        - render.####.exr (Maya)
        - render.0001.exr (numeric)

        Args:
            pattern: File pattern with frame number placeholder

        Returns:
            FrameSequence object

        Raises:
            SequenceDetectionError: If sequence cannot be detected
        """
        pattern_path = Path(pattern)
        base_path = pattern_path.parent
        filename = pattern_path.name

        # Try to detect which pattern is being used
        detected_pattern = None
        padding = 4
        frame_numbers: list[int] = []

        # Check for %04d pattern
        if "%" in filename and "d" in filename:
            match = re.search(r"%(\d+)d", filename)
            if match:
                padding = int(match.group(1))
                detected_pattern = filename
                # Find all matching files
                frame_numbers = SequenceDetector._find_frames_by_pattern(
                    base_path, filename, padding, "%04d"
                )

        # Check for $F4 pattern
        elif "$F" in filename:
            match = re.search(r"\$F(\d+)", filename)
            if match:
                padding = int(match.group(1))
                detected_pattern = filename
                frame_numbers = SequenceDetector._find_frames_by_pattern(
                    base_path, filename, padding, "$F4"
                )

        # Check for #### pattern
        elif "#" in filename:
            match = re.search(r"(#+)", filename)
            if match:
                padding = len(match.group(1))
                detected_pattern = filename
                frame_numbers = SequenceDetector._find_frames_by_pattern(
                    base_path, filename, padding, "####"
                )

        # Check for numeric pattern (e.g., render.0001.exr)
        else:
            numeric_match = re.search(r"(\d+)", filename)
            if numeric_match:
                # Try to find sequence by replacing the number
                frame_numbers = SequenceDetector._find_frames_by_numeric_pattern(
                    base_path, filename, numeric_match
                )
                if frame_numbers:
                    padding = len(numeric_match.group(1))
                    detected_pattern = filename

        if not frame_numbers:
            raise SequenceDetectionError(f"Could not detect frame sequence from pattern: {pattern}")

        return FrameSequence(base_path, detected_pattern or filename, frame_numbers, padding)

    @staticmethod
    def _find_frames_by_pattern(
        base_path: Path, pattern: str, padding: int, placeholder: str
    ) -> list[int]:
        """Find frame numbers matching a pattern.

        Args:
            base_path: Directory to search
            pattern: Pattern string with placeholder
            padding: Number of digits for padding
            placeholder: The placeholder string to replace

        Returns:
            List of frame numbers found
        """
        frame_numbers: list[int] = []
        pattern_regex = pattern

        # Convert pattern to regex
        if placeholder == "%04d":
            pattern_regex = re.sub(r"%\d+d", lambda m: r"(\d+)", pattern)
        elif placeholder == "$F4":
            pattern_regex = re.sub(r"\$F\d+", lambda m: r"(\d+)", pattern)
        elif placeholder == "####":
            pattern_regex = re.sub(r"#+", lambda m: r"(\d+)", pattern)

        regex = re.compile(pattern_regex)

        # Search for matching files
        if base_path.exists():
            for file_path in base_path.iterdir():
                if file_path.is_file():
                    match = regex.match(file_path.name)
                    if match:
                        try:
                            frame_num = int(match.group(1))
                            frame_numbers.append(frame_num)
                        except (ValueError, IndexError):
                            continue

        return sorted(frame_numbers)

    @staticmethod
    def _find_frames_by_numeric_pattern(
        base_path: Path, filename: str, numeric_match: re.Match[str]
    ) -> list[int]:
        """Find frame numbers by replacing numeric part of filename.

        Args:
            base_path: Directory to search
            filename: Filename with numeric pattern
            numeric_match: Regex match object for the numeric part

        Returns:
            List of frame numbers found
        """
        frame_numbers: list[int] = []
        start_pos, end_pos = numeric_match.span()
        prefix = filename[:start_pos]
        suffix = filename[end_pos:]

        # Try to find files with same prefix/suffix but different numbers
        if base_path.exists():
            pattern_regex = re.compile(re.escape(prefix) + r"(\d+)" + re.escape(suffix))
            for file_path in base_path.iterdir():
                if file_path.is_file():
                    match = pattern_regex.match(file_path.name)
                    if match:
                        try:
                            frame_num = int(match.group(1))
                            frame_numbers.append(frame_num)
                        except ValueError:
                            continue

        return sorted(frame_numbers)

    @staticmethod
    def auto_detect_fps(
        frame_numbers: list[int], default_fps: Optional[float] = None
    ) -> Optional[float]:
        """Auto-detect frame rate from frame numbers (if possible).

        This is a simple heuristic that assumes constant frame rate.
        For more accurate detection, would need metadata or user input.

        Args:
            frame_numbers: List of frame numbers
            default_fps: Default FPS to return if detection fails

        Returns:
            Detected FPS or default, or None if cannot determine
        """
        # This is a placeholder - real FPS detection would require
        # file metadata or timestamps
        # For now, return default or None
        return default_fps
