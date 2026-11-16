import json
from pathlib import Path
from typing import Any

import pytest

from glory_boot.config import ConfigError, load_config


@pytest.fixture
def config_root(tmp_path: Path) -> Path:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    media_dir = tmp_path / "media"
    media_dir.mkdir()
    (media_dir / "startup.mp4").write_bytes(b"fake video")
    (media_dir / "poster.png").write_bytes(b"fake poster")

    base: dict[str, Any] = {
        "app_id": "OpenAI.Codex_2p2nqsd0c76g0!App",
        "process_names": ["Codex.exe"],
        "process_path_fragment": "OpenAI.Codex_",
        "video_path": "media/startup.mp4",
        "poster_path": "media/poster.png",
        "duration": 8.0,
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
            }
        ],
    }
    (config_dir / "launcher.example.json").write_text(
        json.dumps(base),
        encoding="utf-8",
    )
    return tmp_path


def _write_skin(
    root: Path,
    *,
    enabled: object,
    wallpaper_path: object,
) -> None:
    config_path = root / "config" / "launcher.example.json"
    data = json.loads(config_path.read_text(encoding="utf-8"))
    data["skin"] = {
        "enabled": enabled,
        "wallpaper_path": wallpaper_path,
    }
    config_path.write_text(json.dumps(data), encoding="utf-8")


def test_missing_skin_section_defaults_to_disabled(config_root: Path) -> None:
    config = load_config(config_root)

    assert config.skin.enabled is False
    assert config.skin.wallpaper_path is None


def test_enabled_skin_keeps_missing_wallpaper_for_runtime_fallback(
    config_root: Path,
) -> None:
    _write_skin(config_root, enabled=True, wallpaper_path="missing.png")

    config = load_config(config_root)

    assert config.skin.enabled is True
    assert config.skin.wallpaper_path == str(
        (config_root / "missing.png").resolve()
    )


def test_disabled_skin_does_not_require_wallpaper(config_root: Path) -> None:
    _write_skin(config_root, enabled=False, wallpaper_path=None)

    assert load_config(config_root).skin.enabled is False


@pytest.mark.parametrize("enabled", [1, "true", None])
def test_skin_enabled_must_be_boolean(
    config_root: Path,
    enabled: object,
) -> None:
    _write_skin(config_root, enabled=enabled, wallpaper_path="wallpaper.png")

    with pytest.raises(ConfigError, match="skin.enabled"):
        load_config(config_root)


def test_skin_wallpaper_path_must_be_string(config_root: Path) -> None:
    _write_skin(config_root, enabled=True, wallpaper_path=42)

    with pytest.raises(ConfigError, match="skin.wallpaper_path"):
        load_config(config_root)


def test_skin_section_must_be_object(config_root: Path) -> None:
    config_path = config_root / "config" / "launcher.example.json"
    data = json.loads(config_path.read_text(encoding="utf-8"))
    data["skin"] = []
    config_path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ConfigError, match="skin"):
        load_config(config_root)
