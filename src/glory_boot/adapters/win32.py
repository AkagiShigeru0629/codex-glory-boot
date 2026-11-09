import ctypes
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


_user32 = ctypes.WinDLL("user32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)

_WNDENUMPROC = ctypes.WINFUNCTYPE(
    wintypes.BOOL,
    wintypes.HWND,
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
