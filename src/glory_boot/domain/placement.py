import math

from glory_boot.domain.geometry import centered
from glory_boot.domain.models import Rect


def default_launcher_rect(
    work_area: Rect,
    *,
    coverage: float = 0.7,
    aspect_width: int = 1920,
    aspect_height: int = 1080,
) -> Rect:
    """在显示器工作区内生成以 16:9 内容为中心的安全默认窗口。"""
    if (
        work_area.width <= 0
        or work_area.height <= 0
        or not math.isfinite(work_area.width)
        or not math.isfinite(work_area.height)
    ):
        raise ValueError("work_area 必须具有有限正尺寸")
    if not math.isfinite(coverage) or not 0 < coverage < 1:
        raise ValueError("coverage 必须位于 0 到 1 之间")
    if aspect_width <= 0 or aspect_height <= 0:
        raise ValueError("内容宽高必须为正数")

    margin_x = work_area.width * (1 - coverage) / 2
    margin_y = work_area.height * (1 - coverage) / 2
    usable = Rect(
        x=work_area.x + margin_x,
        y=work_area.y + margin_y,
        width=work_area.width * coverage,
        height=work_area.height * coverage,
    )
    return centered(usable, aspect_width, aspect_height)


def is_rect_visible(
    rect: Rect,
    monitors: tuple[Rect, ...],
    *,
    minimum_width: int = 64,
    minimum_height: int = 64,
) -> bool:
    """判断窗口是否至少有一部分落在某个显示器内。"""
    if minimum_width <= 0 or minimum_height <= 0:
        raise ValueError("最小可见宽高必须为正数")
    values = (rect.x, rect.y, rect.width, rect.height)
    if not all(math.isfinite(value) for value in values):
        return False
    if rect.width <= 0 or rect.height <= 0:
        return False

    for monitor in monitors:
        intersection_width = min(rect.right, monitor.right) - max(
            rect.x,
            monitor.x,
        )
        intersection_height = min(rect.bottom, monitor.bottom) - max(
            rect.y,
            monitor.y,
        )
        if (
            intersection_width >= minimum_width
            and intersection_height >= minimum_height
        ):
            return True
    return False
