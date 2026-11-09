from collections.abc import Callable
from concurrent.futures import Future
from dataclasses import dataclass
from threading import Lock
from typing import Protocol

from PySide6.QtCore import QProcess

from glory_boot.adapters.win32 import (
    WindowInfo,
    find_codex_window,
)
from glory_boot.domain.models import AppConfig


class ProcessBackend(Protocol):
    def launch(self, app_id: str) -> None:
        ...


class QProcessBackend:
    def launch(self, app_id: str) -> None:
        result = QProcess.startDetached(
            "explorer.exe",
            [f"shell:AppsFolder\\{app_id}"],
        )
        started = result[0] if isinstance(result, tuple) else bool(result)
        if not started:
            raise OSError("无法把 Codex 启动请求交给 Windows Shell")


class NoopProcessBackend:
    """只用于无外部副作用的启动基准。"""

    def launch(self, app_id: str) -> None:
        if not app_id:
            raise ValueError("app_id 不能为空")


@dataclass(frozen=True, slots=True)
class LaunchResult:
    launch_requested: bool
    existing_window_hwnd: int | None = None
    error: str | None = None


WindowFinder = Callable[[AppConfig], WindowInfo | None]


class CodexLauncher:
    def __init__(
        self,
        config: AppConfig,
        *,
        process_backend: ProcessBackend | None = None,
        window_finder: WindowFinder = find_codex_window,
    ) -> None:
        self._config = config
        self._process_backend = process_backend or QProcessBackend()
        self._window_finder = window_finder
        self._lock = Lock()
        self._future: Future[LaunchResult] | None = None

    def request_once(self) -> LaunchResult:
        return self._request(force_retry=False)

    def request_retry(self) -> LaunchResult:
        return self._request(force_retry=True)

    def _request(self, *, force_retry: bool) -> LaunchResult:
        owner = False
        with self._lock:
            if self._future is None or (
                force_retry and self._future.done()
            ):
                self._future = Future()
                owner = True
            future = self._future

        if owner:
            try:
                future.set_result(self._launch_or_reuse())
            except BaseException as exc:
                future.set_exception(exc)

        result = future.result()
        if owner:
            if result.error is not None:
                with self._lock:
                    if self._future is future:
                        self._future = None
            return result
        return LaunchResult(
            launch_requested=False,
            existing_window_hwnd=result.existing_window_hwnd,
            error=result.error,
        )

    def _launch_or_reuse(self) -> LaunchResult:
        try:
            existing = self._window_finder(self._config)
        except Exception as exc:
            return LaunchResult(
                launch_requested=False,
                error=str(exc) or type(exc).__name__,
            )
        if existing is not None:
            return LaunchResult(
                launch_requested=False,
                existing_window_hwnd=existing.hwnd,
            )

        try:
            self._process_backend.launch(self._config.app_id)
        except Exception as exc:
            return LaunchResult(
                launch_requested=False,
                error=str(exc) or type(exc).__name__,
            )
        return LaunchResult(launch_requested=True)
