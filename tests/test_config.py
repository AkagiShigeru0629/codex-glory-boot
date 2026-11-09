import json
from pathlib import Path
from typing import Any

import pytest

from glory_boot.config import ConfigError, load_config, validate_config
from glory_boot.domain.models import AppConfig, Rect, ScreenFrame


ROOT = Path(__file__).resolve().parents[1]


def _default_config_data() -> dict[str, Any]:
    return {
        "app_id": "OpenAI.Codex_2p2nqsd0c76g0!App",
        "process_names": ["Codex.exe"],
        "process_path_fragment": "OpenAI.Codex_",
        "video_path": "media/startup.mp4",
        "poster_path": "media/poster.png",
        "duration": 8.0,
        "hold_at": 6.4,
        "transition_start": 6.7,
        "transition_end": 7.6,
        "max_wait_seconds": 60.0,
        "volume": 0.35,
        "screen_frames": [
            {
                "time": 0.0,
                "rect": {
                    "x": 0.36,
                    "y": 0.18,
                    "width": 0.28,
                    "height": 0.64,
                },
                "opacity": 0.75,
            },
            {
                "time": 6.7,
                "rect": {
                    "x": 0.28,
                    "y": 0.12,
                    "width": 0.44,
                    "height": 0.76,
                },
                "opacity": 0.95,
            },
            {
                "time": 7.6,
                "rect": {
                    "x": 0.0,
                    "y": 0.0,
                    "width": 1.0,
                    "height": 1.0,
                },
                "opacity": 1.0,
            },
        ],
    }


def _write_config(
    root: Path,
    data: dict[str, Any] | None = None,
    *,
    create_media: bool = True,
) -> Path:
    config_dir = root / "config"
    config_dir.mkdir(parents=True)
    config_path = config_dir / "launcher.example.json"
    payload = _default_config_data() if data is None else data
    config_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    if create_media:
        media_dir = root / "media"
        media_dir.mkdir()
        (media_dir / "startup.mp4").write_bytes(b"fake video")
        (media_dir / "poster.png").write_bytes(b"fake poster")

    return config_path


def test_load_config_accepts_example_and_resolves_media_paths(
    tmp_path: Path,
) -> None:
    _write_config(tmp_path)

    config = load_config(tmp_path)

    assert isinstance(config, AppConfig)
    assert config.process_names == ("Codex.exe",)
    assert config.video_path == str((tmp_path / "media/startup.mp4").resolve())
    assert config.poster_path == str((tmp_path / "media/poster.png").resolve())
    assert config.skin.enabled is False
    assert config.skin.wallpaper_path is None
    assert config.screen_frames[0] == ScreenFrame(
        time=0.0,
        rect=Rect(x=0.36, y=0.18, width=0.28, height=0.64),
        opacity=0.75,
    )


@pytest.mark.parametrize("asset_name", ["video", "poster"])
def test_load_config_rejects_missing_media(
    tmp_path: Path,
    asset_name: str,
) -> None:
    _write_config(tmp_path)
    filename = {
        "video": "startup.mp4",
        "poster": "poster.png",
    }[asset_name]
    (tmp_path / "media" / filename).unlink()

    with pytest.raises(ConfigError, match=asset_name):
        load_config(tmp_path)


@pytest.mark.parametrize("app_id", ["", "   ", "not-an-app-id"])
def test_load_config_rejects_invalid_app_id(
    tmp_path: Path,
    app_id: str,
) -> None:
    data = _default_config_data()
    data["app_id"] = app_id
    _write_config(tmp_path, data)

    with pytest.raises(ConfigError, match="app_id"):
        load_config(tmp_path)


@pytest.mark.parametrize("process_names", [[], [""], ["   "]])
def test_load_config_rejects_empty_process_name(
    tmp_path: Path,
    process_names: list[str],
) -> None:
    data = _default_config_data()
    data["process_names"] = process_names
    _write_config(tmp_path, data)

    with pytest.raises(ConfigError, match="process_names"):
        load_config(tmp_path)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("hold_at", 6.8),
        ("transition_start", 7.6),
        ("transition_end", 8.0),
    ],
)
def test_load_config_rejects_non_increasing_timeline(
    tmp_path: Path,
    field: str,
    value: float,
) -> None:
    data = _default_config_data()
    data[field] = value
    _write_config(tmp_path, data)

    with pytest.raises(ConfigError, match="时间线"):
        load_config(tmp_path)


def test_load_config_rejects_short_maximum_wait(tmp_path: Path) -> None:
    data = _default_config_data()
    data["max_wait_seconds"] = 9.99
    _write_config(tmp_path, data)

    with pytest.raises(ConfigError, match="max_wait_seconds"):
        load_config(tmp_path)


@pytest.mark.parametrize("volume", [-0.01, 1.01])
def test_load_config_rejects_volume_outside_unit_range(
    tmp_path: Path,
    volume: float,
) -> None:
    data = _default_config_data()
    data["volume"] = volume
    _write_config(tmp_path, data)

    with pytest.raises(ConfigError, match="volume"):
        load_config(tmp_path)


def test_load_config_rejects_non_finite_duration(tmp_path: Path) -> None:
    data = _default_config_data()
    data["duration"] = float("nan")
    _write_config(tmp_path, data)

    with pytest.raises(ConfigError, match="有限数值"):
        load_config(tmp_path)


@pytest.mark.parametrize(
    ("axis", "value"),
    [
        ("width", 0.0),
        ("height", 0.0),
    ],
)
def test_load_config_rejects_zero_size_screen_frame(
    tmp_path: Path,
    axis: str,
    value: float,
) -> None:
    data = _default_config_data()
    data["screen_frames"][0]["rect"][axis] = value
    _write_config(tmp_path, data)

    with pytest.raises(ConfigError, match="关键帧"):
        load_config(tmp_path)


def test_load_config_rejects_duplicate_screen_frame_time(
    tmp_path: Path,
) -> None:
    data = _default_config_data()
    data["screen_frames"][1]["time"] = data["screen_frames"][0]["time"]
    _write_config(tmp_path, data)

    with pytest.raises(ConfigError, match="关键帧时间"):
        load_config(tmp_path)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("x", -0.01),
        ("y", 1.01),
        ("width", 1.01),
        ("height", 0.0),
    ],
)
def test_load_config_rejects_screen_frame_outside_normalized_bounds(
    tmp_path: Path,
    key: str,
    value: float,
) -> None:
    data = _default_config_data()
    data["screen_frames"][-1]["rect"][key] = value
    _write_config(tmp_path, data)

    with pytest.raises(ConfigError, match="关键帧"):
        load_config(tmp_path)


def test_validate_config_rejects_out_of_order_screen_frames() -> None:
    config = AppConfig(
        app_id="OpenAI.Codex_2p2nqsd0c76g0!App",
        process_names=("Codex.exe",),
        process_path_fragment="OpenAI.Codex_",
        video_path="video.mp4",
        poster_path="poster.png",
        duration=8.0,
        hold_at=6.3,
        transition_start=6.8,
        transition_end=7.6,
        max_wait_seconds=60.0,
        volume=0.35,
        screen_frames=(
            ScreenFrame(6.8, Rect(0.2, 0.2, 0.5, 0.5), 1.0),
            ScreenFrame(0.0, Rect(0.0, 0.0, 1.0, 1.0), 1.0),
        ),
    )

    with pytest.raises(ConfigError, match="关键帧时间"):
        validate_config(config)


def test_project_config_targets_microsoft_store_chatgpt_executable() -> None:
    config_path = ROOT / "config" / "launcher.example.json"
    data = json.loads(config_path.read_text(encoding="utf-8"))

    assert data["app_id"] == "OpenAI.Codex_2p2nqsd0c76g0!App"
    assert "ChatGPT.exe" in data["process_names"]
    assert data["process_path_fragment"] == "OpenAI.Codex_"


def test_project_config_uses_final_retime_timeline() -> None:
    config_path = ROOT / "config" / "launcher.example.json"
    data = json.loads(config_path.read_text(encoding="utf-8"))

    assert data["hold_at"] == 6.4
    assert data["transition_start"] == 6.7
    assert data["transition_end"] == 7.6
    assert data["screen_frames"][1]["time"] == 6.7
