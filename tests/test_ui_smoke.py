from pathlib import Path

import pytest
from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

import glory_boot.ui.application as application_module
from glory_boot.adapters.win32 import WindowInfo
from glory_boot.domain.models import AppConfig, Rect, ScreenFrame, SkinConfig
from glory_boot.domain.skin import SkinProfile
from glory_boot.services.codex_launcher import LaunchResult
from glory_boot.ui.application import (
    LauncherApplication,
    SkinLaunchOptions,
    build_process_backend,
    build_skin_controller,
    prepare_skin_launch,
    present_initial_window,
)
from glory_boot.ui.boot_window import BootWindow


SUPPORTED_VERSION = "26.924.22138.0"
SKIN_PROFILE = SkinProfile(
    SUPPORTED_VERSION,
    ("#root",),
    ("--color-surface",),
)


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


def _wallpaper(tmp_path: Path) -> Path:
    path = tmp_path / "wallpaper.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\n")
    return path


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


def test_enabled_skin_allocates_one_loopback_port(
    tmp_path: Path,
) -> None:
    options = prepare_skin_launch(
        _app_config(
            skin_enabled=True,
            wallpaper_path=str(_wallpaper(tmp_path)),
        ),
        skin_disabled_by_cli=False,
        benchmark=False,
        codex_version=SUPPORTED_VERSION,
        skin_profiles=(SKIN_PROFILE,),
        port_allocator=lambda: 50123,
    )

    assert options.skin_enabled is True
    assert options.skin_port == 50123
    assert options.launch_arguments == (
        "--remote-debugging-address=127.0.0.1 "
        "--remote-debugging-port=50123"
    )


def test_enabled_skin_requires_existing_wallpaper(
    tmp_path: Path,
) -> None:
    calls: list[None] = []
    options = prepare_skin_launch(
        _app_config(
            skin_enabled=True,
            wallpaper_path=str(tmp_path / "missing.png"),
        ),
        skin_disabled_by_cli=False,
        benchmark=False,
        codex_version=SUPPORTED_VERSION,
        skin_profiles=(SKIN_PROFILE,),
        port_allocator=lambda: calls.append(None) or 50123,
    )

    assert options == SkinLaunchOptions(False, None, "")
    assert calls == []


@pytest.mark.parametrize("codex_version", [None, "99.0.0.0"])
def test_enabled_skin_requires_supported_codex_version(
    tmp_path: Path,
    codex_version: str | None,
) -> None:
    calls: list[None] = []
    options = prepare_skin_launch(
        _app_config(
            skin_enabled=True,
            wallpaper_path=str(_wallpaper(tmp_path)),
        ),
        skin_disabled_by_cli=False,
        benchmark=False,
        codex_version=codex_version,
        skin_profiles=(SKIN_PROFILE,),
        port_allocator=lambda: calls.append(None) or 50123,
    )

    assert options == SkinLaunchOptions(False, None, "")
    assert calls == []


def test_skin_without_wallpaper_does_not_open_debug_port() -> None:
    options = prepare_skin_launch(
        _app_config(skin_enabled=True, wallpaper_path=None),
        skin_disabled_by_cli=False,
        benchmark=False,
        port_allocator=lambda: 50123,
    )

    assert options == SkinLaunchOptions(False, None, "")


class RecordingProcessBackend:
    pass


def test_process_backend_uses_activation_only_for_enabled_skin() -> None:
    created: list[str] = []

    backend = build_process_backend(
        benchmark=False,
        skin_enabled=True,
        activation_factory=lambda: created.append("activation")
        or RecordingProcessBackend(),
    )

    assert isinstance(backend, RecordingProcessBackend)
    assert created == ["activation"]
    assert build_process_backend(
        benchmark=False,
        skin_enabled=False,
    ) is None
    assert isinstance(
        build_process_backend(
            benchmark=True,
            skin_enabled=True,
            noop_factory=lambda: RecordingProcessBackend(),
        ),
        RecordingProcessBackend,
    )


class FakeSkinController:
    def __init__(self) -> None:
        self.starts: list[int | None] = []
        self.close_calls = 0
        self.closed = False

    def start(self, launched_pid: int | None) -> None:
        self.starts.append(launched_pid)

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        self.close_calls += 1


def test_build_skin_controller_uses_launch_port_and_profile(
    tmp_path: Path,
) -> None:
    calls: list[dict[str, object]] = []
    fake = FakeSkinController()

    controller = build_skin_controller(
        _app_config(
            skin_enabled=True,
            wallpaper_path=str(_wallpaper(tmp_path)),
        ),
        root=tmp_path,
        options=SkinLaunchOptions(True, 50123, "args"),
        profiles=(SKIN_PROFILE,),
        stage_marker=lambda _name: None,
        parent=None,
        factory=lambda **kwargs: calls.append(kwargs) or fake,
    )

    assert controller is fake
    assert calls[0]["port"] == 50123
    assert calls[0]["profiles"] == (SKIN_PROFILE,)
    assert build_skin_controller(
        _app_config(skin_enabled=False, wallpaper_path=None),
        root=tmp_path,
        options=SkinLaunchOptions(False, None, ""),
        profiles=(),
        stage_marker=lambda _name: None,
        parent=None,
        factory=lambda **kwargs: pytest.fail("不应创建控制器"),
    ) is None


def test_application_starts_and_closes_skin_from_launch_result() -> None:
    application = object.__new__(LauncherApplication)
    fake = FakeSkinController()
    application.skin = fake  # type: ignore[assignment]

    application._start_skin(
        LaunchResult(launch_requested=True, launched_pid=9876)
    )
    application._start_skin(
        LaunchResult(launch_requested=False, existing_window_hwnd=4321)
    )
    application._close_skin()
    application._close_skin()

    assert fake.starts == [9876, None]
    assert fake.close_calls == 1


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

    def close(self) -> None:
        self.calls.append("close")


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


def test_existing_codex_is_focused_before_launcher_is_shown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing = WindowInfo(
        hwnd=4321,
        pid=9876,
        process_path=r"C:\Apps\OpenAI.Codex_x\ChatGPT.exe",
        client_rect=Rect(0, 0, 1280, 688),
        responsive=True,
    )
    focused: list[int] = []
    application = object.__new__(LauncherApplication)
    application._config = _app_config(
        skin_enabled=False,
        wallpaper_path=None,
    )
    application.window = PresentationWindow()
    application.skin = None
    application._runtime_store = None
    application._timer = PresentationTimer()
    application._timer.calls = application.window.calls
    monkeypatch.setattr(
        application_module,
        "find_codex_window",
        lambda _config: existing,
    )
    monkeypatch.setattr(
        application_module,
        "focus_window",
        focused.append,
    )

    assert application._focus_existing_codex() is True
    assert focused == [4321]
    assert "show" not in application.window.calls
