import ctypes
import logging
import time
from ctypes import wintypes


class StageTimer:
    def __init__(
        self,
        *,
        start: float | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._start = time.perf_counter() if start is None else start
        self._logger = logger or logging.getLogger("glory_boot.stage")
        self.marks: dict[str, float] = {}

    def mark(self, name: str) -> float:
        elapsed_ms = (time.perf_counter() - self._start) * 1000
        self.marks[name] = elapsed_ms
        self._logger.info(
            "stage=%s elapsed_ms=%.1f",
            name,
            elapsed_ms,
        )
        return elapsed_ms


class SingleInstanceGuard:
    def __init__(self, name: str = "Local\\GloryCodexBoot") -> None:
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._kernel32.CreateMutexW.argtypes = [
            ctypes.c_void_p,
            wintypes.BOOL,
            wintypes.LPCWSTR,
        ]
        self._kernel32.CreateMutexW.restype = wintypes.HANDLE
        self._kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        self._kernel32.CloseHandle.restype = wintypes.BOOL
        self._handle = self._kernel32.CreateMutexW(None, False, name)
        if not self._handle:
            raise OSError(ctypes.get_last_error(), "创建单实例互斥量失败")
        self.already_running = ctypes.get_last_error() == 183

    def close(self) -> None:
        if self._handle:
            self._kernel32.CloseHandle(self._handle)
            self._handle = None

    def __enter__(self) -> "SingleInstanceGuard":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()
