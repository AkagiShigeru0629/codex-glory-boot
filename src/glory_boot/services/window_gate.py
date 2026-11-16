from collections.abc import Callable

from glory_boot.adapters.win32 import (
    WindowInfo,
    WindowTransparencyState,
    conceal_window,
    restore_window,
)


class WindowGateController:
    """在启动器首帧前隐藏目标窗口，覆盖完成后恢复。"""

    def __init__(
        self,
        *,
        conceal: Callable[[int], WindowTransparencyState] = conceal_window,
        restore: Callable[[WindowTransparencyState], None] = restore_window,
    ) -> None:
        self._conceal = conceal
        self._restore = restore
        self._states: dict[int, WindowTransparencyState] = {}

    def conceal(self, window: WindowInfo) -> bool:
        if window.hwnd in self._states:
            return True
        try:
            state = self._conceal(window.hwnd)
        except (OSError, ValueError):
            return False
        self._states[window.hwnd] = state
        return True

    def release_all(self) -> bool:
        released = True
        for hwnd in reversed(tuple(self._states)):
            state = self._states.pop(hwnd)
            try:
                self._restore(state)
            except (OSError, ValueError):
                released = False
        return released
