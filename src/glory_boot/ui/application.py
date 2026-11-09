import os
import time
from pathlib import Path
from typing import Sequence

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from glory_boot.adapters.win32 import (
    find_codex_window,
    focus_window,
)
from glory_boot.diagnostics import SingleInstanceGuard, StageTimer
from glory_boot.domain.models import AppConfig
from glory_boot.domain.policy import HandoffReason
from glory_boot.services.codex_launcher import (
    CodexLauncher,
    NoopProcessBackend,
)
from glory_boot.services.codex_readiness import CodexReadinessProbe
from glory_boot.services.media import MediaController
from glory_boot.services.session import SessionController
from glory_boot.ui.boot_window import BootWindow


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
        self.launcher = CodexLauncher(
            config,
            process_backend=NoopProcessBackend() if benchmark else None,
            window_finder=(lambda _config: None)
            if benchmark
            else find_codex_window,
        )
        local_app_data = Path(os.environ.get("LOCALAPPDATA", ""))
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
        self.window.skip_requested.connect(
            lambda: self.session.handoff(HandoffReason.SKIPPED)
        )

    def run(self, *, benchmark: bool = False) -> int:
        self._benchmark = benchmark
        with SingleInstanceGuard() as guard:
            if guard.already_running:
                existing = find_codex_window(self._config)
                if existing is not None:
                    focus_window(existing.hwnd)
                return 0

            self.window.show_poster_first(self._config.poster_path)
            self.window.showFullScreen()
            self._qt_app.processEvents()
            self._timer.mark("window_visible")
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
