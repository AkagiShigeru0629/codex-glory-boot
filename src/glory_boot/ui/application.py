import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Sequence

from PySide6.QtCore import QObject, QTimer
from PySide6.QtWidgets import QApplication

from glory_boot.adapters.codex_runtime import CodexRuntimeStore
from glory_boot.adapters.win32 import (
    WindowAppIdentity,
    WindowInfo,
    WindowIconHandles,
    cursor_work_area,
    find_codex_window,
    focus_window,
    monitor_work_areas,
    release_window_app_identity,
    release_window_icons,
    set_window_app_identity,
    set_window_icon,
    set_window_rect,
    window_screen_rect,
)
from glory_boot.adapters.app_activation import ApplicationActivationBackend
from glory_boot.adapters.network_ports import allocate_loopback_port
from glory_boot.adapters.window_state import WindowStateStore
from glory_boot.diagnostics import SingleInstanceGuard, StageTimer
from glory_boot.domain.models import AppConfig, Rect
from glory_boot.domain.placement import default_launcher_rect
from glory_boot.domain.policy import HandoffReason
from glory_boot.domain.skin import SkinProfile
from glory_boot.services.codex_launcher import (
    CodexLauncher,
    FallbackProcessBackend,
    LaunchResult,
    NoopProcessBackend,
    ProcessBackend,
    QProcessBackend,
)
from glory_boot.services.media import MediaController
from glory_boot.services.session import SessionController
from glory_boot.services.skin import SkinController, SkinState
from glory_boot.services.window_gate import WindowGateController
from glory_boot.services.window_placement import WindowPlacementController
from glory_boot.ui.boot_window import BootWindow


_SKIN_TERMINAL_STATES = {
    SkinState.DISABLED,
    SkinState.SKIPPED,
    SkinState.INSTALLED,
    SkinState.FAILED,
    SkinState.RESTORED,
}


class WindowPresenter(Protocol):
    def winId(self) -> int:
        ...

    def show(self) -> None:
        ...

    def setWindowOpacity(self, opacity: float) -> None:
        ...


class PlacementProvider(Protocol):
    def initial_viewport(self) -> Rect:
        ...


class QtEventProcessor(Protocol):
    def processEvents(self) -> None:
        ...


class StageMarker(Protocol):
    def mark(self, name: str) -> object:
        ...


@dataclass(frozen=True, slots=True)
class SkinLaunchOptions:
    skin_enabled: bool
    skin_port: int | None
    launch_arguments: str


def prepare_skin_launch(
    config: AppConfig,
    *,
    skin_disabled_by_cli: bool,
    benchmark: bool,
    skin_profiles: tuple[SkinProfile, ...] = (),
    port_allocator: Callable[[], int] = allocate_loopback_port,
) -> SkinLaunchOptions:
    """只在实际启用且存在壁纸时申请一次本机调试端口。"""
    if (
        not config.skin.enabled
        or not config.skin.wallpaper_path
        or not Path(config.skin.wallpaper_path).is_file()
        or skin_disabled_by_cli
        or benchmark
        or not skin_profiles
    ):
        return SkinLaunchOptions(False, None, "")
    try:
        port = port_allocator()
    except OSError:
        return SkinLaunchOptions(False, None, "")
    if isinstance(port, bool) or not isinstance(port, int) or not 0 < port <= 65535:
        raise ValueError("皮肤调试端口无效")
    return SkinLaunchOptions(
        True,
        port,
        (
            "--remote-debugging-address=127.0.0.1 "
            f"--remote-debugging-port={port}"
        ),
    )


def build_process_backend(
    *,
    benchmark: bool,
    skin_enabled: bool,
    noop_factory: Callable[[], ProcessBackend] = NoopProcessBackend,
    activation_factory: Callable[[], ProcessBackend] = (
        ApplicationActivationBackend
    ),
    fallback_factory: Callable[[], ProcessBackend] = QProcessBackend,
) -> ProcessBackend | None:
    """按启动模式选择无副作用、调试激活或普通 Shell 后端。"""
    if benchmark:
        return noop_factory()
    if skin_enabled:
        return FallbackProcessBackend(
            activation_factory(),
            fallback_factory(),
        )
    return None


def build_skin_controller(
    config: AppConfig,
    *,
    root: Path,
    options: SkinLaunchOptions,
    profiles: tuple[SkinProfile, ...],
    stage_marker: Callable[[str], object],
    parent: QObject | None,
    factory: Callable[..., SkinController] = SkinController,
) -> SkinController | None:
    """仅在皮肤启动参数完整时创建控制器，并复用同一回环端口。"""
    if not options.skin_enabled or options.skin_port is None:
        return None
    return factory(
        config=config.skin,
        root=root,
        port=options.skin_port,
        profiles=profiles,
        stage_marker=stage_marker,
        timeout_ms=round(config.max_wait_seconds * 1000),
        parent=parent,
    )


def present_initial_window(
    *,
    window: WindowPresenter,
    placement: PlacementProvider,
    place_window: Callable[[int, Rect], None],
    qt_app: QtEventProcessor,
    timer: StageMarker,
) -> None:
    """显示窗口后立即锁定原生矩形，再处理首帧绘制。"""
    try:
        rect = placement.initial_viewport()
        hwnd = int(window.winId())
        place_window(hwnd, rect)
        window.setWindowOpacity(0.0)
        window.show()
        place_window(hwnd, rect)
    except (OSError, RuntimeError, ValueError):
        timer.mark("window_placement_failed")
        window.show()
    qt_app.processEvents()
    window.setWindowOpacity(1.0)
    qt_app.processEvents()
    timer.mark("window_visible")


class LauncherApplication:
    def __init__(
        self,
        *,
        root: Path,
        config: AppConfig,
        qt_app: QApplication,
        timer: StageTimer,
        benchmark: bool = False,
        skin_disabled_by_cli: bool = False,
        skin_profiles: tuple[SkinProfile, ...] = (),
        runtime_store: CodexRuntimeStore | None = None,
    ) -> None:
        self._root = root
        self._config = config
        self._qt_app = qt_app
        self._timer = timer
        self._runtime_store = runtime_store
        self._skin_options = prepare_skin_launch(
            config,
            skin_disabled_by_cli=skin_disabled_by_cli,
            benchmark=benchmark,
            skin_profiles=skin_profiles,
        )
        self.window = BootWindow()
        self.media = MediaController(self.window)
        self.media.set_volume(config.volume)
        local_app_data = Path(os.environ.get("LOCALAPPDATA", ""))
        self._placement = WindowPlacementController(
            window_hwnd=lambda: int(self.window.winId()),
            state_store=WindowStateStore(
                local_app_data / "GloryBoot" / "window-state.json"
            ),
            monitors=monitor_work_areas,
            default_rect=lambda: default_launcher_rect(cursor_work_area()),
            target_rect=window_screen_rect,
            place_window=set_window_rect,
        )
        self._target_aligned = False
        self._window_gate = WindowGateController()
        process_backend = build_process_backend(
            benchmark=benchmark,
            skin_enabled=self._skin_options.skin_enabled,
        )
        self.launcher = CodexLauncher(
            config,
            process_backend=process_backend,
            window_finder=(lambda _config: None)
            if benchmark
            else find_codex_window,
            launch_arguments=self._skin_options.launch_arguments,
        )
        self._handoff_completed = False
        self._skin_started = False
        self._skip_requested = False
        self.session = SessionController(
            config,
            launcher=self.launcher,
            media=self.media,
            window=self.window,
            window_finder=(lambda _config: None)
            if benchmark
            else find_codex_window,
            target_found_callback=self._conceal_target_window,
            target_stable_callback=self._align_target_window,
            viewport_provider=self._placement.viewport,
            exit_callback=self._request_exit,
            stage_timer=timer,
            parent=self.window,
        )
        self.media.first_frame.connect(
            lambda: self._timer.mark("media_first_frame")
        )
        self._benchmark = benchmark
        self._window_visible = False
        self._window_identity: WindowAppIdentity | None = None
        self._window_icons: WindowIconHandles | None = None
        self.skin = build_skin_controller(
            config,
            root=root,
            options=self._skin_options,
            profiles=skin_profiles,
            stage_marker=timer.mark,
            parent=self.window,
        )
        self.session.handoff_completed.connect(self._remember_placement)
        self.session.handoff_started.connect(self._reveal_for_handoff)
        self.session.launch_result_ready.connect(self._start_skin)
        self.window.skip_requested.connect(self._skip_startup)
        if self.skin is not None:
            self.skin.state_changed.connect(self._on_skin_state_changed)

    def _align_target_window(self, window: WindowInfo) -> None:
        if self._window_visible:
            return
        aligned = self._placement.align(window)
        self._target_aligned = aligned
        self._timer.mark(
            "window_aligned" if aligned else "window_align_failed"
        )
        if aligned:
            self._reveal_window()

    def _conceal_target_window(self, window: WindowInfo) -> None:
        if self._window_gate.conceal(window):
            self._timer.mark("codex_window_concealed")

    def _remember_placement(self) -> None:
        if self._target_aligned and self._placement.remember_success():
            self._timer.mark("window_geometry_saved")
        elif self._target_aligned:
            self._timer.mark("window_geometry_save_failed")

    def _reveal_window(self, *, start_media: bool = True) -> None:
        if self._window_visible:
            return
        present_initial_window(
            window=self.window,
            placement=self._placement,
            place_window=set_window_rect,
            qt_app=self._qt_app,
            timer=self._timer,
        )
        self._apply_taskbar_icon()
        if start_media:
            self._window_gate.release_all()
            self.window.attach_media(self.media)
            self.session.begin_media()
        else:
            self._window_gate.release_all()
        self._window_visible = True

    def _apply_taskbar_icon(self) -> None:
        if self._window_icons is not None:
            return
        identity: WindowAppIdentity | None = None
        icons: WindowIconHandles | None = None
        try:
            hwnd = int(self.window.winId())
            icon_path = self._root / "assets" / "taskbar-icon.ico"
            identity = set_window_app_identity(
                hwnd,
                "Glory.Codex.Boot",
                icon_path,
            )
            icons = set_window_icon(hwnd, icon_path)
            self._window_identity = identity
            self._window_icons = icons
            self._timer.mark("taskbar_icon_applied")
        except OSError:
            release_window_app_identity(identity)
            release_window_icons(icons)
            self._timer.mark("taskbar_icon_failed")

    def _reveal_for_handoff(self) -> None:
        if not self._window_visible:
            self._reveal_window(start_media=False)

    def _focus_existing_codex(self) -> bool:
        try:
            existing = find_codex_window(self._config)
        except OSError:
            return False
        if existing is None:
            return False

        try:
            focus_window(existing.hwnd)
        except OSError:
            self._timer.mark("activation_failed")
        if self._runtime_store is not None:
            self._runtime_store.save(existing.process_path)
        self._timer.mark("codex_launch_reused")
        self._close_skin()
        self.window.close()
        self._timer.mark("handoff_complete")
        return True

    def _start_skin(self, result: LaunchResult) -> None:
        runtime_store = getattr(self, "_runtime_store", None)
        if (
            result.existing_window_hwnd is not None
            and runtime_store is not None
        ):
            existing = find_codex_window(self._config)
            if existing is not None:
                runtime_store.save(existing.process_path)
        if self.skin is not None:
            self._skin_started = True
            self.skin.start(result.launched_pid)

    def _skip_startup(self) -> None:
        self._skip_requested = True
        self.session.handoff(HandoffReason.SKIPPED)

    def _on_skin_state_changed(self, state: str) -> None:
        if (
            self._handoff_completed
            and state in {item.value for item in _SKIN_TERMINAL_STATES}
        ):
            self._close_skin()
            self._qt_app.quit()

    def _request_exit(self) -> None:
        self._handoff_completed = True
        skin_pending = (
            self.skin is not None
            and self._skin_started
            and not self._skip_requested
            and self.skin.state not in _SKIN_TERMINAL_STATES
        )
        if skin_pending:
            return
        self._close_skin()
        self._qt_app.quit()

    def _close_skin(self) -> None:
        if self.skin is not None:
            self.skin.close()

    def run(self, *, benchmark: bool = False) -> int:
        self._benchmark = benchmark
        quit_on_last_window = self._qt_app.quitOnLastWindowClosed()
        self._qt_app.setQuitOnLastWindowClosed(False)
        try:
            with SingleInstanceGuard() as guard:
                if guard.already_running:
                    existing = find_codex_window(self._config)
                    if existing is not None:
                        focus_window(existing.hwnd)
                    self._close_skin()
                    return 0

                if not benchmark and self._focus_existing_codex():
                    return 0

                self.window.show_poster_first(self._config.poster_path)
                if benchmark:
                    self._reveal_window()
                    self.session.start()
                else:
                    self.session.start(defer_media=True)
                if benchmark:
                    QTimer.singleShot(1500, self._qt_app.quit)
                try:
                    exit_code = self._qt_app.exec()
                finally:
                    self._window_gate.release_all()
                    self._close_skin()
                if benchmark:
                    self._timer.mark("benchmark_exit")
                return exit_code
        finally:
            release_window_app_identity(
                getattr(self, "_window_identity", None)
            )
            release_window_icons(getattr(self, "_window_icons", None))
            self._window_identity = None
            self._window_icons = None
            self._qt_app.setQuitOnLastWindowClosed(quit_on_last_window)


def create_qt_application(argv: Sequence[str] | None = None) -> QApplication:
    application = QApplication.instance()
    if application is not None:
        return application
    return QApplication(list(argv or []))
