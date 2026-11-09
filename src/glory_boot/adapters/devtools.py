import json
import re
from dataclasses import dataclass
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, build_opener


MAX_TARGETS_BYTES = 1_048_576
_AUXILIARY_ROUTE = re.compile(
    r"(?:avatar|quick[.-]?chat|detached|mini|popover|notification)",
    re.IGNORECASE,
)


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise HTTPError(req.full_url, code, msg, headers, fp)


@dataclass(frozen=True, slots=True)
class DevToolsPage:
    target_id: str
    url: str
    websocket_url: str


def _valid_port(port: int) -> bool:
    return not isinstance(port, bool) and 0 < port <= 65535


def validate_websocket_url(value: str, port: int) -> str:
    """只接受绑定到当前端口和 IPv4 回环地址的调试 WebSocket。"""
    if not _valid_port(port):
        raise ValueError("调试端口无效")
    parsed = urlsplit(value)
    try:
        parsed_port = parsed.port
    except ValueError as exc:
        raise ValueError("调试端口无效") from exc
    if (
        parsed.scheme != "ws"
        or parsed.hostname != "127.0.0.1"
        or parsed_port != port
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or not parsed.path.startswith("/devtools/page/")
    ):
        raise ValueError("调试 WebSocket 地址不受信任")
    return value


def parse_targets(
    payload: object,
    port: int,
) -> tuple[DevToolsPage, ...]:
    """从 DevTools 目标列表提取经过严格校验的页面。"""
    if not isinstance(payload, list):
        raise ValueError("调试目标响应必须是数组")

    pages: list[DevToolsPage] = []
    for item in payload:
        if not isinstance(item, dict) or item.get("type") != "page":
            continue
        target_id = item.get("id")
        url = item.get("url")
        websocket_url = item.get("webSocketDebuggerUrl")
        if not all(
            isinstance(value, str)
            for value in (target_id, url, websocket_url)
        ):
            continue
        assert isinstance(target_id, str)
        assert isinstance(url, str)
        assert isinstance(websocket_url, str)
        if not target_id or not url:
            continue
        try:
            validated_socket = validate_websocket_url(websocket_url, port)
        except ValueError:
            continue
        pages.append(DevToolsPage(target_id, url, validated_socket))
    return tuple(pages)


def is_codex_page(page: DevToolsPage) -> bool:
    """判断目标是否为可注入的 Codex 主页面。"""
    try:
        parsed = urlsplit(page.url)
    except ValueError:
        return False
    if (
        parsed.scheme != "app"
        or parsed.hostname != "-"
        or parsed.path != "/index.html"
    ):
        return False

    routes = parse_qs(parsed.query, keep_blank_values=True)
    initial_routes = routes.get("initialRoute", ["/"])
    return not any(_AUXILIARY_ROUTE.search(route) for route in initial_routes)


def find_pages(
    port: int,
    timeout_ms: int = 1000,
) -> tuple[DevToolsPage, ...]:
    """向本机 DevTools 端点请求页面列表；不得在界面线程调用。"""
    if not _valid_port(port):
        raise ValueError("调试端口无效")
    if timeout_ms <= 0:
        raise ValueError("超时时间必须为正数")

    opener = build_opener(ProxyHandler({}), _RejectRedirects())
    with opener.open(
        f"http://127.0.0.1:{port}/json/list",
        timeout=timeout_ms / 1000,
    ) as response:
        body = response.read(MAX_TARGETS_BYTES + 1)
    if len(body) > MAX_TARGETS_BYTES:
        raise ValueError("调试目标响应过大")
    payload = json.loads(body.decode("utf-8"))
    return tuple(
        page for page in parse_targets(payload, port) if is_codex_page(page)
    )
