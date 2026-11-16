import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
RENDERER_PATH = ROOT / "tools" / "append_crt_shutdown.py"


def _load_renderer() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "_append_crt_shutdown_under_test",
        RENDERER_PATH,
    )
    if spec is None or spec.loader is None:
        raise AssertionError(f"无法加载 CRT 渲染器: {RENDERER_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _bright_bounds(frame: Image.Image) -> tuple[int, int]:
    pixels = np.asarray(frame.convert("RGB"))
    mask = pixels.max(axis=2) > 16
    rows, columns = np.where(mask)
    if rows.size == 0:
        return 0, 0
    return (
        int(rows.max() - rows.min() + 1),
        int(columns.max() - columns.min() + 1),
    )


def test_crt_starts_with_the_source_frame() -> None:
    renderer = _load_renderer()
    source = Image.new("RGB", (120, 90), (165, 28, 36))

    assert np.array_equal(
        np.asarray(renderer.render_crt_frame(source, 0)),
        np.asarray(source),
    )


def test_crt_compresses_height_before_pinching_width() -> None:
    renderer = _load_renderer()
    source = Image.new("RGB", (120, 90), (245, 235, 225))
    frames = list(renderer.iter_crt_frames(source))

    source_height, source_width = _bright_bounds(frames[0])
    line_height, line_width = _bright_bounds(frames[18])
    dot_height, dot_width = _bright_bounds(frames[36])

    assert source_height == 90
    assert source_width == 120
    assert line_height <= 6
    assert line_width == source_width
    assert dot_height <= 6
    assert dot_width < line_width


def test_crt_finishes_on_black() -> None:
    renderer = _load_renderer()
    source = Image.new("RGB", (120, 90), (245, 235, 225))
    frames = list(renderer.iter_crt_frames(source))

    assert len(frames) == renderer.CRT_FRAME_COUNT
    assert int(np.asarray(frames[-1]).max()) <= 2


def test_crt_rejects_out_of_range_frames() -> None:
    renderer = _load_renderer()
    source = Image.new("RGB", (120, 90), (20, 30, 40))

    with pytest.raises(ValueError, match="frame_index"):
        renderer.render_crt_frame(source, renderer.CRT_FRAME_COUNT)


def test_current_crt_media_contract_has_expected_frame_counts() -> None:
    renderer = _load_renderer()

    assert renderer.SOURCE_END_SECONDS == pytest.approx(6.4)
    assert renderer.OUTPUT_DURATION_SECONDS == pytest.approx(7.7)
    assert renderer.TOTAL_FRAMES == 462
    assert renderer.CRT_FRAME_COUNT == 42
