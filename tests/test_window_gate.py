from glory_boot.adapters.win32 import WindowInfo, WindowTransparencyState
from glory_boot.domain.models import Rect
from glory_boot.services.window_gate import WindowGateController


def _window(hwnd: int) -> WindowInfo:
    return WindowInfo(
        hwnd=hwnd,
        pid=9876,
        process_path=r"C:\Apps\OpenAI.Codex_x\ChatGPT.exe",
        client_rect=Rect(0, 0, 1280, 720),
        responsive=True,
    )


def test_window_gate_conceals_each_target_once_and_restores_all() -> None:
    concealed: list[int] = []
    restored: list[WindowTransparencyState] = []

    def conceal(hwnd: int) -> WindowTransparencyState:
        concealed.append(hwnd)
        return WindowTransparencyState(hwnd, 0, False, 0, 255, 0)

    controller = WindowGateController(
        conceal=conceal,
        restore=restored.append,
    )

    controller.conceal(_window(1001))
    controller.conceal(_window(1001))
    controller.conceal(_window(1002))
    controller.release_all()
    controller.release_all()

    assert concealed == [1001, 1002]
    assert [state.hwnd for state in restored] == [1002, 1001]
