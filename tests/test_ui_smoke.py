from pathlib import Path

import pytest
from PIL import Image
from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtTest import QTest

import glory_boot.ui.application as application_module
from glory_boot.adapters.win32 import WindowInfo
from glory_boot.domain.models import AppConfig, Rect, ScreenFrame, SkinConfig
from glory_boot.domain.skin import SkinProfile
from glory_boot.services.codex_launcher import FallbackProcessBackend, LaunchResult
from glory_boot.services.skin import SkinState
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
        skin_profiles=(SKIN_PROFILE,),
        port_allocator=lambda: calls.append(None) or 50123,
    )

    assert options == SkinLaunchOptions(False, None, "")
    assert calls == []


def test_enabled_skin_opens_debug_port_until_activated_version_is_known(
    tmp_path: Path,
) -> None:
    calls: list[None] = []
    options = prepare_skin_launch(
        _app_config(
            skin_enabled=True,
            wallpaper_path=str(_wallpaper(tmp_path)),
        ),
        skin_disabled_by_cli=False,
        benchmark=False,
        skin_profiles=(SKIN_PROFILE,),
        port_allocator=lambda: calls.append(None) or 50123,
    )

    assert options.skin_enabled is True
    assert options.skin_port == 50123
    assert options.launch_arguments
    assert calls == [None]


def test_enabled_skin_requires_registered_profiles(tmp_path: Path) -> None:
    options = prepare_skin_launch(
        _app_config(
            skin_enabled=True,
            wallpaper_path=str(_wallpaper(tmp_path)),
        ),
        skin_disabled_by_cli=False,
        benchmark=False,
        skin_profiles=(),
        port_allocator=lambda: 50123,
    )

    assert options == SkinLaunchOptions(False, None, "")


def test_skin_without_wallpaper_does_not_open_debug_port() -> None:
    options = prepare_skin_launch(
        _app_config(skin_enabled=True, wallpaper_path=None),
        skin_disabled_by_cli=False,
        benchmark=False,
        port_allocator=lambda: 50123,
    )

    assert options == SkinLaunchOptions(False, None, "")


class RecordingProcessBackend:
    def __init__(self, *, process_id: int | None = None) -> None:
        self.process_id = process_id
        self.calls: list[tuple[str, str]] = []

    def launch(self, app_id: str, arguments: str = "") -> int | None:
        self.calls.append((app_id, arguments))
        return self.process_id


def test_process_backend_wraps_activation_with_shell_fallback() -> None:
    created: list[str] = []
    activation = RecordingProcessBackend(process_id=9876)
    shell = RecordingProcessBackend()

    backend = build_process_backend(
        benchmark=False,
        skin_enabled=True,
        activation_factory=lambda: created.append("activation")
        or activation,
        fallback_factory=lambda: shell,
    )

    assert isinstance(backend, FallbackProcessBackend)
    assert created == ["activation"]
    assert backend.launch(
        "OpenAI.Codex_2p2nqsd0c76g0!App",
        "--remote-debugging-port=50123",
    ) == 9876
    assert activation.calls == [
        (
            "OpenAI.Codex_2p2nqsd0c76g0!App",
            "--remote-debugging-port=50123",
        )
    ]
    assert shell.calls == []
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


class BackgroundSkin:
    def __init__(self) -> None:
        self.state = SkinState.WAITING
        self.close_calls = 0

    def close(self) -> None:
        self.close_calls += 1


class QuitApplication:
    def __init__(self) -> None:
        self.quit_calls = 0

    def quit(self) -> None:
        self.quit_calls += 1


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
    assert calls[0]["timeout_ms"] == 60_000
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


def test_handoff_keeps_skin_alive_until_background_install_finishes() -> None:
    application = object.__new__(LauncherApplication)
    application.skin = BackgroundSkin()  # type: ignore[assignment]
    application._skin_started = True
    application._handoff_completed = True
    application._skip_requested = False
    application._qt_app = QuitApplication()  # type: ignore[assignment]

    application._request_exit()

    assert application.skin.close_calls == 0
    assert application._qt_app.quit_calls == 0

    application.skin.state = SkinState.INSTALLED
    application._on_skin_state_changed(SkinState.INSTALLED.value)

    assert application.skin.close_calls == 1
    assert application._qt_app.quit_calls == 1


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

    def setWindowOpacity(self, opacity: float) -> None:
        self.calls.append(f"opacity:{opacity:.1f}")

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


class RevealWindow(PresentationWindow):
    def attach_media(self, _media: object) -> None:
        self.calls.append("attach_media")


class RevealSession:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    def begin_media(self) -> None:
        self.calls.append("begin_media")


class PassThroughWindowGate:
    def release_all(self) -> bool:
        return True


class ColdStartWindow:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    def show_poster_first(self, _path: str) -> None:
        self.calls.append("prepare_poster")


class ColdStartSession:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    def start(self, *, defer_media: bool = False) -> None:
        self.calls.append(f"session_start:{defer_media}")


class ColdStartApplication:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls
        self._quit_on_last_window = True

    def exec(self) -> int:
        self.calls.append("event_loop")
        return 0

    def quitOnLastWindowClosed(self) -> bool:
        return self._quit_on_last_window

    def setQuitOnLastWindowClosed(self, enabled: bool) -> None:
        self._quit_on_last_window = enabled
        self.calls.append(f"quit_on_last_window:{enabled}")


class AvailableGuard:
    already_running = False

    def __enter__(self) -> "AvailableGuard":
        return self

    def __exit__(self, *_args: object) -> None:
        return None


class CapturingSession(QObject):
    handoff_completed = Signal()
    handoff_started = Signal()
    launch_result_ready = Signal(object)

    def __init__(self, *_args: object, **kwargs: object) -> None:
        super().__init__()
        self.kwargs = kwargs


class AlignmentPlacement:
    def __init__(self) -> None:
        self.aligned_hwnds: list[int] = []

    def align(self, window: WindowInfo) -> bool:
        self.aligned_hwnds.append(window.hwnd)
        return True


def test_present_initial_window_places_rect_before_showing(qapp) -> None:
    window = PresentationWindow()
    application = PresentationApplication()
    application.calls = window.calls
    timer = PresentationTimer()
    timer.calls = window.calls

    present_initial_window(
        window=window,
        placement=Placement(),
        place_window=lambda hwnd, rect: window.calls.append(
            f"place:{hwnd}:{rect.x},{rect.y},{rect.width},{rect.height}"
        ),
        qt_app=application,
        timer=timer,
    )

    assert window.calls == [
        "winId",
        "place:900:-1200,40,1400,820",
        "opacity:0.0",
        "show",
        "place:900:-1200,40,1400,820",
        "processEvents",
        "opacity:1.0",
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


def test_reveal_locks_target_before_first_events_and_starting_media(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    window = RevealWindow()
    window.calls = calls
    application = object.__new__(LauncherApplication)
    application.window = window
    application._placement = Placement()
    application._qt_app = PresentationApplication()
    application._qt_app.calls = calls
    application._timer = PresentationTimer()
    application._timer.calls = calls
    application.media = object()
    application.session = RevealSession(calls)
    application._window_gate = PassThroughWindowGate()
    application._window_visible = False
    monkeypatch.setattr(
        application_module,
        "set_window_rect",
        lambda _hwnd, _rect: calls.append("place"),
    )

    application._reveal_window()

    assert calls.index("place") < calls.index("show")
    assert calls.index("opacity:0.0") < calls.index("show")
    assert calls.index("show") < calls.index("opacity:1.0")
    assert calls.index("processEvents") < calls.index("attach_media")
    assert calls.index("attach_media") < calls.index("begin_media")
    assert application._window_visible is True


def test_cold_start_waits_for_codex_instead_of_using_timed_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    application = object.__new__(LauncherApplication)
    application._config = _app_config(
        skin_enabled=False,
        wallpaper_path=None,
    )
    application._focus_existing_codex = lambda: False
    application.window = ColdStartWindow(calls)
    application.session = ColdStartSession(calls)
    application._qt_app = ColdStartApplication(calls)
    application._close_skin = lambda: calls.append("close_skin")
    application._window_gate = PassThroughWindowGate()
    monkeypatch.setattr(
        application_module,
        "SingleInstanceGuard",
        AvailableGuard,
    )

    assert application.run(benchmark=False) == 0
    assert calls == [
        "quit_on_last_window:False",
        "prepare_poster",
        "session_start:True",
        "event_loop",
        "close_skin",
        "quit_on_last_window:True",
    ]


def test_handoff_before_codex_reveals_poster_without_starting_media() -> None:
    calls: list[str] = []
    application = object.__new__(LauncherApplication)
    application.window = RevealWindow()
    application.window.calls = calls
    application._placement = Placement()
    application._qt_app = PresentationApplication()
    application._qt_app.calls = calls
    application._timer = PresentationTimer()
    application._timer.calls = calls
    application.session = RevealSession(calls)
    application._window_gate = PassThroughWindowGate()
    application._window_visible = False

    application._reveal_for_handoff()

    assert "show" in calls
    assert "attach_media" not in calls
    assert "begin_media" not in calls
    assert application._window_visible is True


def test_visible_launcher_does_not_realign_after_window_appears() -> None:
    placement = AlignmentPlacement()
    application = object.__new__(LauncherApplication)
    application._window_visible = True
    application._placement = placement
    application._timer = PresentationTimer()
    application._timer.calls = []
    application._target_aligned = False

    application._align_target_window(
        WindowInfo(
            hwnd=4321,
            pid=9876,
            process_path=r"C:\Apps\OpenAI.Codex_x\ChatGPT.exe",
            client_rect=Rect(0, 0, 1920, 1032),
            responsive=True,
        )
    )

    assert placement.aligned_hwnds == []
    assert application._target_aligned is False


def test_target_alignment_uses_notified_window_without_other_process_requery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    placement = AlignmentPlacement()
    application = object.__new__(LauncherApplication)
    application._config = _app_config(
        skin_enabled=True,
        wallpaper_path="wallpaper.png",
    )
    application._window_visible = False
    application._placement = placement
    application._timer = PresentationTimer()
    application._timer.calls = []
    application._target_aligned = False
    revealed: list[None] = []
    monkeypatch.setattr(
        application,
        "_reveal_window",
        lambda: revealed.append(None),
    )
    early_window = WindowInfo(
        hwnd=1111,
        pid=9876,
        process_path=r"C:\Apps\OpenAI.Codex_x\ChatGPT.exe",
        client_rect=Rect(0, 0, 1280, 720),
        responsive=True,
    )
    monkeypatch.setattr(
        application_module,
        "find_codex_window",
        lambda _config: pytest.fail("几何回调不应重新查询其他进程窗口"),
    )

    application._align_target_window(early_window)

    assert placement.aligned_hwnds == [1111]
    assert revealed == [None]


def test_failed_alignment_does_not_reveal_saved_fullscreen_rect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application = object.__new__(LauncherApplication)
    application._config = _app_config(
        skin_enabled=False,
        wallpaper_path=None,
    )
    application._window_visible = False
    application._placement = type(
        "FailingPlacement",
        (),
        {"align": lambda self, _window: False},
    )()
    application._timer = PresentationTimer()
    application._timer.calls = []
    application._target_aligned = False
    revealed: list[None] = []
    monkeypatch.setattr(
        application_module,
        "find_codex_window",
        lambda _config: None,
    )
    monkeypatch.setattr(
        application,
        "_reveal_window",
        lambda: revealed.append(None),
    )

    application._align_target_window(
        WindowInfo(
            hwnd=4321,
            pid=9876,
            process_path=r"C:\Apps\OpenAI.Codex_x\ChatGPT.exe",
            client_rect=Rect(0, 0, 1920, 1032),
            responsive=True,
        )
    )

    assert revealed == []
    assert "mark:window_align_failed" in application._timer.calls


def test_application_aligns_only_after_window_is_stable(
    qapp,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[CapturingSession] = []

    def create_session(*args: object, **kwargs: object) -> CapturingSession:
        session = CapturingSession(*args, **kwargs)
        captured.append(session)
        return session

    monkeypatch.setattr(application_module, "SessionController", create_session)
    application = LauncherApplication(
        root=tmp_path,
        config=_app_config(
            skin_enabled=False,
            wallpaper_path=None,
        ),
        qt_app=qapp,
        timer=application_module.StageTimer(),
    )

    assert (
        captured[0].kwargs["target_found_callback"]
        == application._conceal_target_window
    )
    assert (
        captured[0].kwargs["target_stable_callback"]
        == application._align_target_window
    )
    application.window.close()


def test_startup_video_fits_entire_frame_to_launcher(qapp) -> None:
    window = BootWindow()

    assert (
        window.video.aspectRatioMode()
        == Qt.AspectRatioMode.IgnoreAspectRatio
    )
    window.close()


def test_startup_poster_fits_entire_frame_to_launcher(qapp, tmp_path: Path) -> None:
    poster_path = tmp_path / "poster.png"
    Image.new("RGB", (160, 90), "#112233").save(poster_path)
    window = BootWindow()
    window.resize(100, 100)

    window.show_poster_first(str(poster_path))
    window.show()
    qapp.processEvents()

    pixmap = window.poster.pixmap()
    assert pixmap is not None
    assert pixmap.width() == window.width()
    assert pixmap.height() == window.height()
    window.close()
