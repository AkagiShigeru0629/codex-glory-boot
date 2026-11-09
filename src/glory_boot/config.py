import json
import math
from pathlib import Path
from typing import Any, NoReturn

from glory_boot.domain.models import AppConfig, Rect, ScreenFrame, SkinConfig


CONFIG_RELATIVE_PATH = Path("config") / "launcher.example.json"


class ConfigError(ValueError):
    """启动器配置无法安全使用。"""


def _reject_constant(value: str) -> NoReturn:
    raise ConfigError(f"配置包含非有限数值: {value}")


def _number(mapping: dict[str, Any], key: str) -> float:
    value = mapping.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{key} 必须是数值")
    converted = float(value)
    if not math.isfinite(converted):
        raise ConfigError(f"{key} 必须是有限数值")
    return converted


def _text(mapping: dict[str, Any], key: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str):
        raise ConfigError(f"{key} 必须是字符串")
    return value


def _parse_screen_frames(
    raw_frames: object,
) -> tuple[ScreenFrame, ...]:
    if not isinstance(raw_frames, list) or not raw_frames:
        raise ConfigError("screen_frames 必须是非空数组")

    frames: list[ScreenFrame] = []
    for index, raw_frame in enumerate(raw_frames):
        if not isinstance(raw_frame, dict):
            raise ConfigError(f"screen_frames[{index}] 必须是对象")
        raw_rect = raw_frame.get("rect")
        if not isinstance(raw_rect, dict):
            raise ConfigError(f"screen_frames[{index}].rect 必须是对象")
        frames.append(
            ScreenFrame(
                time=_number(raw_frame, "time"),
                rect=Rect(
                    x=_number(raw_rect, "x"),
                    y=_number(raw_rect, "y"),
                    width=_number(raw_rect, "width"),
                    height=_number(raw_rect, "height"),
                ),
                opacity=_number(raw_frame, "opacity"),
            )
        )
    return tuple(frames)


def _parse_skin(raw_skin: object, root: Path) -> SkinConfig:
    if raw_skin is None:
        return SkinConfig()
    if not isinstance(raw_skin, dict):
        raise ConfigError("skin 必须是对象")

    enabled = raw_skin.get("enabled", False)
    if not isinstance(enabled, bool):
        raise ConfigError("skin.enabled 必须是布尔值")

    raw_path = raw_skin.get("wallpaper_path")
    if raw_path is not None and not isinstance(raw_path, str):
        raise ConfigError("skin.wallpaper_path 必须是字符串或 null")
    if not raw_path:
        return SkinConfig(enabled=enabled)

    return SkinConfig(
        enabled=enabled,
        wallpaper_path=str((root / raw_path).resolve()),
    )


def load_config(root: Path) -> AppConfig:
    config_path = root / CONFIG_RELATIVE_PATH
    try:
        raw = json.loads(
            config_path.read_text(encoding="utf-8"),
            parse_constant=_reject_constant,
        )
    except FileNotFoundError as exc:
        raise ConfigError(f"找不到配置文件: {config_path}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"配置文件不是有效 JSON: {exc}") from exc

    if not isinstance(raw, dict):
        raise ConfigError("配置文件顶层必须是对象")

    raw_process_names = raw.get("process_names")
    if not isinstance(raw_process_names, list) or not all(
        isinstance(name, str) for name in raw_process_names
    ):
        raise ConfigError("process_names 必须是字符串数组")

    config = AppConfig(
        app_id=_text(raw, "app_id"),
        process_names=tuple(raw_process_names),
        process_path_fragment=_text(raw, "process_path_fragment"),
        video_path=_text(raw, "video_path"),
        poster_path=_text(raw, "poster_path"),
        duration=_number(raw, "duration"),
        hold_at=_number(raw, "hold_at"),
        transition_start=_number(raw, "transition_start"),
        transition_end=_number(raw, "transition_end"),
        max_wait_seconds=_number(raw, "max_wait_seconds"),
        volume=_number(raw, "volume"),
        screen_frames=_parse_screen_frames(raw.get("screen_frames")),
        skin=_parse_skin(raw.get("skin"), root),
    )
    validate_config(config)

    video_path = (root / config.video_path).resolve()
    poster_path = (root / config.poster_path).resolve()
    if not video_path.is_file():
        raise ConfigError(f"video_path 指向的文件不存在: {video_path}")
    if not poster_path.is_file():
        raise ConfigError(f"poster_path 指向的文件不存在: {poster_path}")

    return AppConfig(
        app_id=config.app_id,
        process_names=config.process_names,
        process_path_fragment=config.process_path_fragment,
        video_path=str(video_path),
        poster_path=str(poster_path),
        duration=config.duration,
        hold_at=config.hold_at,
        transition_start=config.transition_start,
        transition_end=config.transition_end,
        max_wait_seconds=config.max_wait_seconds,
        volume=config.volume,
        screen_frames=config.screen_frames,
        skin=config.skin,
    )


def validate_config(config: AppConfig) -> None:
    if not config.app_id.strip() or "!" not in config.app_id:
        raise ConfigError("app_id 必须是有效的 Microsoft Store 应用标识")
    if not config.process_names or any(
        not name.strip() for name in config.process_names
    ):
        raise ConfigError("process_names 不能为空")
    if not config.process_path_fragment.strip():
        raise ConfigError("process_path_fragment 不能为空")

    numeric_values = {
        "duration": config.duration,
        "hold_at": config.hold_at,
        "transition_start": config.transition_start,
        "transition_end": config.transition_end,
        "max_wait_seconds": config.max_wait_seconds,
        "volume": config.volume,
    }
    for key, value in numeric_values.items():
        if not math.isfinite(value):
            raise ConfigError(f"{key} 必须是有限数值")

    if not (
        0 <= config.hold_at
        < config.transition_start
        < config.transition_end
        < config.duration
    ):
        raise ConfigError("时间线必须严格递增并位于动画时长内")
    if config.max_wait_seconds < 10:
        raise ConfigError("max_wait_seconds 不能小于 10 秒")
    if not 0 <= config.volume <= 1:
        raise ConfigError("volume 必须位于 0 到 1 之间")

    if not config.screen_frames:
        raise ConfigError("screen_frames 不能为空")

    previous_time = -math.inf
    for index, frame in enumerate(config.screen_frames):
        if not math.isfinite(frame.time):
            raise ConfigError(f"关键帧 {index} 的时间必须是有限数值")
        if frame.time <= previous_time:
            raise ConfigError("关键帧时间必须严格递增且不能重复")
        if not 0 <= frame.time <= config.duration:
            raise ConfigError(f"关键帧 {index} 的时间超出动画范围")
        previous_time = frame.time

        rect_values = (
            frame.rect.x,
            frame.rect.y,
            frame.rect.width,
            frame.rect.height,
        )
        if not all(math.isfinite(value) for value in rect_values):
            raise ConfigError(f"关键帧 {index} 的矩形必须是有限数值")
        if frame.rect.width <= 0 or frame.rect.height <= 0:
            raise ConfigError(f"关键帧 {index} 的宽高必须大于零")
        if (
            frame.rect.x < 0
            or frame.rect.y < 0
            or frame.rect.right > 1
            or frame.rect.bottom > 1
        ):
            raise ConfigError(f"关键帧 {index} 超出规范化屏幕范围")
        if not math.isfinite(frame.opacity) or not 0 <= frame.opacity <= 1:
            raise ConfigError(f"关键帧 {index} 的透明度必须位于 0 到 1 之间")
