"""Configuration classes using Builder pattern for conversion settings."""

from dataclasses import dataclass
from typing import Optional

from renderkit.exceptions import ConfigurationError
from renderkit.processing.color_space import ColorSpacePreset


@dataclass
class ConversionConfig:
    """Configuration for image sequence to video conversion."""

    input_pattern: str
    output_path: str
    fps: Optional[float] = None
    color_space_preset: ColorSpacePreset = ColorSpacePreset.LINEAR_TO_SRGB
    width: Optional[int] = None
    height: Optional[int] = None
    codec: str = "mp4v"
    bitrate: Optional[int] = None
    start_frame: Optional[int] = None
    end_frame: Optional[int] = None
    use_multiprocessing: bool = False
    num_workers: Optional[int] = None

    def __post_init__(self) -> None:
        """Validate configuration after initialization."""
        if self.fps is not None and self.fps <= 0:
            raise ConfigurationError("FPS must be greater than 0")
        if self.width is not None and self.width <= 0:
            raise ConfigurationError("Width must be greater than 0")
        if self.height is not None and self.height <= 0:
            raise ConfigurationError("Height must be greater than 0")
        if self.start_frame is not None and self.end_frame is not None:
            if self.start_frame > self.end_frame:
                raise ConfigurationError("Start frame must be <= end frame")
        if self.num_workers is not None and self.num_workers <= 0:
            raise ConfigurationError("Number of workers must be greater than 0")


class ConversionConfigBuilder:
    """Builder for ConversionConfig using Builder pattern."""

    def __init__(self) -> None:
        """Initialize the builder."""
        self._input_pattern: Optional[str] = None
        self._output_path: Optional[str] = None
        self._fps: Optional[float] = None
        self._color_space_preset: ColorSpacePreset = ColorSpacePreset.LINEAR_TO_SRGB
        self._width: Optional[int] = None
        self._height: Optional[int] = None
        self._codec: str = "mp4v"
        self._bitrate: Optional[int] = None
        self._start_frame: Optional[int] = None
        self._end_frame: Optional[int] = None
        self._use_multiprocessing: bool = False
        self._num_workers: Optional[int] = None

    def with_input_pattern(self, pattern: str) -> "ConversionConfigBuilder":
        """Set the input file pattern."""
        self._input_pattern = pattern
        return self

    def with_output_path(self, path: str) -> "ConversionConfigBuilder":
        """Set the output video path."""
        self._output_path = path
        return self

    def with_fps(self, fps: float) -> "ConversionConfigBuilder":
        """Set the frame rate."""
        self._fps = fps
        return self

    def with_color_space_preset(self, preset: ColorSpacePreset) -> "ConversionConfigBuilder":
        """Set the color space preset."""
        self._color_space_preset = preset
        return self

    def with_resolution(self, width: int, height: int) -> "ConversionConfigBuilder":
        """Set the output resolution."""
        self._width = width
        self._height = height
        return self

    def with_codec(self, codec: str) -> "ConversionConfigBuilder":
        """Set the video codec."""
        self._codec = codec
        return self

    def with_bitrate(self, bitrate: int) -> "ConversionConfigBuilder":
        """Set the video bitrate."""
        self._bitrate = bitrate
        return self

    def with_frame_range(self, start: int, end: int) -> "ConversionConfigBuilder":
        """Set the frame range."""
        self._start_frame = start
        self._end_frame = end
        return self

    def with_multiprocessing(
        self, enabled: bool = True, num_workers: Optional[int] = None
    ) -> "ConversionConfigBuilder":
        """Enable multiprocessing for batch operations."""
        self._use_multiprocessing = enabled
        self._num_workers = num_workers
        return self

    def build(self) -> ConversionConfig:
        """Build the ConversionConfig object."""
        if self._input_pattern is None:
            raise ConfigurationError("Input pattern is required")
        if self._output_path is None:
            raise ConfigurationError("Output path is required")

        return ConversionConfig(
            input_pattern=self._input_pattern,
            output_path=self._output_path,
            fps=self._fps,
            color_space_preset=self._color_space_preset,
            width=self._width,
            height=self._height,
            codec=self._codec,
            bitrate=self._bitrate,
            start_frame=self._start_frame,
            end_frame=self._end_frame,
            use_multiprocessing=self._use_multiprocessing,
            num_workers=self._num_workers,
        )
