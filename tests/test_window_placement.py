from collections.abc import Callable
from pathlib import Path

from glory_boot.adapters.win32 import WindowInfo
from glory_boot.adapters.window_state import WindowStateStore
from glory_boot.domain.models import Rect
from glory_boot.services.window_placement import WindowPlacementController


MONITORS = (
    Rect(-1920, 0, 1920, 1080),
    Rect(0, 0, 2560, 1440),
)


def _codex_window(hwnd: int = 4321) -> WindowInfo:
    return WindowInfo(
        hwnd=hwnd,
        pid=99,
        process_path=r"C:\Apps\OpenAI.Codex_x\Codex.exe",
        client_rect=Rect(0, 0, 1400, 820),
        responsive=True,
    )


class PlacementHarness:
    def __init__(
        self,
        tmp_path: Path,
        *,
        saved: Rect | None = None,
        client_rect: Callable[[int], Rect] | None = None,
        client_rect_error: Exception | None = None,
        default_rect_error: Exception | None = None,
    ) -> None:
        self.store = WindowStateStore(tmp_path / "window-state.json")
        if saved is not None:
            self.store.save(saved)
        self.placed: list[tuple[int, Rect]] = []
        self.client_rect_calls: list[int] = []
        self.client_rect_error = client_rect_error
        self.default_rect_error = default_rect_error
        self.controller = WindowPlacementController(
            window_hwnd=lambda: 900,
            state_store=self.store,
            monitors=lambda: MONITORS,
            default_rect=lambda: self._default_rect(),
            client_rect=client_rect or self._client_rect,
            place_window=self._place_window,
        )

    def _client_rect(self, hwnd: int) -> Rect:
        self.client_rect_calls.append(hwnd)
        if self.client_rect_error is not None:
            raise self.client_rect_error
        return Rect(-1920, 40, 1400, 820)

    def _default_rect(self) -> Rect:
        if self.default_rect_error is not None:
            raise self.default_rect_error
        return Rect(100, 100, 1280, 720)

    def _place_window(self, hwnd: int, rect: Rect) -> None:
        self.placed.append((hwnd, rect))


def test_initial_viewport_uses_valid_saved_rect(tmp_path: Path) -> None:
    harness = PlacementHarness(tmp_path, saved=Rect(-1200, 40, 1400, 820))

    assert harness.controller.initial_viewport() == Rect(
        -1200,
        40,
        1400,
        820,
    )


def test_initial_viewport_rejects_offscreen_saved_rect(tmp_path: Path) -> None:
    harness = PlacementHarness(tmp_path, saved=Rect(5000, 5000, 800, 600))

    assert harness.controller.initial_viewport() == Rect(100, 100, 1280, 720)


def test_initial_viewport_uses_emergency_rect_when_defaults_fail(
    tmp_path: Path,
) -> None:
    harness = PlacementHarness(
        tmp_path,
        default_rect_error=OSError("display unavailable"),
    )

    assert harness.controller.initial_viewport() == Rect(0, 0, 1280, 720)


def test_align_moves_window_once_and_updates_viewport(tmp_path: Path) -> None:
    harness = PlacementHarness(tmp_path)
    harness.controller.initial_viewport()

    assert harness.controller.align(_codex_window()) is True
    assert harness.controller.align(_codex_window()) is True

    assert harness.placed == [(900, Rect(-1920, 40, 1400, 820))]
    assert harness.controller.viewport() == Rect(-1920, 40, 1400, 820)


def test_align_failure_keeps_previous_viewport(tmp_path: Path) -> None:
    harness = PlacementHarness(
        tmp_path,
        client_rect_error=OSError("denied"),
    )
    initial = harness.controller.initial_viewport()

    assert harness.controller.align(_codex_window()) is False
    assert harness.controller.viewport() == initial


def test_remember_success_writes_only_after_alignment(tmp_path: Path) -> None:
    harness = PlacementHarness(tmp_path)
    harness.controller.initial_viewport()

    assert harness.controller.remember_success() is False

    harness.controller.align(_codex_window())
    assert harness.controller.remember_success() is True
    assert harness.store.load() == Rect(-1920, 40, 1400, 820)
