import json
from collections.abc import Callable
from typing import Any, Protocol

from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtWebSockets import QWebSocket


class CdpSocket(Protocol):
    connected: Any
    textMessageReceived: Any
    disconnected: Any
    errorOccurred: Any

    def open(self, url: QUrl) -> None:
        ...

    def sendTextMessage(self, message: str) -> int:
        ...

    def close(self) -> None:
        ...

    def abort(self) -> None:
        ...


class CdpClient(QObject):
    """在 Qt 事件循环中执行最小化 Runtime.evaluate 请求。"""

    connected = Signal()
    evaluation_finished = Signal(int, object)
    failed = Signal(str)

    def __init__(
        self,
        *,
        socket_factory: Callable[[str], CdpSocket] | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._socket_factory = socket_factory or (lambda _url: QWebSocket())
        self._socket: CdpSocket | None = None
        self._socket_is_connected = False
        self._closing_intentionally = False
        self._pending: dict[int, QTimer] = {}
        self._retired_timers: list[QTimer] = []
        self._connect_timer = QTimer(self)
        self._connect_timer.setSingleShot(True)
        self._connect_timer.timeout.connect(self._on_connect_timeout)

    @property
    def socket(self) -> CdpSocket | None:
        return self._socket

    def connect_to(
        self,
        websocket_url: str,
        timeout_ms: int = 5000,
    ) -> None:
        if timeout_ms <= 0:
            raise ValueError("连接超时必须是正数")
        self.close()
        self._closing_intentionally = False
        self._socket_is_connected = False
        socket = self._socket_factory(websocket_url)
        if isinstance(socket, QObject):
            socket.setParent(self)
        self._socket = socket
        socket.connected.connect(self._on_connected)
        socket.textMessageReceived.connect(self._on_text_message)
        socket.disconnected.connect(self._on_disconnected)
        socket.errorOccurred.connect(self._on_socket_error)
        self._connect_timer.start(timeout_ms)
        socket.open(QUrl(websocket_url))

    def evaluate(
        self,
        expression: str,
        request_id: int,
        timeout_ms: int = 5000,
    ) -> None:
        if timeout_ms <= 0:
            raise ValueError("评估超时必须是正数")
        if (
            isinstance(request_id, bool)
            or not isinstance(request_id, int)
            or request_id <= 0
        ):
            raise ValueError("request_id 必须是正整数")
        if self._socket is None or not self._socket_is_connected:
            self.failed.emit("not_connected")
            return
        if request_id in self._pending:
            self.failed.emit(f"request_id_in_use:{request_id}")
            return

        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(
            lambda: self._on_evaluate_timeout(request_id, timer)
        )
        self._pending[request_id] = timer
        message = json.dumps(
            {
                "id": request_id,
                "method": "Runtime.evaluate",
                "params": {
                    "expression": expression,
                    "returnByValue": True,
                },
            },
            ensure_ascii=False,
        )
        timer.start(timeout_ms)
        try:
            sent = self._socket.sendTextMessage(message)
        except (OSError, RuntimeError):
            sent = -1
        if sent < 0:
            self._finish_request(request_id)
            self.failed.emit(f"send_failed:{request_id}")

    def close(self) -> None:
        self._closing_intentionally = True
        self._connect_timer.stop()
        for request_id in tuple(self._pending):
            self._finish_request(request_id)
        for timer in self._retired_timers:
            timer.deleteLater()
        self._retired_timers.clear()
        socket = self._socket
        self._socket = None
        self._socket_is_connected = False
        if socket is not None:
            socket.close()

    def _on_connected(self) -> None:
        if not self._is_active_sender():
            return
        self._connect_timer.stop()
        self._socket_is_connected = True
        self.connected.emit()

    def _on_connect_timeout(self) -> None:
        socket = self._socket
        if socket is None or self._socket_is_connected:
            return
        self._socket = None
        self._socket_is_connected = False
        socket.abort()
        self.failed.emit("connect_timeout")

    def _on_socket_error(self, _error: object) -> None:
        if not self._is_active_sender() or self._closing_intentionally:
            return
        self._fail_connection()

    def _on_disconnected(self) -> None:
        if not self._is_active_sender() or self._closing_intentionally:
            return
        self._fail_connection()

    def _fail_connection(self) -> None:
        self._connect_timer.stop()
        for request_id in tuple(self._pending):
            self._finish_request(request_id)
        self._socket = None
        message = (
            "connection_closed"
            if self._socket_is_connected
            else "connect_failed"
        )
        self._socket_is_connected = False
        self.failed.emit(message)

    def _on_text_message(self, message: str) -> None:
        if not self._is_active_sender() or self._closing_intentionally:
            return
        try:
            payload = json.loads(message)
        except (TypeError, ValueError):
            return
        if not isinstance(payload, dict):
            return
        request_id = payload.get("id")
        if (
            isinstance(request_id, bool)
            or not isinstance(request_id, int)
            or request_id not in self._pending
        ):
            return

        self._finish_request(request_id)
        if "error" in payload:
            self.failed.emit(f"evaluation_error:{request_id}")
            return
        self.evaluation_finished.emit(request_id, payload.get("result"))

    def _on_evaluate_timeout(
        self,
        request_id: int,
        timer: QTimer,
    ) -> None:
        if self._pending.get(request_id) is not timer:
            return
        self._finish_request(request_id)
        self.failed.emit(f"evaluation_timeout:{request_id}")

    def _finish_request(self, request_id: int) -> None:
        timer = self._pending.pop(request_id, None)
        if timer is not None:
            timer.stop()
            self._retired_timers.append(timer)

    def _is_active_sender(self) -> bool:
        return self.sender() is self._socket
