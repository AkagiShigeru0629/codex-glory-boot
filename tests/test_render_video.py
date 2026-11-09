import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest


ROOT = Path(__file__).resolve().parents[1]
RENDER_SCRIPT = ROOT / "tools" / "render_video.py"


def _load_renderer(path: Path, module_name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"无法加载渲染器: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def test_renderer_renders_procedural_emblem_without_private_assets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    renderer = _load_renderer(RENDER_SCRIPT, "_procedural_emblem_render_video")
    frame = renderer.render_frame(4.8)
    center = np.asarray(frame)[180:740, 560:1360]

    assert frame.mode == "RGB"
    assert frame.size == (1920, 1080)
    gold_pixels = (
        (center[:, :, 0] > 150)
        & (center[:, :, 1] > 110)
        & (center[:, :, 2] > 40)
    )
    assert gold_pixels.sum() > 10_000


def test_background_uses_dark_ink_green_instead_of_ice_blue() -> None:
    renderer = _load_renderer(RENDER_SCRIPT, "_palette_render_video")
    frame = np.asarray(renderer.render_frame(0.0).crop((0, 0, 180, 180)))
    channel_means = frame.reshape(-1, 3).mean(axis=0)

    assert channel_means[1] > channel_means[2], (
        f"背景仍偏蓝: RGB 均值={channel_means.round(2).tolist()}"
    )
    assert channel_means.mean() < 45, (
        f"背景不够深: RGB 均值={channel_means.round(2).tolist()}"
    )
