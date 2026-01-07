"""Configuration classes using Builder pattern for conversion settings."""

from dataclasses import dataclass, field
from typing import Optional

from renderkit.exceptions import ConfigurationError
from renderkit.processing.color_space import ColorSpacePreset


@dataclass
class BurnInElement:
    """Individual burn-in element configuration."""

    text_template: str  # e.g. "Frame: {frame}"
    x: int = 50
    y: int = 50
    font: str = ""  # Default OIIO font
    font_size: int = 24
    color: tuple[float, float, float] = (1.0, 1.0, 1.0)
    alignment: str = "left"  # left, center, right


@dataclass
class BurnInConfig:
    """Configuration for all burn-ins on a frame."""

    elements: list[BurnInElement] = field(default_factory=list)
    use_background: bool = True
    background_opacity: int = 30  # 0-100 percentage


@dataclass
class ContactSheetConfig:
    """Configuration for contact sheet layout in multi-AOV mode."""

    columns: int = 4
    thumbnail_width: int = 512
    padding: int = 10
    background_color: tuple[float, float, float] = (0.1, 0.1, 0.1)
    show_labels: bool = True
    font_size: int = 12

    def __post_init__(self) -> None:
        """Validate configuration."""
        if self.columns <= 0:
            raise ConfigurationError("Columns must be greater than 0")
        if self.thumbnail_width <= 0:
            raise ConfigurationError("Thumbnail width must be greater than 0")
        if self.padding < 0:
            raise ConfigurationError("Padding cannot be negative")


class ContactSheetConfigBuilder:
    """Builder for ContactSheetConfig."""

    def __init__(self) -> None:
        """Initialize builder."""
        self._columns: int = 4
        self._thumbnail_width: int = 512
        self._padding: int = 10
        self._background_color: tuple[float, float, float] = (0.1, 0.1, 0.1)
        self._show_labels: bool = True
        self._font_size: int = 12

    def with_columns(self, columns: int) -> "ContactSheetConfigBuilder":
        """Set number of columns."""
        self._columns = columns
        return self

    def with_thumbnail_width(self, width: int) -> "ContactSheetConfigBuilder":
        """Set thumbnail width."""
        self._thumbnail_width = width
        return self

    def with_padding(self, padding: int) -> "ContactSheetConfigBuilder":
        """Set padding between thumbnails."""
        self._padding = padding
        return self

    def with_labels(self, show: bool, font_size: int = 12) -> "ContactSheetConfigBuilder":
        """Set label options."""
        self._show_labels = show
        self._font_size = font_size
        return self

    def build(self) -> ContactSheetConfig:
        """Build ContactSheetConfig."""
        return ContactSheetConfig(
            columns=self._columns,
            thumbnail_width=self._thumbnail_width,
            padding=self._padding,
            background_color=self._background_color,
            show_labels=self._show_labels,
            font_size=self._font_size,
        )


@dataclass
class ConversionConfig:
    """Configuration for image sequence to video conversion."""

    input_pattern: str
    output_path: str
    fps: Optional[float] = None
    color_space_preset: ColorSpacePreset = ColorSpacePreset.LINEAR_TO_SRGB
    width: Optional[int] = None
    height: Optional[int] = None
    codec: str = "libx265"
    bitrate: Optional[int] = None
    quality: int = 10  # 0-10, 10 is best
    layer: Optional[str] = None  # Specific layer to extract (e.g. "diffuse")
    start_frame: Optional[int] = None
    end_frame: Optional[int] = None
    use_multiprocessing: bool = False
    num_workers: Optional[int] = None
    explicit_input_color_space: Optional[str] = (
        None  # Force specific input space (e.g. "ACES - ACEScg")
    )
    burnin_config: Optional[BurnInConfig] = None
    contact_sheet_mode: bool = False
    contact_sheet_config: Optional[ContactSheetConfig] = None

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
        self._codec: str = "libx265"
        self._bitrate: Optional[int] = None
        self._quality: int = 10
        self._layer: Optional[str] = None
        self._start_frame: Optional[int] = None
        self._end_frame: Optional[int] = None
        self._use_multiprocessing: bool = False
        self._num_workers: Optional[int] = None
        self._explicit_input_color_space: Optional[str] = None
        self._burnin_config: Optional[BurnInConfig] = None
        self._contact_sheet_mode: bool = False
        self._contact_sheet_config: Optional[ContactSheetConfig] = None

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

    def with_explicit_input_color_space(self, space_name: str) -> "ConversionConfigBuilder":
        """Set explicit input color space name (for OCIO)."""
        self._explicit_input_color_space = space_name
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

    def with_quality(self, quality: int) -> "ConversionConfigBuilder":
        """Set the video quality (0-10)."""
        self._quality = quality
        return self

    def with_layer(self, layer: str) -> "ConversionConfigBuilder":
        """Set the EXR layer to extract."""
        self._layer = layer
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

    def with_burnin(self, config: BurnInConfig) -> "ConversionConfigBuilder":
        """Set the burn-in configuration."""
        self._burnin_config = config
        return self

    def with_contact_sheet(
        self, enabled: bool = True, config: Optional[ContactSheetConfig] = None
    ) -> "ConversionConfigBuilder":
        """Enable contact sheet mode."""
        self._contact_sheet_mode = enabled
        self._contact_sheet_config = config
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
            quality=self._quality,
            layer=self._layer,
            start_frame=self._start_frame,
            end_frame=self._end_frame,
            use_multiprocessing=self._use_multiprocessing,
            num_workers=self._num_workers,
            explicit_input_color_space=self._explicit_input_color_space,
            burnin_config=self._burnin_config,
            contact_sheet_mode=self._contact_sheet_mode,
            contact_sheet_config=self._contact_sheet_config,
        )
