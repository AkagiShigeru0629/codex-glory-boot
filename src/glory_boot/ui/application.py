import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Sequence

from PySide6.QtCore import QObject, QTimer
from PySide6.QtWidgets import QApplication

from glory_boot.adapters.codex_runtime import CodexRuntimeStore
from glory_boot.adapters.win32 import (
    WindowInfo,
    client_screen_rect,
    cursor_work_area,
    find_codex_window,
    focus_window,
    monitor_work_areas,
    set_window_rect,
)
from glory_boot.adapters.app_activation import ApplicationActivationBackend
from glory_boot.adapters.network_ports import allocate_loopback_port
from glory_boot.adapters.window_state import WindowStateStore
from glory_boot.diagnostics import SingleInstanceGuard, StageTimer
from glory_boot.domain.models import AppConfig, Rect
from glory_boot.domain.placement import default_launcher_rect
from glory_boot.domain.policy import HandoffReason
from glory_boot.domain.skin import SkinProfile, select_skin_profile
from glory_boot.services.codex_launcher import (
    CodexLauncher,
    FallbackProcessBackend,
    LaunchResult,
    NoopProcessBackend,
    ProcessBackend,
    QProcessBackend,
)
from glory_boot.services.codex_readiness import CodexReadinessProbe
from glory_boot.services.media import MediaController
from glory_boot.services.session import SessionController
from glory_boot.services.skin import SkinController
from glory_boot.services.window_placement import WindowPlacementController
from glory_boot.ui.boot_window import BootWindow


REVEAL_FALLBACK_MS = 12_000


class WindowPresenter(Protocol):
    def winId(self) -> int:
        ...

    def show(self) -> None:
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
    codex_version: str | None = None,
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
        or select_skin_profile(skin_profiles, codex_version) is None
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
        window.show()
        place_window(int(window.winId()), rect)
    except (OSError, RuntimeError, ValueError):
        timer.mark("window_placement_failed")

        window.show()
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
        codex_version: str | None = None,
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
            codex_version=codex_version,
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
            client_rect=client_screen_rect,
            place_window=set_window_rect,
        )
        self._target_aligned = False
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
        readiness = CodexReadinessProbe(
            local_app_data / "Codex" / "Logs",
            launched_at=time.time(),
        )
        self.session = SessionController(
            config,
            launcher=self.launcher,
            media=self.media,
            window=self.window,
            window_finder=(lambda _config: None)
            if benchmark
            else find_codex_window,
            target_stable_callback=self._align_target_window,
            viewport_provider=self._placement.viewport,
            exit_callback=self._qt_app.quit,
            content_ready_finder=(
                (lambda: False)
                if benchmark
                else readiness.is_primary_mounted
            ),
            stage_timer=timer,
            parent=self.window,
        )
        self.media.first_frame.connect(
            lambda: self._timer.mark("media_first_frame")
        )
        self._benchmark = benchmark
        self._window_visible = False
        self._reveal_timer = QTimer(self.window)
        self._reveal_timer.setSingleShot(True)
        self._reveal_timer.timeout.connect(self._reveal_window)
        self.skin = build_skin_controller(
            config,
            root=root,
            options=self._skin_options,
            profiles=skin_profiles,
            stage_marker=timer.mark,
            parent=self.window,
        )
        self.session.handoff_completed.connect(self._remember_placement)
        self.session.handoff_completed.connect(self._close_skin)
        self.session.launch_result_ready.connect(self._start_skin)
        self.window.skip_requested.connect(
            lambda: self.session.handoff(HandoffReason.SKIPPED)
        )

    def _align_target_window(self, window: WindowInfo) -> None:
        if self._window_visible:
            return
        aligned = self._placement.align(window)
        self._target_aligned = aligned
        self._timer.mark(
            "window_aligned" if aligned else "window_align_failed"
        )
        if not self._window_visible:
            self._reveal_window()

    def _remember_placement(self) -> None:
        if self._target_aligned and self._placement.remember_success():
            self._timer.mark("window_geometry_saved")
        elif self._target_aligned:
            self._timer.mark("window_geometry_save_failed")

    def _reveal_window(self) -> None:
        if self._window_visible:
            return
        self._reveal_timer.stop()
        present_initial_window(
            window=self.window,
            placement=self._placement,
            place_window=set_window_rect,
            qt_app=self._qt_app,
            timer=self._timer,
        )
        self.window.attach_media(self.media)
        self.session.begin_media()
        self._window_visible = True

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
            self.skin.start(result.launched_pid)

    def _close_skin(self) -> None:
        if self.skin is not None:
            self.skin.close()

    def run(self, *, benchmark: bool = False) -> int:
        self._benchmark = benchmark
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
                self._reveal_timer.start(REVEAL_FALLBACK_MS)
            if benchmark:
                QTimer.singleShot(1500, self._qt_app.quit)
            try:
                exit_code = self._qt_app.exec()
            finally:
                self._close_skin()
            if benchmark:
                self._timer.mark("benchmark_exit")
            return exit_code


def create_qt_application(argv: Sequence[str] | None = None) -> QApplication:
    application = QApplication.instance()
    if application is not None:
        return application
    return QApplication(list(argv or []))
