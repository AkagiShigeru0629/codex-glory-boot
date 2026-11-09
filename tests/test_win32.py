from dataclasses import replace

import pytest

import glory_boot.adapters.win32 as win32
from glory_boot.adapters.dwm import DwmController
from glory_boot.adapters.win32 import (
    RawWindowRecord,
    WindowInfo,
    Win32Error,
    client_screen_rect,
    cursor_work_area,
    monitor_work_areas,
    process_path_for_pid,
    select_codex_window,
    set_window_rect,
)
from glory_boot.domain.models import AppConfig, Rect, ScreenFrame


@pytest.fixture
def config() -> AppConfig:
    return AppConfig(
        app_id="OpenAI.Codex_2p2nqsd0c76g0!App",
        process_names=("Codex.exe",),
        process_path_fragment="OpenAI.Codex_",
        video_path="startup.mp4",
        poster_path="poster.png",
        duration=8.0,
        hold_at=6.3,
        transition_start=6.8,
        transition_end=7.6,
        max_wait_seconds=60.0,
        volume=0.35,
        screen_frames=(
            ScreenFrame(0.0, Rect(0.3, 0.2, 0.4, 0.6), 0.75),
            ScreenFrame(7.6, Rect(0.0, 0.0, 1.0, 1.0), 1.0),
        ),
    )


def _valid_record() -> RawWindowRecord:
    return RawWindowRecord(
        hwnd=1001,
        pid=4242,
        class_name="Chrome_WidgetWin_1",
        visible=True,
        cloaked=False,
        tool_window=False,
        process_path=(
            r"C:\Program Files\WindowsApps"
            r"\OpenAI.Codex_2p2nqsd0c76g0\Codex.exe"
        ),
        client_rect=Rect(0, 0, 1280, 800),
        responsive=True,
    )


def test_select_codex_window_accepts_unique_stable_record(
    config: AppConfig,
) -> None:
    result = select_codex_window(config, [_valid_record()])

    assert result == WindowInfo(
        hwnd=1001,
        pid=4242,
        process_path=(
            r"C:\Program Files\WindowsApps"
            r"\OpenAI.Codex_2p2nqsd0c76g0\Codex.exe"
        ),
        client_rect=Rect(0, 0, 1280, 800),
        responsive=True,
    )


@pytest.mark.parametrize(
    "change",
    [
        {"visible": False},
        {"cloaked": True},
        {"tool_window": True},
        {"class_name": "Chrome_WidgetWin_0"},
        {"process_path": r"C:\Other\Codex.exe"},
        {"client_rect": Rect(0, 0, 449, 800)},
        {"client_rect": Rect(0, 0, 1280, 279)},
        {"responsive": False},
    ],
)
def test_select_codex_window_rejects_ineligible_record(
    config: AppConfig,
    change: dict[str, object],
) -> None:
    invalid = replace(_valid_record(), **change)

    assert select_codex_window(config, [invalid]) is None


def test_select_codex_window_rejects_wrong_process_name(
    config: AppConfig,
) -> None:
    invalid = replace(
        _valid_record(),
        process_path=r"C:\Apps\NotCodex.exe",
    )

    assert select_codex_window(config, [invalid]) is None


def test_select_codex_window_rejects_multiple_matches(
    config: AppConfig,
) -> None:
    duplicate = replace(_valid_record(), hwnd=1002, pid=4243)

    assert select_codex_window(
        config,
        [_valid_record(), duplicate],
    ) is None


class FakeUser32:
    def __init__(self) -> None:
        self.position: tuple[int, int, int, int] | None = None

    def GetClientRect(self, hwnd: int, pointer: object) -> int:
        assert hwnd == 1001
        rect = pointer._obj  # type: ignore[attr-defined]
        rect.left = 0
        rect.top = 0
        rect.right = 800
        rect.bottom = 600
        return 1

    def ClientToScreen(self, hwnd: int, pointer: object) -> int:
        assert hwnd == 1001
        point = pointer._obj  # type: ignore[attr-defined]
        point.x += 150
        point.y += 80
        return 1

    def SetWindowPos(
        self,
        hwnd: int,
        insert_after: int,
        x: int,
        y: int,
        width: int,
        height: int,
        flags: int,
    ) -> int:
        self.position = (x, y, width, height)
        return 1

    def GetCursorPos(self, pointer: object) -> int:
        point = pointer._obj  # type: ignore[attr-defined]
        point.x = -100
        point.y = 50
        return 1

    def MonitorFromPoint(self, point: object, flags: int) -> int:
        assert flags == win32.MONITOR_DEFAULTTONEAREST
        return 2

    def GetMonitorInfoW(self, monitor: int, pointer: object) -> int:
        info = pointer._obj  # type: ignore[attr-defined]
        if monitor == 2:
            info.rcWork.left = -1920
            info.rcWork.top = 0
            info.rcWork.right = 0
            info.rcWork.bottom = 1040
        else:
            info.rcWork.left = 0
            info.rcWork.top = 0
            info.rcWork.right = 2560
            info.rcWork.bottom = 1400
        return 1

    def EnumDisplayMonitors(
        self,
        hdc: int,
        clip: object,
        callback: object,
        data: int,
    ) -> int:
        callback(2, 0, None, 0)
        callback(1, 0, None, 0)
        return 1


def test_client_screen_rect_converts_client_origin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(win32, "_user32", FakeUser32())

    assert client_screen_rect(1001) == Rect(150, 80, 800, 600)


def test_set_window_rect_uses_physical_rectangle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user32 = FakeUser32()
    monkeypatch.setattr(win32, "_user32", user32)

    set_window_rect(1001, Rect(150.4, 80.6, 800.2, 600.5))

    assert user32.position == (150, 81, 800, 600)


def test_monitor_geometry_uses_win32_work_areas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(win32, "_user32", FakeUser32())

    assert cursor_work_area() == Rect(-1920, 0, 1920, 1040)
    assert monitor_work_areas() == (
        Rect(-1920, 0, 1920, 1040),
        Rect(0, 0, 2560, 1400),
    )


def test_window_geometry_rejects_invalid_inputs() -> None:
    with pytest.raises(Win32Error):
        client_screen_rect(0)
    with pytest.raises(ValueError):
        set_window_rect(1001, Rect(0, 0, 0, 100))
    assert process_path_for_pid(0) is None


class FakeDwmBackend:
    def __init__(self) -> None:
        self.register_calls: list[int] = []
        self.update_calls: list[tuple[int, Rect, int, bool]] = []
        self.unregister_calls: list[int] = []

    def register_thumbnail(self, destination_hwnd: int, source_hwnd: int) -> int:
        assert destination_hwnd == 900
        self.register_calls.append(source_hwnd)
        return 77

    def update_thumbnail(
        self,
        thumbnail: int,
        destination: Rect,
        opacity: int,
        visible: bool,
    ) -> None:
        self.update_calls.append((thumbnail, destination, opacity, visible))

    def unregister_thumbnail(self, thumbnail: int) -> None:
        self.unregister_calls.append(thumbnail)


def test_dwm_controller_registers_once_and_converts_opacity() -> None:
    backend = FakeDwmBackend()
    controller = DwmController(destination_hwnd=900, backend=backend)

    controller.register(1001)
    controller.register(1002)
    controller.update(
        destination=Rect(10, 20, 300, 200),
        opacity=0.5,
        visible=True,
    )

    assert backend.register_calls == [1001]
    assert backend.update_calls == [
        (77, Rect(10, 20, 300, 200), 128, True),
    ]


def test_dwm_controller_close_is_idempotent_and_releases_once() -> None:
    backend = FakeDwmBackend()
    controller = DwmController(destination_hwnd=900, backend=backend)
    controller.register(1001)

    controller.close()
    controller.close()

    assert backend.unregister_calls == [77]
