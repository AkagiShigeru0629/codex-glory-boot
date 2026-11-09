import pytest

from glory_boot.domain.models import Rect
from glory_boot.domain.placement import default_launcher_rect, is_rect_visible


def test_default_launcher_rect_fits_sixteen_by_nine_inside_coverage() -> None:
    result = default_launcher_rect(Rect(0, 0, 1920, 1040))

    assert result.x == pytest.approx(312.8888888889)
    assert result.y == pytest.approx(156)
    assert result.width == pytest.approx(1294.2222222222)
    assert result.height == pytest.approx(728)


def test_default_launcher_rect_supports_negative_work_area() -> None:
    result = default_launcher_rect(Rect(-2560, 0, 2560, 1440))

    assert result.x == pytest.approx(-2176)
    assert result.y == pytest.approx(216)
    assert result.width == pytest.approx(1792)
    assert result.height == pytest.approx(1008)


@pytest.mark.parametrize("coverage", [0.0, 1.0, -0.1, 1.1])
def test_default_launcher_rect_rejects_invalid_coverage(
    coverage: float,
) -> None:
    with pytest.raises(ValueError):
        default_launcher_rect(
            Rect(0, 0, 1920, 1040),
            coverage=coverage,
        )


def test_is_rect_visible_requires_minimum_intersection() -> None:
    monitors = (Rect(-1920, 0, 1920, 1080), Rect(0, 0, 2560, 1440))

    assert is_rect_visible(Rect(-100, 100, 800, 600), monitors)
    assert not is_rect_visible(Rect(-1900, 100, 50, 50), monitors)


def test_is_rect_visible_rejects_invalid_input() -> None:
    assert not is_rect_visible(Rect(0, 0, 0, 100), (Rect(0, 0, 1, 1),))
    assert not is_rect_visible(Rect(0, 0, 100, 100), ())
