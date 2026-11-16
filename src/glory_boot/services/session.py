import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from threading import Lock
from typing import Protocol

from PySide6.QtCore import QObject, QTimer, Signal

from glory_boot.adapters.dwm import DwmController
from glory_boot.adapters.win32 import (
    WindowInfo,
    find_codex_window,
    focus_window,
)
from glory_boot.domain.geometry import destination_at
from glory_boot.domain.models import AppConfig
from glory_boot.domain.policy import (
    HandoffPolicy,
    HandoffReason,
)
from glory_boot.domain.timeline import transition_progress
from glory_boot.diagnostics import StageTimer
from glory_boot.services.codex_launcher import (
    CodexLauncher,
    LaunchResult,
)
from glory_boot.services.media import MediaController

FINAL_FRAME_HOLD_SECONDS = 0.2
FINAL_FRAME_BACKOFF_SECONDS = 0.05
FADE_OUT_DURATION_MS = 360
LAUNCH_FAILURE_RETRY_SECONDS = 1.0
LAUNCH_WINDOW_GRACE_SECONDS = 8.0
MAX_LAUNCH_ATTEMPTS = 3


class SessionMedia(Protocol):
    position_seconds: float
    position_changed: Signal
    failed: Signal
    finished: Signal

    def open(self, path: str) -> None:
        ...

    def play(self) -> None:
        ...

    def pause_at(self, seconds: float) -> None:
        ...

    def pause(self) -> None:
        ...

    def resume(self) -> None:
        ...

    def stop(self) -> None:
        ...


class SessionWindow(Protocol):
    def winId(self) -> int:
        ...

    def show_waiting(self, visible: bool) -> None:
        ...

    def fade_out(
        self,
        duration_ms: int,
        completed: Callable[[], None],
    ) -> None:
        ...

    def setWindowOpacity(self, opacity: float) -> None:
        ...

    def show_error(self, message: str) -> None:
        ...

    def close(self) -> None:
        ...


class SessionController(QObject):
    """连接媒体、启动请求、窗口探测和交接状态。"""

    handoff_started = Signal()
    handoff_completed = Signal()
    launch_result_ready = Signal(object)

    def __init__(
        self,
        config: AppConfig,
        *,
        launcher: CodexLauncher,
        media: MediaController | SessionMedia,
        window: SessionWindow,
        window_finder: Callable[[AppConfig], WindowInfo | None] = find_codex_window,
        target_found_callback: Callable[[WindowInfo], None] | None = None,
        target_stable_callback: Callable[[WindowInfo], None] | None = None,
        dwm_factory: Callable[[int], DwmController] | None = None,
        viewport_provider: Callable[[], object] | None = None,
        exit_callback: Callable[[], None] | None = None,
        clock: Callable[[], float] = time.monotonic,
        schedule_timer: bool = True,
        async_window_probe: bool = True,
        timer_interval_ms: int = 250,
        final_hold_seconds: float = FINAL_FRAME_HOLD_SECONDS,
        fade_out_ms: int = FADE_OUT_DURATION_MS,
        stage_timer: StageTimer | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.config = config
        self.launcher = launcher
        self.media = media
        self.window = window
        self._window_finder = window_finder
        self._target_found_callback = target_found_callback
        self._target_stable_callback = target_stable_callback
        self._dwm_factory = dwm_factory or (
            lambda destination_hwnd: DwmController(
                destination_hwnd=destination_hwnd
            )
        )
        self._viewport_provider = viewport_provider
        self._exit_callback = exit_callback
        self._clock = clock
        self._schedule_timer = schedule_timer
        self._async_window_probe = async_window_probe
        self._final_hold_seconds = final_hold_seconds
        self._fade_out_ms = fade_out_ms
        self._stage_timer = stage_timer
        self._timer = QTimer(self)
        self._timer.setInterval(timer_interval_ms)
        self._timer.timeout.connect(self.tick)
        self._worker = ThreadPoolExecutor(max_workers=1)
        self._probe_worker = (
            ThreadPoolExecutor(max_workers=1)
            if async_window_probe
            else None
        )
        self._launch_lock = Lock()
        self._launch_future: Future[LaunchResult] | None = None
        self._launch_result_emitted = False
        self._launch_attempts = 0
        self._expected_pid: int | None = None
        self._launch_accepted_at: float | None = None
        self._launch_retry_at: float | None = None
        self._launch_confirmed = False
        self._probe_future: Future[WindowInfo | None] | None = None
        self._started = False
        self._started_at = 0.0
        self._media_started = False
        self._handing_off = False
        self._source_window: WindowInfo | None = None
        self._probe_miss_count = 0
        self._stable_count = 0
        self._stable_notified_hwnds: set[int] = set()
        self._found_notified_hwnds: set[int] = set()
        self._target_frame_ready = False
        self._media_finished_at: float | None = None
        self._dwm: DwmController | None = None
        self._dwm_failed = False
        self._policy = HandoffPolicy()

        self.media.failed.connect(self._on_media_failed)
        self.media.finished.connect(self._on_media_finished)
        self.media.position_changed.connect(self._on_media_position_changed)

    def start(self, *, defer_media: bool = False) -> None:
        if self._started:
            return
        self._started = True
        self._started_at = self._clock()

        if not defer_media:
            self._start_media()
        self._ensure_launch_requested()
        if self._schedule_timer:
            self._timer.start()
        self.tick()

    def begin_media(self) -> None:
        self._start_media()
        self.tick()

    def _start_media(self) -> None:
        if self._media_started or self._handing_off:
            return
        self._media_started = True
        self.media.open(self.config.video_path)
        if self._stage_timer is not None:
            self._stage_timer.mark("media_requested")
        self.media.play()

    def tick(self) -> None:
        if not self._started or self._handing_off:
            return

        self._poll_launch_state()
        self._retry_launch_if_needed()
        if not self._target_frame_ready and self._launch_result_emitted:
            self._poll_codex_state()

        target_ready = self._target_frame_ready
        if (
            not self._media_started
            and not target_ready
            and self._clock() - self._started_at
            >= self.config.max_wait_seconds
        ):
            self.handoff(HandoffReason.TIMEOUT)
            return
        if (
            target_ready
            and self._stage_timer is not None
            and "codex_stable" not in self._stage_timer.marks
        ):
            self._stage_timer.mark("codex_stable")
        if self._media_finished_at is not None:
            finished_seconds = self._clock() - self._media_finished_at
            self.window.show_waiting(False)
            if finished_seconds >= self._final_hold_seconds:
                self.handoff(HandoffReason.COMPLETED)
            return

        progress = transition_progress(
            self.config,
            media_seconds=self.media.position_seconds,
        )

        if target_ready:
            self._update_transition(progress)

    def handoff(self, reason: HandoffReason) -> None:
        if self._handing_off:
            return
        self._handing_off = True
        self.handoff_started.emit()
        self._timer.stop()
        self.window.show_waiting(False)

        existing = self._source_window or self._find_window()
        decision = self._policy.decide(
            reason,
            window_available=existing is not None,
        )
        if decision.reveal_existing_window and existing is not None:
            try:
                focus_window(existing.hwnd)
            except Exception as exc:
                self.window.show_error(f"无法激活 Codex：{exc}")
        elif decision.show_error:
            self.window.show_error("未找到可用的 Codex 主窗口")

        dwm_complete = (
            self._dwm is not None
            and not self._dwm_failed
            and self.media.position_seconds >= self.config.transition_end
        )
        if dwm_complete:
            if self._stage_timer is not None:
                self._stage_timer.mark("handoff_direct_dwm")
            self._finish_handoff()
            return

        try:
            self.window.fade_out(self._fade_out_ms, self._finish_handoff)
        except Exception:
            self._finish_handoff()

    def _finish_handoff(self) -> None:
        self.media.stop()
        if self._dwm is not None:
            try:
                self._dwm.close()
            finally:
                self._dwm = None
        self._worker.shutdown(wait=False, cancel_futures=True)
        if self._probe_worker is not None:
            self._probe_worker.shutdown(wait=False, cancel_futures=True)
        self.window.close()
        if self._exit_callback is not None:
            self._exit_callback()
        if self._stage_timer is not None:
            self._stage_timer.mark("handoff_complete")
        self.handoff_completed.emit()

    def set_window_finder(
        self,
        window_finder: Callable[[AppConfig], WindowInfo | None],
    ) -> None:
        self._window_finder = window_finder

    def _poll_codex_state(self) -> None:
        if self._async_window_probe:
            if self._probe_future is None:
                assert self._probe_worker is not None
                self._probe_future = self._probe_worker.submit(
                    self._probe_codex_state
                )
                return
            if not self._probe_future.done():
                return
            future = self._probe_future
            self._probe_future = None
            try:
                found = future.result()
            except Exception:
                found = None
        else:
            found = self._probe_codex_state()
        self._apply_codex_state(found)

    def _probe_codex_state(self) -> WindowInfo | None:
        return self._find_window()

    def _apply_codex_state(
        self,
        found: WindowInfo | None,
    ) -> None:
        if found is None:
            if self._source_window is not None:
                self._probe_miss_count += 1
                if self._probe_miss_count < 3:
                    return
            self._source_window = None
            self._probe_miss_count = 0
            self._stable_count = 0
            return
        self._probe_miss_count = 0
        if (
            self._source_window is None
            or self._source_window.hwnd != found.hwnd
        ):
            self._source_window = found
            self._stable_count = 1
            if self._stage_timer is not None:
                self._stage_timer.mark("codex_window_found")
            if (
                found.hwnd not in self._found_notified_hwnds
                and self._target_found_callback is not None
            ):
                self._found_notified_hwnds.add(found.hwnd)
                try:
                    self._target_found_callback(found)
                except Exception:
                    if self._stage_timer is not None:
                        self._stage_timer.mark(
                            "window_found_callback_failed"
                        )
            return

        self._stable_count += 1
        if (
            self._stable_count == 2
            and found.hwnd not in self._stable_notified_hwnds
        ):
            self._stable_notified_hwnds.add(found.hwnd)
            if self._target_stable_callback is not None:
                try:
                    self._target_stable_callback(found)
                except Exception:
                    if self._stage_timer is not None:
                        self._stage_timer.mark("window_alignment_failed")
        if self._stable_count >= 2 and self._media_started:
            self._mark_target_frame_ready()

    def _mark_target_frame_ready(self) -> None:
        if self._target_frame_ready:
            return
        self._target_frame_ready = True
        self._launch_confirmed = True
        self._launch_retry_at = None
        if self._stage_timer is not None:
            self._stage_timer.mark("target_frame_ready")

    def _ensure_launch_requested(
        self,
    ) -> Future[LaunchResult] | None:
        with self._launch_lock:
            if self._launch_attempts > 0:
                return self._launch_future
        return self._submit_launch(retry=False)

    def _submit_launch(self, *, retry: bool) -> Future[LaunchResult]:
        with self._launch_lock:
            if self._launch_future is None:
                self._launch_future = self._worker.submit(
                    self._request_launch,
                    retry,
                )
                self._launch_attempts += 1
                self._launch_retry_at = None
            return self._launch_future

    def _poll_launch_state(self) -> None:
        future = self._launch_future
        if future is None or not future.done():
            return

        self._launch_future = None
        try:
            result = future.result()
        except Exception as exc:
            result = LaunchResult(
                launch_requested=False,
                error=str(exc) or type(exc).__name__,
            )

        now = self._clock()
        if result.error is not None:
            self._launch_accepted_at = None
            self._launch_retry_at = now + LAUNCH_FAILURE_RETRY_SECONDS
            if self._stage_timer is not None:
                self._stage_timer.mark("codex_launch_failed")
            return

        if result.existing_window_hwnd is not None:
            self._expected_pid = None
            self._launch_accepted_at = now
            self._launch_retry_at = None
            if self._stage_timer is not None:
                self._stage_timer.mark("codex_launch_reused")
            self._emit_launch_result(result)
            return

        if result.launch_requested:
            if result.launched_pid is not None and result.launched_pid > 0:
                self._expected_pid = result.launched_pid
            self._launch_accepted_at = now
            self._launch_retry_at = None
            if self._stage_timer is not None:
                self._stage_timer.mark("codex_launch_accepted")
            self._emit_launch_result(result)
            return

        self._launch_accepted_at = None
        self._launch_retry_at = now + LAUNCH_FAILURE_RETRY_SECONDS

    def _emit_launch_result(self, result: LaunchResult) -> None:
        if self._launch_result_emitted:
            return
        self._launch_result_emitted = True
        self.launch_result_ready.emit(result)

    def _retry_launch_if_needed(self) -> None:
        if (
            self._launch_confirmed
            or self._source_window is not None
            or self._launch_future is not None
            or self._launch_attempts >= MAX_LAUNCH_ATTEMPTS
        ):
            return

        now = self._clock()
        retry_due = (
            self._launch_retry_at is not None
            and now >= self._launch_retry_at
        )
        window_missing = (
            self._launch_accepted_at is not None
            and now - self._launch_accepted_at
            >= LAUNCH_WINDOW_GRACE_SECONDS
        )
        if retry_due or window_missing:
            if self._stage_timer is not None:
                self._stage_timer.mark("codex_launch_retry")
            self._submit_launch(retry=True)

    def _find_window(self) -> WindowInfo | None:
        try:
            found = self._window_finder(self.config)
        except OSError:
            return None
        if (
            found is not None
            and self._expected_pid is not None
            and found.pid != self._expected_pid
        ):
            return None
        return found

    def _request_launch(self, retry: bool) -> LaunchResult:
        if self._stage_timer is not None:
            self._stage_timer.mark("codex_launch_requested")
        if retry:
            return self.launcher.request_retry()
        return self.launcher.request_once()

    def _on_media_failed(self, _message: str) -> None:
        self._ensure_launch_requested()
        self.handoff(HandoffReason.MEDIA_FAILED)

    def _on_media_finished(self) -> None:
        self._begin_final_frame_hold()

    def _on_media_position_changed(self, position_ms: int) -> None:
        stop_at_ms = round(
            max(0.0, self.config.duration - FINAL_FRAME_BACKOFF_SECONDS)
            * 1000
        )
        if position_ms >= stop_at_ms:
            self._begin_final_frame_hold()

    def _begin_final_frame_hold(self) -> None:
        if self._media_finished_at is not None:
            return
        self._media_finished_at = self._clock()
        self.media.pause_at(
            max(0.0, self.config.duration - FINAL_FRAME_BACKOFF_SECONDS)
        )
        self.window.show_waiting(False)
        if self._stage_timer is not None:
            self._stage_timer.mark("playback_final_hold")
        self.tick()

    def _frame_opacity(self, seconds: float) -> float:
        frames = self.config.screen_frames
        if seconds <= frames[0].time:
            return frames[0].opacity
        if seconds >= frames[-1].time:
            return frames[-1].opacity
        for previous, following in zip(frames, frames[1:], strict=False):
            if previous.time <= seconds <= following.time:
                progress = (seconds - previous.time) / (
                    following.time - previous.time
                )
                return round(
                    previous.opacity
                    + (following.opacity - previous.opacity) * progress,
                    9,
                )
        return frames[-1].opacity

    def _update_transition(self, progress: float) -> None:
        if self.media.position_seconds < self.config.transition_start:
            return
        if self._source_window is None:
            return

        if self._dwm is None and not self._dwm_failed:
            try:
                self._dwm = self._dwm_factory(int(self.window.winId()))
                self._dwm.register(self._source_window.hwnd)
            except Exception:
                self._dwm_failed = True
                if self._dwm is not None:
                    try:
                        self._dwm.close()
                    finally:
                        self._dwm = None

        if self._dwm_failed or self._dwm is None:
            self.window.setWindowOpacity(max(0.0, 1.0 - progress))
            return

        viewport = (
            self._viewport_provider()
            if self._viewport_provider is not None
            else self._primary_viewport()
        )
        destination = destination_at(
            self.config.screen_frames,
            self.media.position_seconds,
            viewport,
        )
        self._dwm.update(
            destination,
            self._frame_opacity(self.media.position_seconds),
            True,
        )

    def _primary_viewport(self):
        from PySide6.QtGui import QGuiApplication

        screen = QGuiApplication.primaryScreen()
        if screen is None:
            raise RuntimeError("没有可用的显示器")
        geometry = screen.geometry()
        from glory_boot.domain.models import Rect

        return Rect(
            x=geometry.x(),
            y=geometry.y(),
            width=geometry.width(),
            height=geometry.height(),
        )
