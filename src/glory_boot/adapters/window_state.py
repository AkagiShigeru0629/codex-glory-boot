import json
import math
import os
from pathlib import Path
from typing import Any, NoReturn

from glory_boot.domain.models import Rect


MIN_WINDOW_WIDTH = 450
MIN_WINDOW_HEIGHT = 280


def _reject_constant(value: str) -> NoReturn:
    raise ValueError(f"非有限数值: {value}")


def _finite_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


class WindowStateStore:
    """在本地保存最近一次成功交接的 Codex 整窗外框。"""

    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> Rect | None:
        try:
            raw: Any = json.loads(
                self._path.read_text(encoding="utf-8"),
                parse_constant=_reject_constant,
            )
        except (OSError, ValueError, TypeError):
            return None
        if not isinstance(raw, dict):
            return None

        x = _finite_number(raw.get("x"))
        y = _finite_number(raw.get("y"))
        width = _finite_number(raw.get("width"))
        height = _finite_number(raw.get("height"))
        if None in (x, y, width, height):
            return None
        assert x is not None
        assert y is not None
        assert width is not None
        assert height is not None
        if width < MIN_WINDOW_WIDTH or height < MIN_WINDOW_HEIGHT:
            return None
        return Rect(x=x, y=y, width=width, height=height)

    def save(self, rect: Rect) -> None:
        values = (rect.x, rect.y, rect.width, rect.height)
        if not all(math.isfinite(value) for value in values):
            raise ValueError("窗口矩形必须是有限数值")
        if rect.width < MIN_WINDOW_WIDTH or rect.height < MIN_WINDOW_HEIGHT:
            raise ValueError("窗口矩形小于 Codex 最小客户区")

        self._path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._path.with_name(f"{self._path.name}.tmp")
        try:
            temporary.write_text(
                json.dumps(
                    {
                        "x": rect.x,
                        "y": rect.y,
                        "width": rect.width,
                        "height": rect.height,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            os.replace(temporary, self._path)
        finally:
            if temporary.exists():
                temporary.unlink()
