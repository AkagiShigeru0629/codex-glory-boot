import ctypes
import math
import socket
import struct
from collections.abc import Iterable
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import PureWindowsPath

from glory_boot.domain.models import AppConfig, Rect


GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
DWMWA_CLOAKED = 14
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
WM_NULL = 0x0000
SMTO_ABORTIFHUNG = 0x0002
SW_RESTORE = 9
HWND_TOPMOST = -1
SWP_NOACTIVATE = 0x0010
MONITOR_DEFAULTTONEAREST = 2
AF_INET = 2
TCP_TABLE_OWNER_PID_LISTENER = 3
ERROR_INSUFFICIENT_BUFFER = 122
MIN_CLIENT_WIDTH = 450
MIN_CLIENT_HEIGHT = 280
CODEX_WINDOW_CLASS = "Chrome_WidgetWin_1"


class Win32Error(OSError):
    """Windows 原生调用失败。"""


@dataclass(frozen=True, slots=True)
class RawWindowRecord:
    hwnd: int
    pid: int
    class_name: str
    visible: bool
    cloaked: bool
    tool_window: bool
    process_path: str
    client_rect: Rect
    responsive: bool


@dataclass(frozen=True, slots=True)
class WindowInfo:
    hwnd: int
    pid: int
    process_path: str
    client_rect: Rect
    responsive: bool


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


class POINT(ctypes.Structure):
    _fields_ = [
        ("x", wintypes.LONG),
        ("y", wintypes.LONG),
    ]


class MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", RECT),
        ("rcWork", RECT),
        ("dwFlags", wintypes.DWORD),
    ]


class MIB_TCPROW_OWNER_PID(ctypes.Structure):
    _fields_ = [
        ("dwState", wintypes.DWORD),
        ("dwLocalAddr", wintypes.DWORD),
        ("dwLocalPort", wintypes.DWORD),
        ("dwRemoteAddr", wintypes.DWORD),
        ("dwRemotePort", wintypes.DWORD),
        ("dwOwningPid", wintypes.DWORD),
    ]


_user32 = ctypes.WinDLL("user32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)
_iphlpapi = ctypes.WinDLL("iphlpapi", use_last_error=True)

_WNDENUMPROC = ctypes.WINFUNCTYPE(
    wintypes.BOOL,
    wintypes.HWND,
    wintypes.LPARAM,
)
_MONITORENUMPROC = ctypes.WINFUNCTYPE(
    wintypes.BOOL,
    wintypes.HANDLE,
    wintypes.HANDLE,
    ctypes.POINTER(RECT),
    wintypes.LPARAM,
)

_user32.EnumWindows.argtypes = [_WNDENUMPROC, wintypes.LPARAM]
_user32.EnumWindows.restype = wintypes.BOOL
_user32.IsWindowVisible.argtypes = [wintypes.HWND]
_user32.IsWindowVisible.restype = wintypes.BOOL
_user32.GetClassNameW.argtypes = [
    wintypes.HWND,
    wintypes.LPWSTR,
    ctypes.c_int,
]
_user32.GetClassNameW.restype = ctypes.c_int
_user32.GetWindowThreadProcessId.argtypes = [
    wintypes.HWND,
    ctypes.POINTER(wintypes.DWORD),
]
_user32.GetWindowThreadProcessId.restype = wintypes.DWORD
_user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT)]
_user32.GetClientRect.restype = wintypes.BOOL
_user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(POINT)]
_user32.ClientToScreen.restype = wintypes.BOOL
_user32.GetCursorPos.argtypes = [ctypes.POINTER(POINT)]
_user32.GetCursorPos.restype = wintypes.BOOL
_user32.MonitorFromPoint.argtypes = [POINT, wintypes.DWORD]
_user32.MonitorFromPoint.restype = wintypes.HANDLE
_user32.GetMonitorInfoW.argtypes = [
    wintypes.HANDLE,
    ctypes.POINTER(MONITORINFO),
]
_user32.GetMonitorInfoW.restype = wintypes.BOOL
_user32.EnumDisplayMonitors.argtypes = [
    wintypes.HANDLE,
    ctypes.POINTER(RECT),
    _MONITORENUMPROC,
    wintypes.LPARAM,
]
_user32.EnumDisplayMonitors.restype = wintypes.BOOL
_user32.SendMessageTimeoutW.argtypes = [
    wintypes.HWND,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
    wintypes.UINT,
    wintypes.UINT,
    ctypes.POINTER(ctypes.c_size_t),
]
_user32.SendMessageTimeoutW.restype = wintypes.LPARAM
_user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
_user32.ShowWindow.restype = wintypes.BOOL
_user32.SetForegroundWindow.argtypes = [wintypes.HWND]
_user32.SetForegroundWindow.restype = wintypes.BOOL
_user32.SetWindowPos.argtypes = [
    wintypes.HWND,
    wintypes.HWND,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.UINT,
]
_user32.SetWindowPos.restype = wintypes.BOOL

_get_window_long = getattr(
    _user32,
    "GetWindowLongPtrW",
    _user32.GetWindowLongW,
)
_get_window_long.argtypes = [wintypes.HWND, ctypes.c_int]
_get_window_long.restype = ctypes.c_ssize_t

_kernel32.OpenProcess.argtypes = [
    wintypes.DWORD,
    wintypes.BOOL,
    wintypes.DWORD,
]
_kernel32.OpenProcess.restype = wintypes.HANDLE
_kernel32.QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE,
    wintypes.DWORD,
    wintypes.LPWSTR,
    ctypes.POINTER(wintypes.DWORD),
]
_kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
_kernel32.CloseHandle.restype = wintypes.BOOL

_dwmapi.DwmGetWindowAttribute.argtypes = [
    wintypes.HWND,
    wintypes.DWORD,
    ctypes.c_void_p,
    wintypes.DWORD,
]
_dwmapi.DwmGetWindowAttribute.restype = ctypes.c_long
_iphlpapi.GetExtendedTcpTable.argtypes = [
    ctypes.c_void_p,
    ctypes.POINTER(wintypes.DWORD),
    wintypes.BOOL,
    wintypes.ULONG,
    ctypes.c_int,
    wintypes.ULONG,
]
_iphlpapi.GetExtendedTcpTable.restype = wintypes.DWORD


def _process_path(pid: int) -> str:
    handle = _kernel32.OpenProcess(
        PROCESS_QUERY_LIMITED_INFORMATION,
        False,
        pid,
    )
    if not handle:
        return ""

    try:
        buffer = ctypes.create_unicode_buffer(32768)
        size = wintypes.DWORD(len(buffer))
        if not _kernel32.QueryFullProcessImageNameW(
            handle,
            0,
            buffer,
            ctypes.byref(size),
        ):
            return ""
        return buffer.value
    finally:
        _kernel32.CloseHandle(handle)


def process_path_for_pid(pid: int) -> str | None:
    """返回进程完整路径；无权读取或进程不存在时返回 None。"""
    if pid <= 0:
        return None
    return _process_path(pid) or None


def is_responsive(hwnd: int) -> bool:
    result = ctypes.c_size_t()
    return bool(
        _user32.SendMessageTimeoutW(
            hwnd,
            WM_NULL,
            0,
            0,
            SMTO_ABORTIFHUNG,
            100,
            ctypes.byref(result),
        )
    )


def focus_window(hwnd: int) -> None:
    _user32.ShowWindow(hwnd, SW_RESTORE)
    if not _user32.SetForegroundWindow(hwnd):
        raise Win32Error("无法把 Codex 主窗口切换到前台")


def client_screen_rect(hwnd: int) -> Rect:
    """读取窗口客户区的物理屏幕矩形。"""
    if hwnd <= 0:
        raise Win32Error("hwnd 必须是有效窗口句柄")

    client = RECT()
    if not _user32.GetClientRect(hwnd, ctypes.byref(client)):
        raise Win32Error("无法读取目标窗口客户区")
    origin = POINT(client.left, client.top)
    if not _user32.ClientToScreen(hwnd, ctypes.byref(origin)):
        raise Win32Error("无法把客户区原点转换为屏幕坐标")
    return Rect(
        x=origin.x,
        y=origin.y,
        width=client.right - client.left,
        height=client.bottom - client.top,
    )


def set_window_rect(hwnd: int, rect: Rect) -> None:
    """使用物理像素移动无边框启动器窗口。"""
    if hwnd <= 0:
        raise Win32Error("hwnd 必须是有效窗口句柄")
    values = (rect.x, rect.y, rect.width, rect.height)
    if not all(math.isfinite(value) for value in values):
        raise ValueError("窗口矩形必须是有限数值")
    if rect.width <= 0 or rect.height <= 0:
        raise ValueError("窗口宽高必须为正数")

    result = _user32.SetWindowPos(
        hwnd,
        HWND_TOPMOST,
        int(round(rect.x)),
        int(round(rect.y)),
        int(round(rect.width)),
        int(round(rect.height)),
        SWP_NOACTIVATE,
    )
    if not result:
        raise Win32Error("无法设置启动器窗口矩形")


def _monitor_work_rect(monitor: int) -> Rect:
    info = MONITORINFO()
    info.cbSize = ctypes.sizeof(MONITORINFO)
    if not _user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
        raise Win32Error("无法读取显示器工作区")
    work = info.rcWork
    return Rect(
        x=work.left,
        y=work.top,
        width=work.right - work.left,
        height=work.bottom - work.top,
    )


def cursor_work_area() -> Rect:
    """读取光标所在显示器的物理工作区。"""
    point = POINT()
    if not _user32.GetCursorPos(ctypes.byref(point)):
        raise Win32Error("无法读取光标位置")
    monitor = _user32.MonitorFromPoint(point, MONITOR_DEFAULTTONEAREST)
    if not monitor:
        raise Win32Error("无法确定光标所在显示器")
    return _monitor_work_rect(int(monitor))


def monitor_work_areas() -> tuple[Rect, ...]:
    """枚举所有显示器的物理工作区。"""
    areas: list[Rect] = []

    @_MONITORENUMPROC
    def collect(
        monitor: int,
        _hdc: int,
        _clip: object,
        _data: int,
    ) -> bool:
        areas.append(_monitor_work_rect(int(monitor)))
        return True

    if not _user32.EnumDisplayMonitors(0, None, collect, 0):
        raise Win32Error("枚举显示器工作区失败")
    return tuple(areas)


def _listener_owner_pid_from_table(table: bytes, port: int) -> int | None:
    row_size = ctypes.sizeof(MIB_TCPROW_OWNER_PID)
    if len(table) < 4:
        return None
    count = struct.unpack_from("<I", table, 0)[0]
    if count == 0 or len(table) < 4 + count * row_size:
        return None

    owners: set[int] = set()
    for index in range(count):
        row = MIB_TCPROW_OWNER_PID.from_buffer_copy(
            table,
            4 + index * row_size,
        )
        local_port = socket.ntohs(row.dwLocalPort & 0xFFFF)
        if local_port == port:
            owners.add(int(row.dwOwningPid))
    return next(iter(owners)) if len(owners) == 1 else None


def listener_owner_pid(port: int) -> int | None:
    """返回唯一持有指定 TCP 监听端口的进程号。"""
    if not 0 < port <= 65535:
        return None

    size = wintypes.DWORD()
    result = _iphlpapi.GetExtendedTcpTable(
        None,
        ctypes.byref(size),
        False,
        AF_INET,
        TCP_TABLE_OWNER_PID_LISTENER,
        0,
    )
    if result not in {0, ERROR_INSUFFICIENT_BUFFER} or size.value < 4:
        return None

    buffer = ctypes.create_string_buffer(size.value)
    result = _iphlpapi.GetExtendedTcpTable(
        buffer,
        ctypes.byref(size),
        False,
        AF_INET,
        TCP_TABLE_OWNER_PID_LISTENER,
        0,
    )
    if result != 0:
        return None
    return _listener_owner_pid_from_table(buffer.raw[: size.value], port)


def _is_cloaked(hwnd: int) -> bool:
    cloaked = wintypes.DWORD()
    result = _dwmapi.DwmGetWindowAttribute(
        hwnd,
        DWMWA_CLOAKED,
        ctypes.byref(cloaked),
        ctypes.sizeof(cloaked),
    )
    return result == 0 and cloaked.value != 0


def _record_for_window(hwnd: int) -> RawWindowRecord | None:
    class_buffer = ctypes.create_unicode_buffer(256)
    if not _user32.GetClassNameW(hwnd, class_buffer, len(class_buffer)):
        return None

    pid = wintypes.DWORD()
    _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    client = RECT()
    if not _user32.GetClientRect(hwnd, ctypes.byref(client)):
        return None

    return RawWindowRecord(
        hwnd=int(hwnd),
        pid=int(pid.value),
        class_name=class_buffer.value,
        visible=bool(_user32.IsWindowVisible(hwnd)),
        cloaked=_is_cloaked(hwnd),
        tool_window=bool(
            _get_window_long(hwnd, GWL_EXSTYLE) & WS_EX_TOOLWINDOW
        ),
        process_path=_process_path(pid.value),
        client_rect=Rect(
            x=client.left,
            y=client.top,
            width=client.right - client.left,
            height=client.bottom - client.top,
        ),
        responsive=is_responsive(hwnd),
    )


def iter_top_level_windows() -> Iterable[RawWindowRecord]:
    records: list[RawWindowRecord] = []

    @_WNDENUMPROC
    def collect(hwnd: int, _lparam: int) -> bool:
        record = _record_for_window(hwnd)
        if record is not None:
            records.append(record)
        return True

    if not _user32.EnumWindows(collect, 0):
        raise Win32Error("枚举顶层窗口失败")
    return records


def _is_codex_candidate(
    config: AppConfig,
    record: RawWindowRecord,
) -> bool:
    process_name = PureWindowsPath(record.process_path).name.casefold()
    allowed_names = {name.casefold() for name in config.process_names}
    return (
        record.visible
        and not record.cloaked
        and not record.tool_window
        and record.class_name == CODEX_WINDOW_CLASS
        and process_name in allowed_names
        and config.process_path_fragment.casefold()
        in record.process_path.casefold()
        and record.client_rect.width >= MIN_CLIENT_WIDTH
        and record.client_rect.height >= MIN_CLIENT_HEIGHT
        and record.responsive
    )


def select_codex_window(
    config: AppConfig,
    records: Iterable[RawWindowRecord],
) -> WindowInfo | None:
    matches = [
        record for record in records if _is_codex_candidate(config, record)
    ]
    if len(matches) != 1:
        return None

    match = matches[0]
    return WindowInfo(
        hwnd=match.hwnd,
        pid=match.pid,
        process_path=match.process_path,
        client_rect=match.client_rect,
        responsive=match.responsive,
    )


def find_codex_window(config: AppConfig) -> WindowInfo | None:
    return select_codex_window(config, iter_top_level_windows())
