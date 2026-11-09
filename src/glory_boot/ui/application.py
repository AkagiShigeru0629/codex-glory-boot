import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Protocol, Sequence

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from glory_boot.adapters.win32 import (
    WindowInfo,
    client_screen_rect,
    cursor_work_area,
    find_codex_window,
    focus_window,
    monitor_work_areas,
    set_window_rect,
)
from glory_boot.adapters.window_state import WindowStateStore
from glory_boot.diagnostics import SingleInstanceGuard, StageTimer
from glory_boot.domain.models import AppConfig, Rect
from glory_boot.domain.placement import default_launcher_rect
from glory_boot.domain.policy import HandoffReason
from glory_boot.services.codex_launcher import (
    CodexLauncher,
    NoopProcessBackend,
)
from glory_boot.services.codex_readiness import CodexReadinessProbe
from glory_boot.services.media import MediaController
from glory_boot.services.session import SessionController
from glory_boot.services.window_placement import WindowPlacementController
from glory_boot.ui.boot_window import BootWindow


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


def present_initial_window(
    *,
    window: WindowPresenter,
    placement: PlacementProvider,
    place_window: Callable[[int, Rect], None],
    qt_app: QtEventProcessor,
    timer: StageMarker,
) -> None:
    """先放置原生窗口，再显示海报，避免先出现错误尺寸。"""
    try:
        rect = placement.initial_viewport()
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
    ) -> None:
        self._root = root
        self._config = config
        self._qt_app = qt_app
        self._timer = timer
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
        self.launcher = CodexLauncher(
            config,
            process_backend=NoopProcessBackend() if benchmark else None,
            window_finder=(lambda _config: None)
            if benchmark
            else find_codex_window,
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
        self.session.handoff_completed.connect(self._remember_placement)
        self.window.skip_requested.connect(
            lambda: self.session.handoff(HandoffReason.SKIPPED)
        )

    def _align_target_window(self, window: WindowInfo) -> None:
        aligned = self._placement.align(window)
        self._target_aligned = aligned
        self._timer.mark(
            "window_aligned" if aligned else "window_align_failed"
        )

    def _remember_placement(self) -> None:
        if self._target_aligned and self._placement.remember_success():
            self._timer.mark("window_geometry_saved")
        elif self._target_aligned:
            self._timer.mark("window_geometry_save_failed")

    def run(self, *, benchmark: bool = False) -> int:
        self._benchmark = benchmark
        with SingleInstanceGuard() as guard:
            if guard.already_running:
                existing = find_codex_window(self._config)
                if existing is not None:
                    focus_window(existing.hwnd)
                return 0

            self.window.show_poster_first(self._config.poster_path)
            present_initial_window(
                window=self.window,
                placement=self._placement,
                place_window=set_window_rect,
                qt_app=self._qt_app,
                timer=self._timer,
            )
            self.window.attach_media(self.media)

            self.session.start()
            if benchmark:
                QTimer.singleShot(1500, self._qt_app.quit)
            exit_code = self._qt_app.exec()
            if benchmark:
                self._timer.mark("benchmark_exit")
            return exit_code


def create_qt_application(argv: Sequence[str] | None = None) -> QApplication:
    application = QApplication.instance()
    if application is not None:
        return application
    return QApplication(list(argv or []))
