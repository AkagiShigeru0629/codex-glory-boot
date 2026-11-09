import json
import socket
import struct
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from urllib.error import HTTPError

import pytest

import glory_boot.adapters.win32 as win32
from glory_boot.adapters.devtools import (
    DevToolsPage,
    find_pages,
    is_codex_page,
    parse_targets,
    validate_websocket_url,
)


def test_rejects_non_loopback_socket() -> None:
    with pytest.raises(ValueError):
        validate_websocket_url(
            "ws://192.168.1.10:50123/devtools/page/1",
            50123,
        )


def test_rejects_wrong_port_and_credentials() -> None:
    with pytest.raises(ValueError):
        validate_websocket_url(
            "ws://127.0.0.1:50000/devtools/page/1",
            50123,
        )
    with pytest.raises(ValueError):
        validate_websocket_url(
            "ws://user:pass@127.0.0.1:50123/devtools/page/1",
            50123,
        )


def test_accepts_main_codex_page() -> None:
    page = DevToolsPage(
        "1",
        "app://-/index.html?initialRoute=%2F",
        "ws://127.0.0.1:50123/devtools/page/1",
    )

    assert is_codex_page(page)


def test_malformed_codex_page_url_is_rejected() -> None:
    page = DevToolsPage(
        "1",
        "app://[bad",
        "ws://127.0.0.1:50123/devtools/page/1",
    )

    assert not is_codex_page(page)


@pytest.mark.parametrize(
    "route",
    [
        "/avatar-overlay",
        "/quick-chat",
        "/detached",
        "/mini",
        "/popover",
        "/notification",
    ],
)
def test_rejects_auxiliary_codex_pages(route: str) -> None:
    page = DevToolsPage(
        "1",
        f"app://-/index.html?initialRoute={route}",
        "ws://127.0.0.1:50123/devtools/page/1",
    )

    assert not is_codex_page(page)


def test_parse_targets_ignores_invalid_and_foreign_socket() -> None:
    payload = [
        {
            "id": "main",
            "type": "page",
            "url": "app://-/index.html",
            "webSocketDebuggerUrl": "ws://127.0.0.1:50123/devtools/page/main",
        },
        {
            "id": "remote",
            "type": "page",
            "url": "app://-/index.html",
            "webSocketDebuggerUrl": "ws://192.168.1.2:50123/devtools/page/remote",
        },
    ]

    assert parse_targets(payload, 50123) == (
        DevToolsPage(
            "main",
            "app://-/index.html",
            "ws://127.0.0.1:50123/devtools/page/main",
        ),
    )


def test_find_pages_reads_only_local_json_targets() -> None:
    payload = [
        {
            "id": "main",
            "type": "page",
            "url": "app://-/index.html?initialRoute=%2F",
            "webSocketDebuggerUrl": "ws://127.0.0.1:0/devtools/page/main",
        }
    ]

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            assert self.path == "/json/list"
            body = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    payload[0]["webSocketDebuggerUrl"] = (
        f"ws://127.0.0.1:{port}/devtools/page/main"
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        assert find_pages(port, timeout_ms=1000) == (
            DevToolsPage(
                "main",
                "app://-/index.html?initialRoute=%2F",
                f"ws://127.0.0.1:{port}/devtools/page/main",
            ),
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=1)


def test_find_pages_rejects_http_redirects() -> None:
    request_paths: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            request_paths.append(self.path)
            self.send_response(302)
            self.send_header("Location", "http://192.0.2.1/")
            self.end_headers()

        def log_message(self, *_args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with pytest.raises(HTTPError) as error:
            find_pages(port, timeout_ms=1000)
        assert error.value.code == 302
        assert request_paths == ["/json/list"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=1)


def test_listener_owner_from_table_uses_network_byte_order_port() -> None:
    row = win32.MIB_TCPROW_OWNER_PID(
        dwState=2,
        dwLocalAddr=int.from_bytes(socket.inet_aton("127.0.0.1"), "little"),
        dwLocalPort=socket.htons(50123),
        dwRemoteAddr=0,
        dwRemotePort=0,
        dwOwningPid=9876,
    )
    table = struct.pack("<I", 1) + bytes(row)

    assert win32._listener_owner_pid_from_table(table, 50123) == 9876
