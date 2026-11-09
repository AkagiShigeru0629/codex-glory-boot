from pathlib import Path

import pytest

from glory_boot.adapters.window_state import WindowStateStore
from glory_boot.domain.models import Rect


def test_window_state_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "window-state.json"
    store = WindowStateStore(path)

    store.save(Rect(-1200, 80, 1400, 820))

    assert store.load() == Rect(-1200, 80, 1400, 820)
    assert list(path.parent.glob("*.tmp")) == []


def test_corrupt_or_invalid_state_is_ignored(tmp_path: Path) -> None:
    path = tmp_path / "window-state.json"
    path.write_text(
        '{"x": true, "y": 0, "width": 1400, "height": 820}',
        encoding="utf-8",
    )

    assert WindowStateStore(path).load() is None


def test_too_small_or_invalid_json_state_is_ignored(tmp_path: Path) -> None:
    path = tmp_path / "window-state.json"
    store = WindowStateStore(path)

    with pytest.raises(ValueError):
        store.save(Rect(0, 0, 449, 280))

    path.write_text(
        '{"x": 0, "y": 0, "width": 449, "height": 280}',
        encoding="utf-8",
    )
    assert store.load() is None

    path.write_text("{", encoding="utf-8")
    assert store.load() is None
