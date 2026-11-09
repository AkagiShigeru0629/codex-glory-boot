from pathlib import Path

from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from glory_boot.domain.models import AppConfig, Rect, ScreenFrame, SkinConfig
from glory_boot.ui.application import (
    SkinLaunchOptions,
    prepare_skin_launch,
    present_initial_window,
)
from glory_boot.ui.boot_window import BootWindow


def _app_config(
    *,
    skin_enabled: bool,
    wallpaper_path: str | None,
) -> AppConfig:
    return AppConfig(
        app_id="OpenAI.Codex_2p2nqsd0c76g0!App",
        process_names=("ChatGPT.exe",),
        process_path_fragment="OpenAI.Codex_",
        video_path="startup.mp4",
        poster_path="poster.png",
        duration=8.0,
        hold_at=6.4,
        transition_start=6.7,
        transition_end=7.6,
        max_wait_seconds=60.0,
        volume=0.35,
        screen_frames=(
            ScreenFrame(0.0, Rect(0.36, 0.18, 0.28, 0.64), 0.75),
            ScreenFrame(7.6, Rect(0.0, 0.0, 1.0, 1.0), 1.0),
        ),
        skin=SkinConfig(
            enabled=skin_enabled,
            wallpaper_path=wallpaper_path,
        ),
    )


def test_cli_disable_skin_overrides_enabled_config() -> None:
    calls: list[None] = []
    options = prepare_skin_launch(
        _app_config(
            skin_enabled=True,
            wallpaper_path="wallpaper.png",
        ),
        skin_disabled_by_cli=True,
        benchmark=False,
        port_allocator=lambda: calls.append(None) or 50123,
    )

    assert options == SkinLaunchOptions(False, None, "")
    assert calls == []


def test_enabled_skin_allocates_one_loopback_port() -> None:
    options = prepare_skin_launch(
        _app_config(
            skin_enabled=True,
            wallpaper_path="wallpaper.png",
        ),
        skin_disabled_by_cli=False,
        benchmark=False,
        port_allocator=lambda: 50123,
    )

    assert options.skin_enabled is True
    assert options.skin_port == 50123
    assert options.launch_arguments == (
        "--remote-debugging-address=127.0.0.1 "
        "--remote-debugging-port=50123"
    )


def test_skin_without_wallpaper_does_not_open_debug_port() -> None:
    options = prepare_skin_launch(
        _app_config(skin_enabled=True, wallpaper_path=None),
        skin_disabled_by_cli=False,
        benchmark=False,
        port_allocator=lambda: 50123,
    )

    assert options == SkinLaunchOptions(False, None, "")


def test_benchmark_never_enables_skin() -> None:
    options = prepare_skin_launch(
        _app_config(
            skin_enabled=True,
            wallpaper_path="wallpaper.png",
        ),
        skin_disabled_by_cli=False,
        benchmark=True,
        port_allocator=lambda: 50123,
    )

    assert options == SkinLaunchOptions(False, None, "")


def test_poster_is_visible_before_player_is_created(
    qapp,
    tmp_path: Path,
) -> None:
    poster_path = tmp_path / "poster.png"
    Image.new("RGB", (16, 9), "#112233").save(poster_path)
    window = BootWindow()

    window.show_poster_first(str(poster_path))
    window.show()
    qapp.processEvents()

    assert window.player is None
    assert window.poster_is_visible is True
    window.close()


def test_missing_poster_opens_black_recovery_window(
    qapp,
    tmp_path: Path,
) -> None:
    window = BootWindow()

    window.show_poster_first(str(tmp_path / "missing.png"))
    window.show()
    qapp.processEvents()

    assert window.isVisible() is True
    assert window.background_name == "#000000"
    assert window.poster_is_visible is False
    window.close()


def test_escape_emits_skip_only_once(qapp) -> None:
    window = BootWindow()
    events: list[None] = []
    window.skip_requested.connect(lambda: events.append(None))
    window.show()
    qapp.processEvents()

    QTest.keyClick(window, Qt.Key.Key_Escape)
    QTest.keyClick(window, Qt.Key.Key_Escape)
    qapp.processEvents()

    assert len(events) == 1
    window.close()


def test_waiting_overlay_does_not_shrink_video(qapp) -> None:
    window = BootWindow()
    window.resize(960, 540)
    window.poster.hide()
    window.video.show()
    window.show()
    qapp.processEvents()

    window.show_waiting(True)
    qapp.processEvents()

    assert window.video.geometry() == window.rect()
    assert window.waiting.geometry() == window.rect()
    window.close()


def test_waiting_overlay_uses_top_right_safe_area(qapp) -> None:
    window = BootWindow()
    window.resize(960, 540)
    window.show_waiting(True)
    qapp.processEvents()

    alignment = window.waiting.alignment()
    margins = window.waiting.contentsMargins()

    assert alignment & Qt.AlignmentFlag.AlignRight
    assert alignment & Qt.AlignmentFlag.AlignTop
    assert margins.right() >= 32
    assert margins.top() >= 32
    assert "\n" in window.waiting.text()
    window.close()


def test_application_escape_shortcut_is_connected(qapp) -> None:
    window = BootWindow()
    events: list[None] = []
    window.skip_requested.connect(lambda: events.append(None))

    assert window.skip_shortcut.context() == Qt.ShortcutContext.ApplicationShortcut
    window.skip_shortcut.activated.emit()
    window.skip_shortcut.activated.emit()

    assert len(events) == 1
    window.close()


def test_window_fade_out_is_animated_and_invokes_completion(qapp) -> None:
    window = BootWindow()
    completed: list[None] = []
    window.show()
    qapp.processEvents()

    window.fade_out(40, lambda: completed.append(None))
    QTest.qWait(80)

    assert completed == [None]
    assert window.windowOpacity() <= 0.01
    window.close()


class PresentationWindow:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def winId(self) -> int:
        self.calls.append("winId")
        return 900

    def show(self) -> None:
        self.calls.append("show")


class Placement:
    def initial_viewport(self) -> Rect:
        return Rect(-1200, 40, 1400, 820)


class PresentationApplication:
    def processEvents(self) -> None:
        self.calls.append("processEvents")


class PresentationTimer:
    def mark(self, name: str) -> None:
        self.calls.append(f"mark:{name}")


def test_present_initial_window_places_before_showing(qapp) -> None:
    window = PresentationWindow()
    application = PresentationApplication()
    application.calls = window.calls
    timer = PresentationTimer()
    timer.calls = window.calls
    placed: list[tuple[int, Rect]] = []

    present_initial_window(
        window=window,
        placement=Placement(),
        place_window=lambda hwnd, rect: placed.append((hwnd, rect)),
        qt_app=application,
        timer=timer,
    )

    assert placed == [(900, Rect(-1200, 40, 1400, 820))]
    assert window.calls == [
        "winId",
        "show",
        "processEvents",
        "mark:window_visible",
    ]
