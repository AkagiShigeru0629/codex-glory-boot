import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
RENDERER_PATH = ROOT / "tools" / "render_lookdev_v2.py"


def _load_renderer() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "_render_lookdev_v2_under_test",
        RENDERER_PATH,
    )
    if spec is None or spec.loader is None:
        raise AssertionError(f"无法加载渲染器: {RENDERER_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_ten_zone_frame_index_uses_complete_late_sequence() -> None:
    renderer = _load_renderer()

    assert renderer._ten_zone_frame_index(6.92, 21) == 0
    assert renderer._ten_zone_frame_index(7.33, 21) == 10
    assert renderer._ten_zone_frame_index(7.75, 21) == 20
    assert renderer._ten_zone_frame_index(6.91, 21) is None
    assert renderer._ten_zone_frame_index(7.76, 21) is None
    assert renderer._ten_zone_frame_index(7.33, 0) is None


def test_ten_zone_overlay_reveals_supplied_frame_during_black_handoff() -> None:
    renderer = _load_renderer()
    source = Image.new("RGB", (renderer.WIDTH, renderer.HEIGHT), (6, 6, 8))
    marker = Image.new("RGB", (renderer.WIDTH, renderer.HEIGHT), (220, 24, 31))

    overlaid = renderer._apply_ten_zone(source, 7.34, (marker,))

    assert np.asarray(overlaid)[:, :, 0].mean() > 200


def test_no_ten_zone_frames_keep_original_handoff_image() -> None:
    renderer = _load_renderer()
    source = Image.new("RGB", (renderer.WIDTH, renderer.HEIGHT), (6, 6, 8))

    assert renderer._apply_ten_zone(source, 7.34, ()) is source
