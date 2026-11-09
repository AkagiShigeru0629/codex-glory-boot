import json
from collections.abc import Callable

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtTest import QTest

from glory_boot.services.cdp import CdpClient


class NeverOpeningSocket(QObject):
    connected = Signal()
    textMessageReceived = Signal(str)
    disconnected = Signal()
    errorOccurred = Signal(object)

    def open(self, _url: QUrl) -> None:
        return

    def sendTextMessage(self, _message: str) -> int:
        return 0

    def close(self) -> None:
        return

    def abort(self) -> None:
        return


class FakeSocket(QObject):
    connected = Signal()
    textMessageReceived = Signal(str)
    disconnected = Signal()
    errorOccurred = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.opened_url: QUrl | None = None
        self.sent: list[dict[str, object]] = []
        self.close_calls = 0

    def open(self, url: QUrl) -> None:
        self.opened_url = url

    def sendTextMessage(self, message: str) -> int:
        self.sent.append(json.loads(message))
        return len(message)

    def close(self) -> None:
        self.close_calls += 1

    def abort(self) -> None:
        self.close_calls += 1

    def receive_json(self, payload: dict[str, object]) -> None:
        self.textMessageReceived.emit(json.dumps(payload))


def _connected_client(
    socket_factory: Callable[[str], FakeSocket | NeverOpeningSocket],
) -> tuple[CdpClient, FakeSocket]:
    client = CdpClient(socket_factory=socket_factory)
    client.connect_to("ws://127.0.0.1:50123/devtools/page/1", 100)
    socket = client.socket
    assert isinstance(socket, FakeSocket)
    socket.connected.emit()
    return client, socket


def test_connect_timeout_emits_failure(qapp) -> None:
    client = CdpClient(
        socket_factory=lambda _url: NeverOpeningSocket(),
    )
    failures: list[str] = []
    client.failed.connect(failures.append)

    client.connect_to("ws://127.0.0.1:50123/devtools/page/1", 20)
    QTest.qWait(50)

    assert failures == ["connect_timeout"]


def test_response_is_matched_by_request_id(qapp) -> None:
    client, socket = _connected_client(lambda _url: FakeSocket())
    results: list[tuple[int, object]] = []
    client.evaluation_finished.connect(
        lambda request_id, value: results.append((request_id, value))
    )

    client.evaluate("true", request_id=17, timeout_ms=100)
    socket.receive_json(
        {"id": 17, "result": {"result": {"value": True}}}
    )

    assert socket.sent == [
        {
            "id": 17,
            "method": "Runtime.evaluate",
            "params": {"expression": "true", "returnByValue": True},
        }
    ]
    assert results == [(17, {"result": {"value": True}})]


def test_evaluate_timeout_and_unknown_response_are_isolated(qapp) -> None:
    client, socket = _connected_client(lambda _url: FakeSocket())
    failures: list[str] = []
    results: list[tuple[int, object]] = []
    client.failed.connect(failures.append)
    client.evaluation_finished.connect(
        lambda request_id, value: results.append((request_id, value))
    )

    client.evaluate("false", request_id=3, timeout_ms=20)
    socket.receive_json({"id": 99, "result": {"result": {"value": "ignored"}}})
    QTest.qWait(50)

    assert results == []
    assert failures == ["evaluation_timeout:3"]


def test_evaluate_before_connection_fails_without_sending(qapp) -> None:
    client = CdpClient(socket_factory=lambda _url: FakeSocket())
    failures: list[str] = []
    client.failed.connect(failures.append)

    client.evaluate("true", request_id=1)

    assert failures == ["not_connected"]
    assert client.socket is None


def test_close_is_idempotent_and_ignores_late_socket_events(qapp) -> None:
    client, socket = _connected_client(lambda _url: FakeSocket())
    failures: list[str] = []
    client.failed.connect(failures.append)

    client.close()
    client.close()
    socket.connected.emit()
    socket.textMessageReceived.emit(
        json.dumps({"id": 1, "result": {"result": {"value": True}}})
    )

    assert socket.close_calls == 1
    assert client.socket is None
    assert failures == []


def test_socket_error_aborts_failed_socket_and_emits_once(qapp) -> None:
    client, socket = _connected_client(lambda _url: FakeSocket())
    failures: list[str] = []
    client.failed.connect(failures.append)

    socket.errorOccurred.emit(object())

    assert socket.close_calls == 1
    assert client.socket is None
    assert failures == ["connection_closed"]


def test_unexpected_disconnect_aborts_socket_and_emits_once(qapp) -> None:
    client, socket = _connected_client(lambda _url: FakeSocket())
    failures: list[str] = []
    client.failed.connect(failures.append)

    socket.disconnected.emit()

    assert socket.close_calls == 1
    assert client.socket is None
    assert failures == ["connection_closed"]
