from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Rect:
    x: float
    y: float
    width: float
    height: float

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height


@dataclass(frozen=True, slots=True)
class ScreenFrame:
    time: float
    rect: Rect
    opacity: float


@dataclass(frozen=True, slots=True)
class SkinConfig:
    enabled: bool = False
    wallpaper_path: str | None = None


@dataclass(frozen=True, slots=True)
class AppConfig:
    app_id: str
    process_names: tuple[str, ...]
    process_path_fragment: str
    video_path: str
    poster_path: str
    duration: float
    transition_start: float
    transition_end: float
    max_wait_seconds: float
    volume: float
    screen_frames: tuple[ScreenFrame, ...]
    skin: SkinConfig = field(default_factory=SkinConfig)
