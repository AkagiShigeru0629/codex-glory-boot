from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock

import pytest
from PySide6.QtCore import QProcess

from glory_boot.adapters.win32 import WindowInfo
from glory_boot.domain.models import AppConfig, Rect, ScreenFrame
from glory_boot.services.codex_launcher import (
    CodexLauncher,
    LaunchResult,
    QProcessBackend,
)


def _config() -> AppConfig:
    return AppConfig(
        app_id="OpenAI.Codex_2p2nqsd0c76g0!App",
        process_names=("Codex.exe",),
        process_path_fragment="OpenAI.Codex_",
        video_path="startup.mp4",
        poster_path="poster.png",
        duration=8.0,
        hold_at=6.3,
        transition_start=6.8,
        transition_end=7.6,
        max_wait_seconds=60.0,
        volume=0.35,
        screen_frames=(
            ScreenFrame(0.0, Rect(0.3, 0.2, 0.4, 0.6), 0.75),
            ScreenFrame(7.6, Rect(0.0, 0.0, 1.0, 1.0), 1.0),
        ),
    )


class FakeProcessBackend:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[str] = []
        self._lock = Lock()
        self.launch_started = Event()
        self.release = Event()
        self.release.set()

    def launch(self, app_id: str, arguments: str = "") -> None:
        with self._lock:
            self.calls.append(app_id)
        self.launch_started.set()
        self.release.wait(timeout=2)
        if self.fail:
            raise RuntimeError("explorer unavailable")


def test_concurrent_requests_only_launch_once() -> None:
    backend = FakeProcessBackend()
    launcher = CodexLauncher(
        _config(),
        process_backend=backend,
        window_finder=lambda _config: None,
    )

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(lambda _index: launcher.request_once(), range(8)))

    assert backend.calls == ["OpenAI.Codex_2p2nqsd0c76g0!App"]
    assert sum(result.launch_requested for result in results) == 1
    assert all(result.error is None for result in results)


def test_existing_window_is_reused_without_starting_codex() -> None:
    backend = FakeProcessBackend()
    existing = WindowInfo(
        hwnd=4321,
        pid=99,
        process_path=r"C:\Apps\OpenAI.Codex_x\Codex.exe",
        client_rect=Rect(0, 0, 1200, 800),
        responsive=True,
    )
    launcher = CodexLauncher(
        _config(),
        process_backend=backend,
        window_finder=lambda _config: existing,
    )

    result = launcher.request_once()

    assert result == LaunchResult(
        launch_requested=False,
        existing_window_hwnd=4321,
        error=None,
    )
    assert backend.calls == []


def test_launch_exception_returns_structured_failure() -> None:
    backend = FakeProcessBackend(fail=True)
    launcher = CodexLauncher(
        _config(),
        process_backend=backend,
        window_finder=lambda _config: None,
    )

    result = launcher.request_once()

    assert result.launch_requested is False
    assert result.existing_window_hwnd is None
    assert result.error == "explorer unavailable"


def test_failed_launch_can_be_retried_explicitly() -> None:
    backend = FakeProcessBackend(fail=True)
    launcher = CodexLauncher(
        _config(),
        process_backend=backend,
        window_finder=lambda _config: None,
    )

    first = launcher.request_once()
    backend.fail = False
    second = launcher.request_retry()

    assert first.error == "explorer unavailable"
    assert second.error is None
    assert second.launch_requested is True
    assert len(backend.calls) == 2


def test_request_can_run_away_from_the_ui_thread() -> None:
    backend = FakeProcessBackend()
    backend.release.clear()
    launcher = CodexLauncher(
        _config(),
        process_backend=backend,
        window_finder=lambda _config: None,
    )

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(launcher.request_once)
        assert backend.launch_started.wait(timeout=1)
        assert future.done() is False
        backend.release.set()
        result = future.result(timeout=2)

    assert result.launch_requested is True


def test_window_probe_exception_returns_structured_failure() -> None:
    def failing_finder(_config):
        raise OSError("window enumeration failed")

    launcher = CodexLauncher(
        _config(),
        process_backend=FakeProcessBackend(),
        window_finder=failing_finder,
    )

    result = launcher.request_once()

    assert result.launch_requested is False
    assert result.error == "window enumeration failed"


class RecordingBackend:
    def __init__(self, *, process_id: int) -> None:
        self.process_id = process_id
        self.calls: list[tuple[str, str]] = []

    def launch(self, app_id: str, arguments: str = "") -> int:
        self.calls.append((app_id, arguments))
        return self.process_id


def test_launcher_passes_arguments_and_returns_process_id() -> None:
    backend = RecordingBackend(process_id=9876)
    launcher = CodexLauncher(
        _config(),
        process_backend=backend,
        launch_arguments="--remote-debugging-port=50123",
        window_finder=lambda _config: None,
    )

    result = launcher.request_once()

    assert backend.calls == [
        ("OpenAI.Codex_2p2nqsd0c76g0!App", "--remote-debugging-port=50123")
    ]
    assert result.launched_pid == 9876


def test_shell_backend_rejects_activation_arguments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, list[str]]] = []

    def start_detached(program: str, arguments: list[str]):
        calls.append((program, arguments))
        return True, 1

    monkeypatch.setattr(QProcess, "startDetached", start_detached)

    with pytest.raises(ValueError):
        QProcessBackend().launch(
            "OpenAI.Codex_2p2nqsd0c76g0!App",
            "--remote-debugging-port=50123",
        )

    assert calls == []
