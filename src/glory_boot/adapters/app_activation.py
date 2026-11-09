import ctypes
from ctypes import wintypes
from typing import Protocol
from uuid import UUID


CLSID_APPLICATION_ACTIVATION_MANAGER = "45BA127D-10A8-46EA-8AB7-56EA9078943C"
IID_IAPPLICATION_ACTIVATION_MANAGER = "2e941141-7f97-4756-ba1d-9decde894a3d"
CLSCTX_LOCAL_SERVER = 0x4
COINIT_APARTMENTTHREADED = 0x2
MAX_ACTIVATION_ARGUMENTS_LENGTH = 4096


class AppActivationError(OSError):
    """Microsoft Store 应用激活失败。"""


class GUID(ctypes.Structure):
    _fields_ = [
        ("data1", wintypes.DWORD),
        ("data2", wintypes.WORD),
        ("data3", wintypes.WORD),
        ("data4", wintypes.BYTE * 8),
    ]


def _guid(value: str) -> GUID:
    return GUID.from_buffer_copy(UUID(value).bytes_le)


_ACTIVATE_APPLICATION = ctypes.WINFUNCTYPE(
    ctypes.c_long,
    ctypes.c_void_p,
    wintypes.LPCWSTR,
    wintypes.LPCWSTR,
    wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD),
)
_RELEASE = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)

_ole32 = ctypes.WinDLL("ole32", use_last_error=True)
_ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, wintypes.DWORD]
_ole32.CoInitializeEx.restype = ctypes.c_long
_ole32.CoUninitialize.argtypes = []
_ole32.CoUninitialize.restype = None
_ole32.CoCreateInstance.argtypes = [
    ctypes.POINTER(GUID),
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.POINTER(GUID),
    ctypes.POINTER(ctypes.c_void_p),
]
_ole32.CoCreateInstance.restype = ctypes.c_long


def _check_hresult(result: int, operation: str) -> None:
    if result >= 0:
        return
    code = ctypes.c_ulong(result).value & 0xFFFFFFFF
    raise AppActivationError(f"{operation} 失败: 0x{code:08X}")


class ApplicationActivator(Protocol):
    def activate(self, app_id: str, arguments: str) -> int:
        ...


class NativeApplicationActivator:
    """通过 IApplicationActivationManager 激活 Store 应用并返回进程号。"""

    def activate(self, app_id: str, arguments: str) -> int:
        initialized = _ole32.CoInitializeEx(None, COINIT_APARTMENTTHREADED)
        _check_hresult(initialized, "CoInitializeEx")
        interface = ctypes.c_void_p()
        try:
            clsid = _guid(CLSID_APPLICATION_ACTIVATION_MANAGER)
            iid = _guid(IID_IAPPLICATION_ACTIVATION_MANAGER)
            result = _ole32.CoCreateInstance(
                ctypes.byref(clsid),
                None,
                CLSCTX_LOCAL_SERVER,
                ctypes.byref(iid),
                ctypes.byref(interface),
            )
            _check_hresult(result, "CoCreateInstance")
            if not interface.value:
                raise AppActivationError("应用激活接口为空")

            vtable = ctypes.cast(
                interface,
                ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)),
            )[0]
            activate = _ACTIVATE_APPLICATION(vtable[3])
            process_id = wintypes.DWORD()
            result = activate(
                interface,
                app_id,
                arguments,
                0,
                ctypes.byref(process_id),
            )
            _check_hresult(result, "ActivateApplication")
            if process_id.value == 0:
                raise AppActivationError("ActivateApplication 未返回进程号")
            return int(process_id.value)
        finally:
            if interface.value:
                vtable = ctypes.cast(
                    interface,
                    ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)),
                )[0]
                _RELEASE(vtable[2])(interface)
            _ole32.CoUninitialize()


class ApplicationActivationBackend:
    def __init__(
        self,
        *,
        activator: ApplicationActivator | None = None,
    ) -> None:
        self._activator = activator or NativeApplicationActivator()

    def launch(self, app_id: str, arguments: str = "") -> int | None:
        normalized_app_id = app_id.strip()
        if not normalized_app_id or "!" not in normalized_app_id:
            raise ValueError("app_id 必须是有效的 Microsoft Store 应用标识")
        if len(arguments) > MAX_ACTIVATION_ARGUMENTS_LENGTH:
            raise ValueError("激活参数过长")
        return self._activator.activate(normalized_app_id, arguments)
