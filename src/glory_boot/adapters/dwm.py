import ctypes
from ctypes import wintypes
from typing import Protocol

from glory_boot.adapters.win32 import RECT
from glory_boot.domain.models import Rect


DWM_TNP_RECTDESTINATION = 0x00000001
DWM_TNP_OPACITY = 0x00000004
DWM_TNP_VISIBLE = 0x00000008
DWM_TNP_SOURCECLIENTAREAONLY = 0x00000010


class DWM_THUMBNAIL_PROPERTIES(ctypes.Structure):
    _fields_ = [
        ("dwFlags", wintypes.DWORD),
        ("rcDestination", RECT),
        ("rcSource", RECT),
        ("opacity", wintypes.BYTE),
        ("fVisible", wintypes.BOOL),
        ("fSourceClientAreaOnly", wintypes.BOOL),
    ]


_dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)
_dwmapi.DwmRegisterThumbnail.argtypes = [
    wintypes.HWND,
    wintypes.HWND,
    ctypes.POINTER(wintypes.HANDLE),
]
_dwmapi.DwmRegisterThumbnail.restype = ctypes.c_long
_dwmapi.DwmUpdateThumbnailProperties.argtypes = [
    wintypes.HANDLE,
    ctypes.POINTER(DWM_THUMBNAIL_PROPERTIES),
]
_dwmapi.DwmUpdateThumbnailProperties.restype = ctypes.c_long
_dwmapi.DwmUnregisterThumbnail.argtypes = [wintypes.HANDLE]
_dwmapi.DwmUnregisterThumbnail.restype = ctypes.c_long


class DwmError(OSError):
    """桌面窗口管理器缩略图调用失败。"""


class DwmBackend(Protocol):
    def register_thumbnail(self, destination_hwnd: int, source_hwnd: int) -> int:
        ...

    def update_thumbnail(
        self,
        thumbnail: int,
        destination: Rect,
        opacity: int,
        visible: bool,
    ) -> None:
        ...

    def unregister_thumbnail(self, thumbnail: int) -> None:
        ...


class NativeDwmBackend:
    def register_thumbnail(self, destination_hwnd: int, source_hwnd: int) -> int:
        handle = wintypes.HANDLE()
        result = _dwmapi.DwmRegisterThumbnail(
            destination_hwnd,
            source_hwnd,
            ctypes.byref(handle),
        )
        if result != 0:
            raise DwmError(f"DwmRegisterThumbnail 失败: 0x{result & 0xFFFFFFFF:08X}")
        return int(handle.value)

    def update_thumbnail(
        self,
        thumbnail: int,
        destination: Rect,
        opacity: int,
        visible: bool,
    ) -> None:
        properties = DWM_THUMBNAIL_PROPERTIES(
            dwFlags=(
                DWM_TNP_RECTDESTINATION
                | DWM_TNP_OPACITY
                | DWM_TNP_VISIBLE
                | DWM_TNP_SOURCECLIENTAREAONLY
            ),
            rcDestination=RECT(
                int(round(destination.x)),
                int(round(destination.y)),
                int(round(destination.right)),
                int(round(destination.bottom)),
            ),
            rcSource=RECT(),
            opacity=opacity,
            fVisible=visible,
            fSourceClientAreaOnly=False,
        )
        result = _dwmapi.DwmUpdateThumbnailProperties(
            thumbnail,
            ctypes.byref(properties),
        )
        if result != 0:
            raise DwmError(
                f"DwmUpdateThumbnailProperties 失败: 0x{result & 0xFFFFFFFF:08X}"
            )

    def unregister_thumbnail(self, thumbnail: int) -> None:
        result = _dwmapi.DwmUnregisterThumbnail(thumbnail)
        if result != 0:
            raise DwmError(
                f"DwmUnregisterThumbnail 失败: 0x{result & 0xFFFFFFFF:08X}"
            )


class DwmController:
    def __init__(
        self,
        *,
        destination_hwnd: int,
        backend: DwmBackend | None = None,
    ) -> None:
        self._destination_hwnd = destination_hwnd
        self._backend = backend or NativeDwmBackend()
        self._thumbnail: int | None = None

    def register(self, source_hwnd: int) -> None:
        if self._thumbnail is not None:
            return
        if source_hwnd <= 0:
            raise ValueError("source_hwnd 必须是有效窗口句柄")
        self._thumbnail = self._backend.register_thumbnail(
            self._destination_hwnd,
            source_hwnd,
        )

    def update(
        self,
        destination: Rect,
        opacity: float,
        visible: bool,
    ) -> None:
        if self._thumbnail is None:
            raise RuntimeError("DWM 缩略图尚未注册")
        if not 0 <= opacity <= 1:
            raise ValueError("opacity 必须位于 0 到 1 之间")
        opacity_byte = int(opacity * 255 + 0.5)
        self._backend.update_thumbnail(
            self._thumbnail,
            destination,
            opacity_byte,
            visible,
        )

    def close(self) -> None:
        thumbnail = self._thumbnail
        if thumbnail is None:
            return
        self._thumbnail = None
        self._backend.unregister_thumbnail(thumbnail)
