import json
import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol

from PySide6.QtCore import QObject, QTimer, Signal

from glory_boot.adapters.devtools import DevToolsPage, find_pages
from glory_boot.adapters.win32 import (
    listener_owner_pid,
    process_path_for_pid,
)
from glory_boot.domain.models import SkinConfig
from glory_boot.domain.skin import (
    SkinProfile,
    package_version_from_path,
    select_skin_profile,
)
from glory_boot.services.cdp import CdpClient
from glory_boot.services.skin_payload import SkinPayload, build_skin_payload


class SkinState(StrEnum):
    DISABLED = "disabled"
    WAITING = "waiting"
    SKIPPED = "skipped"
    INSTALLED = "installed"
    FAILED = "failed"
    RESTORED = "restored"


class CdpSession(Protocol):
    connected: Any
    evaluation_finished: Any
    failed: Any

    def connect_to(self, websocket_url: str, timeout_ms: int = 5000) -> None:
        ...

    def evaluate(
        self,
        expression: str,
        request_id: int,
        timeout_ms: int = 5000,
    ) -> None:
        ...

    def close(self) -> None:
        ...


@dataclass(frozen=True, slots=True)
class _DiscoveryResult:
    status: str
    page: DevToolsPage | None = None
    profile: SkinProfile | None = None
    payload: SkinPayload | None = None
    reason: str = ""


def _capability_expression(profile: SkinProfile) -> str:
    selectors = json.dumps(list(profile.required_selectors))
    tokens = json.dumps(list(profile.required_tokens))
    return (
        "(() => {"
        "const root = document.documentElement;"
        "const style = getComputedStyle(root);"
        f"return {selectors}.every((selector) => Boolean(document.querySelector(selector)))"
        f" && {tokens}.every((token) => style.getPropertyValue(token).trim().length > 0);"
        "})()"
    )


def _value_from_result(result: object) -> object:
    current = result
    while isinstance(current, dict) and "value" in current:
        current = current["value"]
    return current


def _installed_from_result(result: object) -> bool:
    value = _value_from_result(result)
    if value is True:
        return True
    return isinstance(value, dict) and value.get("installed") is True


class SkinController(QObject):
    """协调可选壁纸的发现、注入、检测和失败回退。"""

    state_changed = Signal(str)

    CAPABILITY_REQUEST = 1
    INSTALL_REQUEST = 2
    DETECT_REQUEST = 3
    RESTORE_REQUEST = 4

    def __init__(
        self,
        config: SkinConfig,
        *,
        root: Path,
        port: int,
        profiles: tuple[SkinProfile, ...],
        page_finder: Callable[[int], tuple[DevToolsPage, ...]] = find_pages,
        listener_owner: Callable[[int], int | None] = listener_owner_pid,
        process_path: Callable[[int], str | None] = process_path_for_pid,
        payload_factory: Callable[[Path, str], SkinPayload] = build_skin_payload,
        cdp_factory: Callable[[], CdpSession] | None = None,
        stage_marker: Callable[[str], object] | None = None,
        interval_ms: int = 250,
        timeout_ms: int = 15_000,
        connect_timeout_ms: int = 3000,
        evaluate_timeout_ms: int = 3000,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        if interval_ms <= 0 or timeout_ms <= 0:
            raise ValueError("皮肤等待时间必须为正数")
        if connect_timeout_ms <= 0 or evaluate_timeout_ms <= 0:
            raise ValueError("皮肤连接超时必须是正数")

        self._config = config
        self._root = root
        self._port = port
        self._profiles = profiles
        self._page_finder = page_finder
        self._listener_owner = listener_owner
        self._process_path = process_path
        self._payload_factory = payload_factory
        self._cdp_factory = cdp_factory or (
            lambda: CdpClient(parent=self)
        )
        self._stage_marker = stage_marker
        self._connect_timeout_ms = connect_timeout_ms
        self._evaluate_timeout_ms = evaluate_timeout_ms
        self._timeout_seconds = timeout_ms / 1000

        self._state = (
            SkinState.WAITING if config.enabled else SkinState.DISABLED
        )
        self._started = False
        self._closed = False
        self._launched_pid: int | None = None
        self._deadline = 0.0
        self._worker: ThreadPoolExecutor | None = None
        self._future: Future[_DiscoveryResult] | None = None
        self._cdp: CdpSession | None = None
        self._connected = False
        self._phase = ""
        self._page: DevToolsPage | None = None
        self._profile: SkinProfile | None = None
        self._payload: SkinPayload | None = None
        self._restore_after_failure = False
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(interval_ms)
        self._poll_timer.timeout.connect(self._poll)

    @property
    def state(self) -> SkinState:
        return self._state

    def start(self, launched_pid: int | None) -> None:
        if self._started or self._closed:
            return
        self._started = True
        if not self._config.enabled:
            self._finish(SkinState.DISABLED, "skin_disabled")
            return
        if launched_pid is None or launched_pid <= 0:
            self._finish(SkinState.SKIPPED, "skin_skipped_existing")
            return
        if not self._config.wallpaper_path:
            self._finish(SkinState.SKIPPED, "skin_skipped_no_wallpaper")
            return

        self._launched_pid = launched_pid
        self._deadline = time.monotonic() + self._timeout_seconds
        self._worker = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="glory-skin",
        )
        self._mark("skin_waiting")
        self._poll_timer.start()
        self._poll()

    def restore(self) -> None:
        if self._cdp is None or not self._connected or self._closed:
            return
        if self._payload is None:
            return
        self._phase = "restore"
        self._restore_after_failure = False
        self._cdp.evaluate(
            self._payload.restore_expression,
            self.RESTORE_REQUEST,
            self._evaluate_timeout_ms,
        )

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._poll_timer.stop()
        self._close_cdp()
        worker = self._worker
        self._worker = None
        self._future = None
        if worker is not None:
            worker.shutdown(wait=False, cancel_futures=True)

    def _poll(self) -> None:
        if self._closed or self._state is not SkinState.WAITING:
            return
        if time.monotonic() >= self._deadline:
            self._finish(SkinState.FAILED, "skin_timeout")
            return

        future = self._future
        if future is None:
            worker = self._worker
            if worker is None:
                return
            self._future = worker.submit(self._discover)
            return
        if not future.done():
            return

        self._future = None
        try:
            result = future.result()
        except Exception:
            self._finish(SkinState.FAILED, "skin_discovery_failed")
            return

        if result.status == "waiting":
            return
        if result.status == "skipped":
            self._finish(SkinState.SKIPPED, f"skin_skipped_{result.reason}")
            return
        if result.status == "failed":
            self._finish(SkinState.FAILED, f"skin_failed_{result.reason}")
            return
        if (
            result.status != "ready"
            or result.page is None
            or result.profile is None
            or result.payload is None
        ):
            self._finish(SkinState.FAILED, "skin_invalid_discovery")
            return
        self._page = result.page
        self._profile = result.profile
        self._payload = result.payload
        self._connect_cdp()

    def _discover(self) -> _DiscoveryResult:
        pid = self._launched_pid
        if pid is None:
            return _DiscoveryResult("skipped", reason="existing")
        try:
            owner = self._listener_owner(self._port)
        except OSError:
            return _DiscoveryResult("waiting")
        if owner is None:
            return _DiscoveryResult("waiting")
        if owner != pid:
            return _DiscoveryResult("skipped", reason="owner")

        try:
            process_path = self._process_path(pid)
        except OSError:
            return _DiscoveryResult("skipped", reason="process")
        version = package_version_from_path(process_path or "")
        profile = select_skin_profile(self._profiles, version)
        if profile is None:
            return _DiscoveryResult("skipped", reason="version")

        try:
            pages = self._page_finder(self._port)
        except OSError:
            return _DiscoveryResult("waiting")
        except ValueError:
            return _DiscoveryResult("failed", reason="target")
        if not pages:
            return _DiscoveryResult("waiting")
        if len(pages) != 1:
            return _DiscoveryResult("skipped", reason="ambiguous_page")

        wallpaper_path = self._config.wallpaper_path
        if wallpaper_path is None:
            return _DiscoveryResult("skipped", reason="wallpaper")
        try:
            payload = self._payload_factory(self._root, wallpaper_path)
        except (OSError, ValueError):
            return _DiscoveryResult("skipped", reason="wallpaper")
        return _DiscoveryResult(
            "ready",
            page=pages[0],
            profile=profile,
            payload=payload,
        )

    def _connect_cdp(self) -> None:
        if self._closed or self._page is None:
            return
        cdp = self._cdp_factory()
        if isinstance(cdp, QObject):
            cdp.setParent(self)
        self._cdp = cdp
        cdp.connected.connect(self._on_connected)
        cdp.evaluation_finished.connect(self._on_evaluation_finished)
        cdp.failed.connect(self._on_cdp_failed)
        self._phase = "capability"
        cdp.connect_to(
            self._page.websocket_url,
            self._connect_timeout_ms,
        )

    def _on_connected(self) -> None:
        if (
            self._closed
            or self._cdp is None
            or self._profile is None
        ):
            return
        self._connected = True
        self._cdp.evaluate(
            _capability_expression(self._profile),
            self.CAPABILITY_REQUEST,
            self._evaluate_timeout_ms,
        )

    def _on_evaluation_finished(self, request_id: int, result: object) -> None:
        if self._closed:
            return
        if request_id == self.CAPABILITY_REQUEST:
            if _value_from_result(result) is not True:
                self._finish(SkinState.SKIPPED, "skin_skipped_capability")
                return
            if self._cdp is None or self._payload is None:
                self._finish(SkinState.FAILED, "skin_payload_missing")
                return
            self._phase = "install"
            self._cdp.evaluate(
                self._payload.install_expression,
                self.INSTALL_REQUEST,
                self._evaluate_timeout_ms,
            )
            return

        if request_id == self.INSTALL_REQUEST:
            if not _installed_from_result(result):
                self._finish(SkinState.FAILED, "skin_install_rejected")
                return
            if self._cdp is None or self._payload is None:
                self._finish(SkinState.FAILED, "skin_payload_missing")
                return
            self._phase = "detect"
            self._cdp.evaluate(
                self._payload.detect_expression,
                self.DETECT_REQUEST,
                self._evaluate_timeout_ms,
            )
            return

        if request_id == self.DETECT_REQUEST:
            if _value_from_result(result) is True:
                self._finish(SkinState.INSTALLED, "skin_installed")
            else:
                self._restore_then_fail("skin_detection_failed")
            return

        if request_id == self.RESTORE_REQUEST:
            if self._restore_after_failure:
                self._finish(SkinState.FAILED, "skin_restore_failed_after_check")
            else:
                self._finish(SkinState.RESTORED, "skin_restored")

    def _on_cdp_failed(self, reason: str) -> None:
        if self._closed:
            return
        if not reason:
            reason = "unknown"
        if self._phase in {"install", "detect"}:
            self._restore_then_fail(f"skin_cdp_{reason}")
            return
        if self._phase == "restore":
            self._finish(SkinState.FAILED, "skin_restore_failed")
            return
        self._finish(SkinState.FAILED, f"skin_cdp_{reason}")

    def _restore_then_fail(self, reason: str) -> None:
        if self._cdp is None or self._payload is None:
            self._finish(SkinState.FAILED, reason)
            return
        self._restore_after_failure = True
        self._phase = "restore"
        self._cdp.evaluate(
            self._payload.restore_expression,
            self.RESTORE_REQUEST,
            self._evaluate_timeout_ms,
        )

    def _finish(self, state: SkinState, marker: str) -> None:
        if self._closed:
            return
        self._set_state(state)
        self._mark(marker)
        self._poll_timer.stop()
        self._close_cdp()
        worker = self._worker
        self._worker = None
        self._future = None
        if worker is not None:
            worker.shutdown(wait=False, cancel_futures=True)

    def _close_cdp(self) -> None:
        cdp = self._cdp
        self._cdp = None
        self._connected = False
        if cdp is not None:
            cdp.close()

    def _set_state(self, state: SkinState) -> None:
        if state is self._state:
            return
        self._state = state
        self.state_changed.emit(state.value)

    def _mark(self, name: str) -> None:
        if self._stage_marker is not None:
            self._stage_marker(name)
