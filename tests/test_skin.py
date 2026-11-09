import time
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtTest import QTest

from glory_boot.adapters.devtools import DevToolsPage
from glory_boot.domain.models import SkinConfig
from glory_boot.domain.skin import SkinProfile
from glory_boot.services.skin import SkinController, SkinState
from glory_boot.services.skin_payload import SkinPayload


VERSION = "26.924.22138.0"
PAGE = DevToolsPage(
    "main",
    "app://-/index.html?initialRoute=%2F",
    "ws://127.0.0.1:50123/devtools/page/main",
)
PROFILE = SkinProfile(
    VERSION,
    ("#root",),
    ("--color-surface",),
)
PAYLOAD = SkinPayload(
    install_expression="install()",
    detect_expression="detect()",
    restore_expression="restore()",
)


class FakeCdp(QObject):
    connected = Signal()
    evaluation_finished = Signal(int, object)
    failed = Signal(str)

    def __init__(
        self,
        *,
        capability_value: bool = True,
        install_value: object = True,
        detect_value: object = True,
    ) -> None:
        super().__init__()
        self.capability_value = capability_value
        self.install_value = install_value
        self.detect_value = detect_value
        self.connect_calls: list[tuple[str, int]] = []
        self.evaluation_calls: list[tuple[str, int, int]] = []
        self.close_calls = 0

    def connect_to(self, websocket_url: str, timeout_ms: int = 5000) -> None:
        self.connect_calls.append((websocket_url, timeout_ms))
        QTimer.singleShot(0, self.connected.emit)

    def evaluate(
        self,
        expression: str,
        request_id: int,
        timeout_ms: int = 5000,
    ) -> None:
        self.evaluation_calls.append((expression, request_id, timeout_ms))
        if request_id == 1:
            value = self.capability_value
        elif request_id == 2:
            value = self.install_value
        else:
            value = self.detect_value
        if request_id == 4:
            value = True
        result = {
            "result": {
                "type": "boolean" if isinstance(value, bool) else "object",
                "value": value,
            }
        }
        QTimer.singleShot(
            0,
            lambda: self.evaluation_finished.emit(request_id, result),
        )

    def close(self) -> None:
        self.close_calls += 1


def _skin_controller(
    tmp_path: Path,
    *,
    enabled: bool = True,
    listener_pid: int | None = 10,
    version: str | None = VERSION,
    cdp: FakeCdp | None = None,
    page_finder=None,
    payload_calls: list[tuple[Path, str]] | None = None,
    process_paths: dict[int, str] | None = None,
    timeout_ms: int = 1000,
) -> tuple[SkinController, FakeCdp]:
    cdp_client = cdp or FakeCdp()

    def payload_factory(root: Path, path: str) -> SkinPayload:
        if payload_calls is not None:
            payload_calls.append((root, path))
        return PAYLOAD

    process_path = (
        r"C:\Program Files\WindowsApps"
        rf"\OpenAI.Codex_{version}_x64__x\ChatGPT.exe"
        if version is not None
        else r"C:\Program Files\WindowsApps\Other\ChatGPT.exe"
    )

    def resolve_process_path(pid: int) -> str | None:
        if process_paths is not None:
            return process_paths.get(pid)
        return process_path

    controller = SkinController(
        SkinConfig(
            enabled=enabled,
            wallpaper_path=str(tmp_path / "wallpaper.png"),
        ),
        root=tmp_path,
        port=50123,
        profiles=(PROFILE,),
        page_finder=page_finder or (lambda _port: (PAGE,)),
        listener_owner=lambda _port: listener_pid,
        process_path=resolve_process_path,
        payload_factory=payload_factory,
        cdp_factory=lambda: cdp_client,
        interval_ms=5,
        monitor_interval_ms=100_000,
        reconnect_delay_ms=5,
        timeout_ms=timeout_ms,
        connect_timeout_ms=20,
        evaluate_timeout_ms=20,
    )
    return controller, cdp_client


class DetectFailCdp(FakeCdp):
    def evaluate(
        self,
        expression: str,
        request_id: int,
        timeout_ms: int = 5000,
    ) -> None:
        if request_id == 3:
            self.evaluation_calls.append((expression, request_id, timeout_ms))
            QTimer.singleShot(
                0,
                lambda: self.failed.emit("evaluation_timeout:3"),
            )
            return
        super().evaluate(expression, request_id, timeout_ms)


class LateCapabilityCdp(FakeCdp):
    def __init__(self) -> None:
        super().__init__()
        self.capability_values = [False, False, True]

    def evaluate(
        self,
        expression: str,
        request_id: int,
        timeout_ms: int = 5000,
    ) -> None:
        if request_id == 1:
            value = self.capability_values.pop(0)
            self.evaluation_calls.append((expression, request_id, timeout_ms))
            QTimer.singleShot(
                0,
                lambda: self.evaluation_finished.emit(
                    request_id,
                    {
                        "result": {
                            "type": "boolean",
                            "value": value,
                        }
                    },
                ),
            )
            return
        super().evaluate(expression, request_id, timeout_ms)


class WallpaperDropCdp(FakeCdp):
    def __init__(self) -> None:
        super().__init__()
        self.health_values = [False, True]
        self.install_count = 0

    def evaluate(
        self,
        expression: str,
        request_id: int,
        timeout_ms: int = 5000,
    ) -> None:
        if request_id == 5:
            value = self.health_values.pop(0)
            self.evaluation_calls.append((expression, request_id, timeout_ms))
            QTimer.singleShot(
                0,
                lambda: self.evaluation_finished.emit(
                    request_id,
                    {
                        "result": {
                            "type": "boolean",
                            "value": value,
                        }
                    },
                ),
            )
            return
        if request_id == 2:
            self.install_count += 1
        super().evaluate(expression, request_id, timeout_ms)


def _wait_for_state(
    qapp,
    controller: SkinController,
    expected: SkinState,
    *,
    timeout_ms: int = 300,
) -> None:
    elapsed = 0
    while controller.state is not expected and elapsed < timeout_ms:
        QTest.qWait(10)
        qapp.processEvents()
        elapsed += 10
    assert controller.state is expected


def test_disabled_controller_never_connects(tmp_path: Path) -> None:
    controller, cdp = _skin_controller(tmp_path, enabled=False)

    controller.start(launched_pid=None)

    assert cdp.connect_calls == []
    assert controller.state is SkinState.DISABLED
    controller.close()


def test_existing_codex_without_launch_pid_is_skipped(tmp_path: Path) -> None:
    controller, cdp = _skin_controller(tmp_path)

    controller.start(launched_pid=None)

    assert controller.state is SkinState.SKIPPED
    assert cdp.connect_calls == []
    controller.close()


def test_listener_pid_mismatch_is_rejected(qapp, tmp_path: Path) -> None:
    launched_path = (
        r"C:\Program Files\WindowsApps"
        rf"\OpenAI.Codex_{VERSION}_x64__x\ChatGPT.exe"
    )
    controller, cdp = _skin_controller(
        tmp_path,
        listener_pid=11,
        process_paths={
            10: launched_path,
            11: r"C:\Program Files\WindowsApps\OpenAI.Other_1.0.0.0_x64__x\Other.exe",
        },
    )

    controller.start(launched_pid=10)
    _wait_for_state(qapp, controller, SkinState.SKIPPED)

    assert cdp.connect_calls == []
    controller.close()


def test_listener_in_same_store_package_is_accepted(
    qapp,
    tmp_path: Path,
) -> None:
    package_path = (
        r"C:\Program Files\WindowsApps"
        rf"\OpenAI.Codex_{VERSION}_x64__x\ChatGPT.exe"
    )
    controller, cdp = _skin_controller(
        tmp_path,
        listener_pid=2996,
        process_paths={
            10: package_path,
            2996: package_path,
        },
    )

    controller.start(launched_pid=10)
    _wait_for_state(qapp, controller, SkinState.INSTALLED)

    assert cdp.connect_calls == [(PAGE.websocket_url, 20)]
    controller.close()


def test_incompatible_version_is_skipped(qapp, tmp_path: Path) -> None:
    controller, cdp = _skin_controller(tmp_path, version="99.0.0.0")

    controller.start(launched_pid=10)
    _wait_for_state(qapp, controller, SkinState.SKIPPED)

    assert cdp.connect_calls == []
    controller.close()


def test_successful_install_runs_detection_and_closes_cdp(
    qapp,
    tmp_path: Path,
) -> None:
    controller, cdp = _skin_controller(tmp_path)

    controller.start(launched_pid=10)
    _wait_for_state(qapp, controller, SkinState.INSTALLED)

    assert cdp.connect_calls == [(PAGE.websocket_url, 20)]
    assert [call[1] for call in cdp.evaluation_calls] == [1, 2, 3]
    assert "#root" in cdp.evaluation_calls[0][0]
    assert "--color-surface" in cdp.evaluation_calls[0][0]
    assert cdp.evaluation_calls[1:] == [
        ("install()", 2, 20),
        ("detect()", 3, 20),
    ]
    assert cdp.close_calls == 0
    controller.close()
    controller.close()
    assert cdp.close_calls == 1


def test_installed_wallpaper_is_reapplied_after_page_reset(
    qapp,
    tmp_path: Path,
) -> None:
    cdp = WallpaperDropCdp()
    controller, _cdp = _skin_controller(tmp_path, cdp=cdp)

    controller.start(launched_pid=10)
    _wait_for_state(qapp, controller, SkinState.INSTALLED)
    controller._check_installed_skin()
    for _ in range(30):
        if cdp.install_count == 2:
            break
        QTest.qWait(10)
        qapp.processEvents()

    assert cdp.install_count == 2
    assert [call[1] for call in cdp.evaluation_calls[-3:]] == [5, 2, 3]
    controller.close()


def test_connection_close_after_install_rediscovers_page(
    qapp,
    tmp_path: Path,
) -> None:
    first = FakeCdp()
    controller, _cdp = _skin_controller(tmp_path, cdp=first)
    controller.start(launched_pid=10)
    _wait_for_state(qapp, controller, SkinState.INSTALLED)

    second = FakeCdp()
    controller._cdp_factory = lambda: second
    controller._on_cdp_failed("connection_closed")

    for _ in range(50):
        if second.connect_calls:
            break
        QTest.qWait(10)
        qapp.processEvents()

    assert second.connect_calls == [(PAGE.websocket_url, 20)]
    _wait_for_state(qapp, controller, SkinState.INSTALLED)
    controller.close()


def test_failed_detection_restores_and_reports_failure(
    qapp,
    tmp_path: Path,
) -> None:
    cdp = FakeCdp(detect_value=False)
    controller, _cdp = _skin_controller(tmp_path, cdp=cdp)

    controller.start(launched_pid=10)
    _wait_for_state(qapp, controller, SkinState.FAILED)

    assert [call[1] for call in cdp.evaluation_calls] == [1, 2, 3, 4]
    assert cdp.evaluation_calls[-1][0] == "restore()"
    assert cdp.close_calls == 1
    controller.close()


def test_detect_transport_failure_restores_installed_wallpaper(
    qapp,
    tmp_path: Path,
) -> None:
    cdp = DetectFailCdp()
    controller, _cdp = _skin_controller(tmp_path, cdp=cdp)

    controller.start(launched_pid=10)
    _wait_for_state(qapp, controller, SkinState.FAILED)

    assert [call[1] for call in cdp.evaluation_calls] == [1, 2, 3, 4]
    assert cdp.evaluation_calls[-1][0] == "restore()"
    assert cdp.close_calls == 1
    controller.close()


def test_waiting_for_page_builds_wallpaper_payload_once(
    qapp,
    tmp_path: Path,
) -> None:
    pages = [(), (), (PAGE,)]
    payload_calls: list[tuple[Path, str]] = []

    def finder(_port: int):
        return pages.pop(0) if pages else (PAGE,)

    controller, _cdp = _skin_controller(
        tmp_path,
        page_finder=finder,
        payload_calls=payload_calls,
    )

    controller.start(launched_pid=10)
    _wait_for_state(qapp, controller, SkinState.INSTALLED)

    assert len(payload_calls) == 1
    controller.close()


def test_missing_page_capability_skips_injection(
    qapp,
    tmp_path: Path,
) -> None:
    cdp = FakeCdp(capability_value=False)
    controller, _cdp = _skin_controller(tmp_path, cdp=cdp)

    controller.start(launched_pid=10)
    _wait_for_state(qapp, controller, SkinState.SKIPPED)

    assert [call[1] for call in cdp.evaluation_calls] == [1, 1, 1, 1, 1]
    assert cdp.close_calls == 1
    controller.close()


def test_capability_is_retried_during_page_initialization(
    qapp,
    tmp_path: Path,
) -> None:
    cdp = LateCapabilityCdp()
    controller, _cdp = _skin_controller(tmp_path, cdp=cdp)

    controller.start(launched_pid=10)
    _wait_for_state(qapp, controller, SkinState.INSTALLED)

    assert [call[1] for call in cdp.evaluation_calls] == [1, 1, 1, 2, 3]
    controller.close()


def test_timeout_stops_waiting_without_connecting(
    qapp,
    tmp_path: Path,
) -> None:
    controller, cdp = _skin_controller(
        tmp_path,
        listener_pid=None,
        timeout_ms=40,
    )

    controller.start(launched_pid=10)
    _wait_for_state(qapp, controller, SkinState.FAILED)

    assert cdp.connect_calls == []
    controller.close()


def test_slow_page_discovery_does_not_block_start(tmp_path: Path) -> None:
    def slow_finder(_port: int):
        time.sleep(0.08)
        return (PAGE,)

    controller, _cdp = _skin_controller(tmp_path, page_finder=slow_finder)

    controller.start(launched_pid=10)

    assert controller.state is SkinState.WAITING
    controller.close()
