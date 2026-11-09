import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest
from PIL import Image, ImageChops


ROOT = Path(__file__).resolve().parents[1]
RENDERER_PATH = ROOT / "tools" / "render_ten_zone_ending.py"


def _load_renderer() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "_render_ten_zone_ending_under_test",
        RENDERER_PATH,
    )
    if spec is None or spec.loader is None:
        raise AssertionError(f"无法加载渲染器: {RENDERER_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _configure_small_canvas(renderer: ModuleType) -> None:
    renderer.WIDTH = 480
    renderer.HEIGHT = 270
    renderer.TITLE_REGION = (120, 75, 360, 195)
    renderer.TITLE_SAFE_REGION = (136, 88, 344, 182)


def test_renderer_matches_production_media_contract() -> None:
    renderer = _load_renderer()

    assert renderer.WIDTH == 1920
    assert renderer.HEIGHT == 1080
    assert renderer.FPS == 60
    assert renderer.TOTAL_FRAMES == 480


def test_renderer_uses_balanced_opening_and_ending_durations() -> None:
    renderer = _load_renderer()

    assert renderer.OPENING_DURATION == pytest.approx(5.2)
    assert renderer.ENDING_DURATION == pytest.approx(2.8)
    assert renderer.ENDING_FRAME_COUNT == 168
    assert renderer.BRIDGE_FRAME_COUNT == 18


def test_ending_is_resampled_to_fill_the_extended_ending_duration() -> None:
    renderer = _load_renderer()
    _configure_small_canvas(renderer)
    frames = [
        Image.new(
            "RGB",
            (renderer.WIDTH, renderer.HEIGHT),
            (index * 30, 4, 8),
        )
        for index in range(3)
    ]

    resampled = list(renderer._iter_resampled_ending(frames))

    assert len(resampled) == renderer.ENDING_FRAME_COUNT
    assert np.asarray(resampled[0]).mean() == pytest.approx(
        np.asarray(frames[0]).mean()
    )
    assert np.asarray(resampled[-1]).mean() == pytest.approx(
        np.asarray(frames[-1]).mean()
    )
    assert {
        int(np.asarray(frame).mean()) for frame in resampled[-60:]
    } == {int(np.asarray(frames[-1]).mean())}


def test_bridge_frames_soften_the_brightness_jump() -> None:
    renderer = _load_renderer()
    _configure_small_canvas(renderer)
    base = Image.new("RGB", (renderer.WIDTH, renderer.HEIGHT), (180, 30, 30))
    ending = Image.new("RGB", (renderer.WIDTH, renderer.HEIGHT), (10, 5, 5))

    bridge = list(renderer._iter_bridge_frames(base, ending))
    sequence = [base, *bridge]
    means = [float(np.asarray(frame).mean()) for frame in sequence]

    assert len(bridge) == renderer.BRIDGE_FRAME_COUNT
    assert max(abs(after - before) for before, after in zip(means, means[1:])) <= 12.0
    assert np.asarray(bridge[-1]).mean() == pytest.approx(
        np.asarray(ending).mean()
    )


def test_replace_title_region_hides_old_glyphs_with_clean_panel() -> None:
    renderer = _load_renderer()
    _configure_small_canvas(renderer)
    old_frame = Image.new("RGB", (renderer.WIDTH, renderer.HEIGHT), (200, 20, 30))
    clean_frame = Image.new("RGB", (renderer.WIDTH, renderer.HEIGHT), (7, 7, 9))

    result = renderer._replace_title_region(old_frame, clean_frame)
    pixels = np.asarray(result)
    left, top, right, bottom = renderer.TITLE_REGION
    center = pixels[top:bottom, left:right]
    edge = pixels[top - 40, :]

    assert center.max() < 30
    assert edge[:, 0].min() > 150


def test_custom_title_adds_red_glyphs_inside_center_panel() -> None:
    renderer = _load_renderer()
    _configure_small_canvas(renderer)
    source = Image.new("RGB", (renderer.WIDTH, renderer.HEIGHT), (6, 6, 8))

    result = renderer._draw_custom_title(source, reveal=1.0, glitch=0.0)
    left, top, right, bottom = renderer.TITLE_REGION
    center = np.asarray(result)[top:bottom, left:right]

    assert center[:, :, 0].max() > 180
    assert np.count_nonzero(center[:, :, 0] > 80) > 500


def test_custom_title_stays_inside_background_safe_region() -> None:
    renderer = _load_renderer()
    _configure_small_canvas(renderer)
    source = Image.new("RGB", (renderer.WIDTH, renderer.HEIGHT), (6, 6, 8))

    result = renderer._draw_custom_title(source, reveal=1.0, glitch=0.0)
    changed_bbox = ImageChops.difference(source, result).getbbox()

    assert changed_bbox is not None
    left, top, right, bottom = renderer.TITLE_SAFE_REGION
    assert left <= changed_bbox[0] < changed_bbox[2] <= right
    assert top <= changed_bbox[1] < changed_bbox[3] <= bottom


def test_custom_title_uses_sparse_light_pixels_instead_of_solid_fill() -> None:
    renderer = _load_renderer()
    _configure_small_canvas(renderer)
    source = Image.new("RGB", (renderer.WIDTH, renderer.HEIGHT), (6, 6, 8))

    result = renderer._draw_custom_title(source, reveal=1.0, glitch=0.0)
    left, top, right, bottom = renderer.TITLE_SAFE_REGION
    pixels = np.asarray(result)[top:bottom, left:right]
    light_pixels = np.all(pixels > 220, axis=2)

    assert 0.0 < light_pixels.mean() < 0.08


def test_prepare_ending_frame_preserves_existing_hud_elements() -> None:
    renderer = _load_renderer()
    _configure_small_canvas(renderer)
    frame = Image.new("RGB", (renderer.WIDTH, renderer.HEIGHT), (210, 20, 30))
    clean = Image.new("RGB", (renderer.WIDTH, renderer.HEIGHT), (6, 6, 8))

    result = renderer._prepare_ending_frame(
        frame,
        clean,
        reveal=1.0,
        glitch=0.0,
    )
    pixels = np.asarray(result)
    title_left, title_top, title_right, title_bottom = renderer.TITLE_SAFE_REGION
    label_left, label_top, label_right, label_bottom = (0, 232, 100, 266)
    button_left, button_top, button_right, button_bottom = (0, 110, 80, 180)
    source = np.asarray(frame)

    assert np.count_nonzero(
        pixels[title_top:title_bottom, title_left:title_right, 0] > 120
    ) > 500
    assert np.array_equal(
        pixels[label_top:label_bottom, label_left:label_right],
        source[label_top:label_bottom, label_left:label_right],
    )
    assert np.array_equal(
        pixels[button_top:button_bottom, button_left:button_right],
        source[button_top:button_bottom, button_left:button_right],
    )


def test_prepared_ending_frames_are_generated_lazily(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    renderer = _load_renderer()
    _configure_small_canvas(renderer)
    frames = [
        Image.new("RGB", (renderer.WIDTH, renderer.HEIGHT), (10, 2, 4))
        for _ in range(3)
    ]
    clean = Image.new("RGB", (renderer.WIDTH, renderer.HEIGHT), (6, 6, 8))
    calls: list[int] = []
    original = renderer._prepare_ending_frame

    def count_prepared(
        frame: Image.Image,
        clean_frame: Image.Image,
        *,
        reveal: float,
        glitch: float,
    ) -> Image.Image:
        calls.append(1)
        return original(
            frame,
            clean_frame,
            reveal=reveal,
            glitch=glitch,
        )

    monkeypatch.setattr(renderer, "_prepare_ending_frame", count_prepared)
    iterator = renderer._iter_prepared_ending_frames(
        frames,
        clean,
        ending_count=6,
    )

    assert calls == []
    next(iterator)
    assert len(calls) == 1
    list(iterator)
    assert len(calls) == 6


def test_prepared_ending_keeps_title_texture_static_after_reveal() -> None:
    renderer = _load_renderer()
    _configure_small_canvas(renderer)
    source = Image.new("RGB", (renderer.WIDTH, renderer.HEIGHT), (10, 2, 4))
    clean = Image.new("RGB", (renderer.WIDTH, renderer.HEIGHT), (6, 6, 8))
    frames = [source, source, source]

    prepared = list(
        renderer._iter_prepared_ending_frames(
            frames,
            clean,
            ending_count=30,
        )
    )
    settled = np.asarray(prepared[20])

    assert all(
        np.array_equal(np.asarray(frame), settled)
        for frame in prepared[21:]
    )


def test_opening_keeps_fixed_scale_during_initial_reveal() -> None:
    renderer = _load_renderer()

    assert renderer._opening_scale(0.0) == 1.0
    assert renderer._opening_scale(0.2) == 1.0
    assert renderer._opening_scale(0.7) == 1.0
    assert renderer._opening_scale(2.0) > 1.0


def test_opening_first_frame_is_visible_for_poster_handoff() -> None:
    renderer = _load_renderer()
    _configure_small_canvas(renderer)
    source = Image.new("RGB", (renderer.WIDTH, renderer.HEIGHT), (80, 80, 80))

    first_frame = np.asarray(renderer._render_opening_frame(source, 0.0))

    assert first_frame.mean() > 55.0


def test_opening_contains_multiple_distinct_light_events() -> None:
    renderer = _load_renderer()
    _configure_small_canvas(renderer)
    source = Image.new("RGB", (renderer.WIDTH, renderer.HEIGHT), (12, 5, 8))

    frames = [
        np.asarray(renderer._render_opening_frame(source, seconds), dtype=np.float32)
        for seconds in (0.9, 1.8, 2.55, 3.3, 4.1, 4.75)
    ]

    differences = [
        float(np.abs(frames[index] - frames[index + 1]).mean())
        for index in range(len(frames) - 1)
    ]

    assert sum(difference > 1.5 for difference in differences) >= 4


def test_opening_uses_only_one_gentle_forward_move_then_holds() -> None:
    renderer = _load_renderer()

    sample_times = (0.8, 1.2, 1.65, 2.0, 2.4, 3.0, 4.8)
    scales = [renderer._opening_scale(seconds) for seconds in sample_times]

    assert all(after >= before for before, after in zip(scales, scales[1:]))
    assert max(scales) - min(scales) <= 0.025
    assert renderer._opening_scale(2.4) == renderer._opening_scale(4.8)


def test_opening_camera_locks_after_the_single_forward_move() -> None:
    renderer = _load_renderer()
    _configure_small_canvas(renderer)
    y, x = np.indices((renderer.HEIGHT, renderer.WIDTH))
    source = Image.fromarray(
        np.stack(
            (
                (x * 3 + y) % 256,
                (x + y * 5) % 256,
                (x * 2 + y * 7) % 256,
            ),
            axis=2,
        ).astype(np.uint8),
        "RGB",
    )

    settled = renderer._opening_camera(source, 2.4)
    later = renderer._opening_camera(source, 4.8)

    assert np.array_equal(np.asarray(settled), np.asarray(later))


def test_opening_uses_seven_distinct_effect_stages() -> None:
    renderer = _load_renderer()
    sample_times = (0.30, 1.00, 1.80, 2.55, 3.30, 4.10, 4.75)

    stages = [renderer._opening_stage(seconds) for seconds in sample_times]

    assert stages == [
        "converge",
        "ring",
        "sweep",
        "glitch",
        "burst",
        "scan",
        "charge",
    ]
    assert len(set(stages)) == 7


def test_opening_light_event_never_becomes_complex_at_frame_boundaries() -> None:
    renderer = _load_renderer()

    for start, end, _, _ in renderer._OPENING_SWEEPS:
        for frame_index in range(round(start * renderer.FPS), round(end * renderer.FPS) + 1):
            strength = renderer._event_strength(frame_index / renderer.FPS, start, end)
            assert isinstance(strength, float)
            assert 0.0 <= strength <= 1.0


def test_final_frame_holds_ten_zone_instead_of_codex_black() -> None:
    renderer = _load_renderer()
    _configure_small_canvas(renderer)
    renderer.TOTAL_FRAMES = 6
    base_frames = [
        Image.new("RGB", (renderer.WIDTH, renderer.HEIGHT), (160, 15, 20))
        for _ in range(3)
    ]
    ending_frames = [
        Image.new("RGB", (renderer.WIDTH, renderer.HEIGHT), (35, 2, 5))
        for _ in range(3)
    ]

    result = renderer._assemble_frames(base_frames, ending_frames)

    assert len(result) == renderer.TOTAL_FRAMES
    assert result[-1] is not result[0]
    assert np.asarray(result[-1])[:, :, 0].max() > 180
