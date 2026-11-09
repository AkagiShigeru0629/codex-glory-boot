import re
from collections.abc import Callable
from datetime import date, timedelta
from pathlib import Path


PRIMARY_MOUNT_PATTERN = re.compile(
    r"\[startup\]\[renderer\] app routes mounted"
    r"[^\r\n]*rendererWindowAppearance=primary"
)


class CodexReadinessProbe:
    """只识别 Codex 主界面挂载完成的结构化日志标记。"""

    def __init__(
        self,
        log_root: Path,
        *,
        launched_at: float,
        today: Callable[[], date] = date.today,
    ) -> None:
        self._log_root = log_root
        self._launched_at = launched_at
        self._today = today

    def is_primary_mounted(self) -> bool:
        current = self._today()
        for day in (current, current - timedelta(days=1)):
            folder = (
                self._log_root
                / f"{day.year:04d}"
                / f"{day.month:02d}"
                / f"{day.day:02d}"
            )
            if not folder.is_dir():
                continue
            for path in folder.glob("*.log"):
                try:
                    if path.stat().st_mtime + 1.0 < self._launched_at:
                        continue
                    text = path.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                if PRIMARY_MOUNT_PATTERN.search(text):
                    return True
        return False
