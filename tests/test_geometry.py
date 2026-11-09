from dataclasses import FrozenInstanceError

import pytest

from glory_boot.domain.geometry import (
    centered,
    destination_at,
    physical_pixels,
    window_for_client,
)
from glory_boot.domain.models import Rect, ScreenFrame


def test_rect_is_immutable() -> None:
    rect = Rect(0, 0, 100, 100)

    with pytest.raises(FrozenInstanceError):
        rect.x = 10  # type: ignore[misc]


@pytest.mark.parametrize(
    ("viewport", "expected"),
    [
        (Rect(0, 0, 1920, 1080), Rect(0, 0, 1920, 1080)),
        (Rect(0, 0, 2560, 1440), Rect(0, 0, 2560, 1440)),
        (Rect(0, 0, 3840, 2160), Rect(0, 0, 3840, 2160)),
        (Rect(0, 0, 1600, 1200), Rect(0, 150, 1600, 900)),
    ],
)
def test_centered_fits_sixteen_by_nine_content(
    viewport: Rect,
    expected: Rect,
) -> None:
    assert centered(viewport, 1920, 1080) == expected


def test_centered_supports_negative_monitor_coordinates() -> None:
    assert centered(Rect(-2560, 0, 2560, 1440), 1920, 1080) == Rect(
        -2560,
        0,
        2560,
        1440,
    )


def test_centered_supports_portrait_monitor() -> None:
    assert centered(Rect(0, -1080, 1080, 1920), 1920, 1080) == Rect(
        0,
        -423.75,
        1080,
        607.5,
    )


def test_window_for_client_adds_asymmetric_borders_and_title_bar() -> None:
    assert window_for_client(
        Rect(100, 200, 800, 600),
        border_x=8,
        border_y=12,
        title_bar_height=32,
    ) == Rect(92, 168, 816, 644)


def test_physical_pixels_converts_logical_size_at_dpi() -> None:
    assert physical_pixels(100, 96) == 100
    assert physical_pixels(100, 120) == 125
    assert physical_pixels(101, 144) == 152


def test_destination_at_interpolates_and_fills_viewport_at_end() -> None:
    frames = (
        ScreenFrame(1.0, Rect(0.25, 0.25, 0.5, 0.5), 0.5),
        ScreenFrame(3.0, Rect(0.0, 0.0, 1.0, 1.0), 1.0),
    )
    viewport = Rect(-1920, 0, 1920, 1080)

    assert destination_at(frames, 2.0, viewport) == Rect(
        -1680,
        135,
        1440,
        810,
    )
    assert destination_at(frames, 3.0, viewport) == viewport


def test_destination_at_clamps_to_first_and_last_frame() -> None:
    frames = (
        ScreenFrame(1.0, Rect(0.25, 0.25, 0.5, 0.5), 0.5),
        ScreenFrame(3.0, Rect(0.5, 0.5, 0.5, 0.5), 1.0),
    )
    viewport = Rect(0, 0, 1000, 500)

    assert destination_at(frames, 0.0, viewport) == Rect(
        250,
        125,
        500,
        250,
    )
    assert destination_at(frames, 10.0, viewport) == Rect(
        500,
        250,
        500,
        250,
    )
