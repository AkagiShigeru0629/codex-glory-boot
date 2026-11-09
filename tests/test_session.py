from dataclasses import dataclass, field
from threading import Condition, Event
import time
from typing import Callable

import pytest
from PySide6.QtCore import QObject, Signal

from glory_boot.adapters.win32 import WindowInfo
from glory_boot.domain.models import AppConfig, Rect, ScreenFrame
from glory_boot.domain.policy import HandoffReason
from glory_boot.services.codex_launcher import LaunchResult
from glory_boot.services.session import SessionController


def _config() -> AppConfig:
    return AppConfig(
        app_id="OpenAI.Codex_2p2nqsd0c76g0!App",
        process_names=("Codex.exe",),
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
            ScreenFrame(6.7, Rect(0.28, 0.12, 0.44, 0.76), 0.95),
            ScreenFrame(7.6, Rect(0.0, 0.0, 1.0, 1.0), 1.0),
        ),
    )


class FakeMedia(QObject):
    first_frame = Signal()
    failed = Signal(str)
    finished = Signal()
    position_changed = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self.position = 0.0
        self.opened_path: str | None = None
        self.play_calls = 0
        self.pause_calls: list[float] = []
        self.plain_pause_calls = 0
        self.resume_calls = 0

    @property
    def position_seconds(self) -> float:
        return self.position

    def open(self, path: str) -> None:
        self.opened_path = path

    def play(self) -> None:
        self.play_calls += 1

    def pause_at(self, seconds: float) -> None:
        self.position = seconds
        self.pause_calls.append(seconds)

    def pause(self) -> None:
        self.plain_pause_calls += 1

    def resume(self) -> None:
        self.resume_calls += 1

    def stop(self) -> None:
        pass


class FakeLauncher:
    def __init__(
        self,
        results: list[LaunchResult] | None = None,
    ) -> None:
        self.calls = 0
        self.called = Event()
        self._results = list(
            results
            or [
                LaunchResult(launch_requested=True),
                LaunchResult(launch_requested=True),
                LaunchResult(launch_requested=True),
            ]
        )
        self._condition = Condition()

    def request_once(self) -> LaunchResult:
        return self._request()

    def request_retry(self) -> LaunchResult:
        return self._request()

    def _request(self) -> LaunchResult:
        with self._condition:
            result = self._results[min(self.calls, len(self._results) - 1)]
            self.calls += 1
            self._condition.notify_all()
        self.called.set()
        return result

    def wait_for_calls(self, count: int) -> bool:
        with self._condition:
            return self._condition.wait_for(
                lambda: self.calls >= count,
                timeout=1,
            )


@dataclass
class FakeWindow:
    waiting_states: list[bool] = field(default_factory=list)
    opacities: list[float] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    fade_calls: int = 0
    close_calls: int = 0

    def winId(self) -> int:
        return 900

    def show_waiting(self, visible: bool) -> None:
        self.waiting_states.append(visible)

    def setWindowOpacity(self, opacity: float) -> None:
        self.opacities.append(opacity)

    def show_error(self, message: str) -> None:
        self.errors.append(message)

    def fade_out(
        self,
        duration_ms: int,
        completed,
    ) -> None:
        assert duration_ms > 0
        self.fade_calls += 1
        completed()

    def close(self) -> None:
        self.close_calls += 1


class FakeDwmController:
    def __init__(self, *, fail_register: bool = False) -> None:
        self.fail_register = fail_register
        self.register_calls: list[int] = []
        self.update_calls: list[tuple[Rect, float, bool]] = []
        self.close_calls = 0

    def register(self, source_hwnd: int) -> None:
        self.register_calls.append(source_hwnd)
        if self.fail_register:
            raise OSError("DWM unavailable")

    def update(
        self,
        destination: Rect,
        opacity: float,
        visible: bool,
    ) -> None:
        self.update_calls.append((destination, opacity, visible))

    def close(self) -> None:
        self.close_calls += 1


def _existing_window() -> WindowInfo:
    return WindowInfo(
        hwnd=4321,
        pid=99,
        process_path=r"C:\Apps\OpenAI.Codex_x\Codex.exe",
        client_rect=Rect(0, 0, 1200, 800),
        responsive=True,
    )


def _session(
    *,
    window_finder: Callable[[AppConfig], WindowInfo | None] = lambda _config: None,
    content_ready_finder: Callable[[], bool] = lambda: True,
    dwm: FakeDwmController | None = None,
    exit_callback=None,
    async_window_probe: bool = False,
    launcher_results: list[LaunchResult] | None = None,
    target_stable_callback: Callable[[WindowInfo], None] | None = None,
):
    media = FakeMedia()
    launcher = FakeLauncher(results=launcher_results)
    window = FakeWindow()
    now = [0.0]
    controller = SessionController(
        _config(),
        launcher=launcher,
        media=media,
        window=window,
        window_finder=window_finder,
        dwm_factory=lambda _destination: dwm or FakeDwmController(),
        viewport_provider=lambda: Rect(0, 0, 1920, 1080),
        exit_callback=exit_callback,
        content_ready_finder=content_ready_finder,
        clock=lambda: now[0],
        schedule_timer=False,
        async_window_probe=async_window_probe,
        target_stable_callback=target_stable_callback,
    )
    return controller, media, launcher, window, now


def test_target_stable_callback_fires_once_per_window() -> None:
    aligned: list[int] = []
    controller, _media, launcher, _window, _now = _session(
        window_finder=lambda _config: _existing_window(),
        target_stable_callback=lambda found: aligned.append(found.hwnd),
    )

    controller.start()
    assert launcher.called.wait(timeout=1)
    controller.tick()
    controller.tick()

    assert aligned == [4321]


def test_session_plays_animation_to_end_before_waiting_for_codex() -> None:
    controller, media, launcher, window, now = _session()
    hold_events: list[None] = []
    controller.hold_started.connect(lambda: hold_events.append(None))
    controller.start()
    assert launcher.called.wait(timeout=1)

    media.position = 6.4
    controller.tick()
    controller.tick()
    assert media.pause_calls == []
    assert window.waiting_states == []
    assert hold_events == []

    media.position = 8.0
    media.finished.emit()
    assert media.pause_calls == [pytest.approx(7.95)]
    assert media.plain_pause_calls == 0
    assert window.waiting_states == [True]
    assert len(hold_events) == 1


def test_window_probe_can_run_without_blocking_the_ui_thread() -> None:
    release = Event()

    def slow_window_finder(_config: AppConfig) -> WindowInfo | None:
        release.wait(timeout=0.3)
        return None

    controller, _media, _launcher, _window, _now = _session(
        window_finder=slow_window_finder,
        async_window_probe=True,
    )
    controller.start()
    started = time.perf_counter()
    controller.tick()
    elapsed = time.perf_counter() - started
    release.set()

    assert elapsed < 0.05


def test_retries_launch_when_a_successful_request_never_creates_a_window() -> None:
    controller, media, launcher, _window, now = _session()
    controller.start()
    assert launcher.wait_for_calls(1)
    controller.tick()

    now[0] = 7.99
    controller.tick()
    assert launcher.calls == 1

    now[0] = 8.0
    controller.tick()

    assert launcher.wait_for_calls(2)
    assert media.pause_calls == []


def test_retries_structured_launch_failure_before_animation_ends() -> None:
    controller, media, launcher, _window, now = _session(
        launcher_results=[
            LaunchResult(
                launch_requested=False,
                error="activation failed",
            ),
            LaunchResult(launch_requested=True),
        ],
    )
    controller.start()
    assert launcher.wait_for_calls(1)
    controller.tick()

    now[0] = 1.0
    controller.tick()

    assert launcher.wait_for_calls(2)
    assert media.pause_calls == []


def test_does_not_retry_launch_after_codex_window_appears() -> None:
    controller, _media, launcher, _window, now = _session(
        window_finder=lambda _config: _existing_window(),
    )
    controller.start()
    assert launcher.wait_for_calls(1)
    controller.tick()
    controller.tick()

    now[0] = 10.0
    controller.tick()

    assert launcher.calls == 1


def test_reactivates_when_a_reused_closing_window_disappears() -> None:
    windows: list[WindowInfo | None] = [_existing_window(), None]

    def flickering_finder(_config: AppConfig) -> WindowInfo | None:
        return windows.pop(0) if windows else None

    controller, _media, launcher, _window, now = _session(
        window_finder=flickering_finder,
        launcher_results=[
            LaunchResult(
                launch_requested=False,
                existing_window_hwnd=4321,
            ),
            LaunchResult(launch_requested=True),
        ],
    )
    controller.start()
    assert launcher.wait_for_calls(1)
    controller.tick()

    now[0] = 8.0
    controller.tick()

    assert launcher.wait_for_calls(2)


def test_waits_for_existing_window_before_reactivating_launch() -> None:
    visible = [True]

    def finder(_config: AppConfig) -> WindowInfo | None:
        return _existing_window() if visible[0] else None

    controller, _media, launcher, _window, now = _session(
        window_finder=finder,
        content_ready_finder=lambda: False,
    )
    controller.start()
    assert launcher.wait_for_calls(1)
    controller.tick()
    controller.tick()

    now[0] = 8.0
    controller.tick()
    assert launcher.calls == 1

    visible[0] = False
    controller.tick()
    controller.tick()
    assert launcher.wait_for_calls(2)


def test_dwm_transition_updates_destination_and_opacity() -> None:
    dwm = FakeDwmController()
    controller, media, launcher, _window, _now = _session(
        window_finder=lambda _config: _existing_window(),
        dwm=dwm,
    )
    controller.start()
    assert launcher.called.wait(timeout=1)

    media.position = 6.7
    controller.tick()
    controller.tick()
    media.position = 7.15
    controller.tick()

    assert dwm.register_calls == [4321]
    destination, opacity, visible = dwm.update_calls[-1]
    assert destination.x == pytest.approx(268.8)
    assert destination.y == pytest.approx(64.8)
    assert destination.width == pytest.approx(1382.4)
    assert destination.height == pytest.approx(950.4)
    assert opacity == pytest.approx(0.975)
    assert visible is True


def test_dwm_registration_failure_uses_window_opacity_fallback() -> None:
    dwm = FakeDwmController(fail_register=True)
    controller, media, launcher, window, _now = _session(
        window_finder=lambda _config: _existing_window(),
        dwm=dwm,
    )
    controller.start()
    assert launcher.called.wait(timeout=1)

    media.position = 6.7
    controller.tick()
    controller.tick()
    media.position = 7.15
    controller.tick()

    assert dwm.register_calls == [4321]
    assert window.opacities
    assert window.opacities[0] == 1.0
    assert window.opacities[-1] < 1.0


def test_timeout_exits_wait_and_hands_off_once() -> None:
    exits: list[None] = []
    completed: list[None] = []
    controller, media, launcher, window, now = _session(
        exit_callback=lambda: exits.append(None),
    )
    controller.handoff_completed.connect(lambda: completed.append(None))
    controller.start()
    assert launcher.called.wait(timeout=1)

    media.position = 8.0
    media.finished.emit()
    now[0] = 60.0
    controller.tick()

    assert window.waiting_states == [True, False]
    assert len(exits) == 1
    assert len(completed) == 1


def test_media_failure_still_requests_codex_and_hands_off() -> None:
    completed: list[None] = []
    controller, media, launcher, _window, _now = _session()
    controller.handoff_completed.connect(lambda: completed.append(None))
    controller.start()

    media.failed.emit("broken video")

    assert launcher.called.wait(timeout=1)
    assert launcher.calls == 1
    assert len(completed) == 1


def test_handoff_is_idempotent() -> None:
    exits: list[None] = []
    completed: list[None] = []
    controller, _media, _launcher, _window, _now = _session(
        exit_callback=lambda: exits.append(None),
    )
    controller.handoff_completed.connect(lambda: completed.append(None))

    controller.handoff(HandoffReason.SKIPPED)
    controller.handoff(HandoffReason.SKIPPED)

    assert len(exits) == 1
    assert len(completed) == 1


def test_window_finder_failure_is_treated_as_codex_not_ready() -> None:
    def failing_finder(_config: AppConfig) -> WindowInfo | None:
        raise OSError("window enumeration failed")

    controller, media, launcher, _window, _now = _session(
        window_finder=failing_finder,
    )

    controller.start()
    assert launcher.called.wait(timeout=1)
    media.position = 6.4
    controller.tick()

    assert media.pause_calls == []
    media.position = 8.0
    media.finished.emit()
    assert media.pause_calls == [pytest.approx(7.95)]


def test_skip_without_detected_codex_exits_without_blocking_error() -> None:
    exits: list[None] = []
    controller, _media, _launcher, window, _now = _session(
        exit_callback=lambda: exits.append(None),
    )

    controller.handoff(HandoffReason.SKIPPED)

    assert window.errors == []
    assert window.close_calls == 1
    assert len(exits) == 1


def test_stable_codex_window_stays_ready_after_transient_probe_failure() -> None:
    controller, media, launcher, _window, _now = _session(
        window_finder=lambda _config: _existing_window(),
    )
    controller.start()
    assert launcher.called.wait(timeout=1)
    controller.tick()
    controller.set_window_finder(lambda _config: None)

    media.position = 6.4
    controller.tick()

    assert media.pause_calls == []


def test_window_shell_is_not_ready_until_primary_renderer_is_mounted() -> None:
    content_ready = [False]
    dwm = FakeDwmController()
    controller, media, launcher, _window, now = _session(
        window_finder=lambda _config: _existing_window(),
        content_ready_finder=lambda: content_ready[0],
        dwm=dwm,
    )
    controller.start()
    assert launcher.called.wait(timeout=1)

    media.position = 7.2
    controller.tick()
    controller.tick()
    controller.tick()

    assert dwm.register_calls == []
    assert media.pause_calls == []

    content_ready[0] = True
    now[0] = 1.0
    controller.tick()

    assert dwm.register_calls == [4321]
    assert media.resume_calls == 0


def test_stable_window_falls_back_to_ready_after_eight_seconds() -> None:
    dwm = FakeDwmController()
    controller, media, launcher, _window, now = _session(
        window_finder=lambda _config: _existing_window(),
        content_ready_finder=lambda: False,
        dwm=dwm,
    )
    controller.start()
    assert launcher.called.wait(timeout=1)
    controller.tick()
    controller.tick()

    media.position = 7.2
    now[0] = 7.99
    controller.tick()
    assert dwm.register_calls == []

    now[0] = 8.0
    controller.tick()
    assert dwm.register_calls == [4321]


def test_transient_window_probe_miss_does_not_reset_ready_fallback() -> None:
    probes = [0]
    dwm = FakeDwmController()

    def flickering_finder(_config: AppConfig) -> WindowInfo | None:
        probes[0] += 1
        return _existing_window() if probes[0] in {1, 3, 4} else None

    controller, media, launcher, _window, now = _session(
        window_finder=flickering_finder,
        content_ready_finder=lambda: False,
        dwm=dwm,
    )
    controller.start()
    assert launcher.called.wait(timeout=1)
    controller.tick()
    controller.tick()
    now[0] = 8.0
    controller.tick()
    media.position = 7.2
    controller.tick()

    assert dwm.register_calls == [4321]


def test_media_finish_does_not_close_before_renderer_is_mounted() -> None:
    controller, media, launcher, window, _now = _session(
        content_ready_finder=lambda: False,
    )
    controller.start()
    assert launcher.called.wait(timeout=1)

    media.position = 8.0
    media.finished.emit()
    controller.tick()

    assert window.close_calls == 0
    assert window.waiting_states == [True]
    assert media.pause_calls == [pytest.approx(7.95)]
    assert media.plain_pause_calls == 0


def test_media_pauses_before_end_of_media_to_hold_last_frame() -> None:
    controller, media, launcher, window, _now = _session(
        content_ready_finder=lambda: False,
    )
    controller.start()
    assert launcher.called.wait(timeout=1)

    media.position = 7.95
    media.position_changed.emit(7950)
    assert media.pause_calls == [pytest.approx(7.95)]
    assert window.waiting_states == [True]

    media.finished.emit()

    assert media.pause_calls == [pytest.approx(7.95)]
    assert window.waiting_states == [True]
    assert window.close_calls == 0


def test_media_finish_holds_final_frame_for_two_point_five_seconds() -> None:
    controller, media, launcher, window, now = _session(
        window_finder=lambda _config: _existing_window(),
    )
    controller.start()
    assert launcher.called.wait(timeout=1)
    controller.tick()
    controller.tick()

    media.position = 8.0
    media.finished.emit()
    now[0] = 2.49
    controller.tick()
    assert window.close_calls == 0
    assert media.pause_calls == [pytest.approx(7.95)]
    assert media.plain_pause_calls == 0

    now[0] = 2.5
    controller.tick()
    assert window.fade_calls == 1
    assert window.close_calls == 1


def test_skip_handoff_also_uses_fade_before_close() -> None:
    controller, _media, _launcher, window, _now = _session(
        exit_callback=lambda: None,
    )

    controller.handoff(HandoffReason.SKIPPED)

    assert window.fade_calls == 1
    assert window.close_calls == 1
