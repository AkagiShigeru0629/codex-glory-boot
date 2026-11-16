from collections.abc import Callable

from glory_boot.adapters.win32 import WindowInfo
from glory_boot.adapters.window_state import WindowStateStore
from glory_boot.domain.models import Rect
from glory_boot.domain.placement import is_rect_visible


EMERGENCY_VIEWPORT = Rect(0, 0, 1280, 720)


class WindowPlacementController:
    """选择初始视口，并在目标窗口稳定后校准一次启动器几何。"""

    def __init__(
        self,
        *,
        window_hwnd: Callable[[], int],
        state_store: WindowStateStore,
        monitors: Callable[[], tuple[Rect, ...]],
        default_rect: Callable[[], Rect],
        target_rect: Callable[[int], Rect],
        place_window: Callable[[int, Rect], None],
    ) -> None:
        self._window_hwnd = window_hwnd
        self._state_store = state_store
        self._monitors = monitors
        self._default_rect = default_rect
        self._target_rect = target_rect
        self._place_window = place_window
        self._viewport: Rect | None = None
        self._aligned_hwnd: int | None = None
        self._successful_rect: Rect | None = None

    def initial_viewport(self) -> Rect:
        if self._viewport is not None:
            return self._viewport

        try:
            monitors = self._monitors()
        except (OSError, RuntimeError, ValueError):
            monitors = ()
        saved = self._state_store.load()
        if saved is not None and is_rect_visible(saved, monitors):
            self._viewport = saved
        else:
            try:
                self._viewport = self._default_rect()
            except (OSError, RuntimeError, ValueError):
                self._viewport = EMERGENCY_VIEWPORT
        return self._viewport

    def align(self, window: WindowInfo) -> bool:
        if self._aligned_hwnd == window.hwnd and self._successful_rect is not None:
            return True

        try:
            target = self._target_rect(window.hwnd)
            if not is_rect_visible(target, self._monitors()):
                return False
            self._place_window(self._window_hwnd(), target)
        except (OSError, ValueError, RuntimeError):
            return False

        self._viewport = target
        self._aligned_hwnd = window.hwnd
        self._successful_rect = target
        return True

    def viewport(self) -> Rect:
        return self.initial_viewport()

    def remember_success(self) -> bool:
        if self._successful_rect is None:
            return False
        try:
            self._state_store.save(self._successful_rect)
        except (OSError, ValueError):
            return False
        return True
