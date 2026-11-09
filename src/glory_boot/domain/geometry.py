import math

from glory_boot.domain.models import Rect, ScreenFrame


def physical_pixels(logical_pixels: float, dpi: int) -> int:
    """把逻辑像素换算为物理像素，并采用 Qt 常用的四舍五入规则。"""
    if logical_pixels < 0 or dpi <= 0:
        raise ValueError("逻辑像素和 DPI 必须为正数")
    return math.floor(logical_pixels * dpi / 96 + 0.5)


def centered(
    viewport: Rect,
    source_width: int,
    source_height: int,
) -> Rect:
    """按原始宽高比在视口中居中并最大化内容。"""
    if viewport.width <= 0 or viewport.height <= 0:
        raise ValueError("视口尺寸必须为正数")
    if source_width <= 0 or source_height <= 0:
        raise ValueError("源尺寸必须为正数")

    scale = min(viewport.width / source_width, viewport.height / source_height)
    width = source_width * scale
    height = source_height * scale
    return Rect(
        x=viewport.x + (viewport.width - width) / 2,
        y=viewport.y + (viewport.height - height) / 2,
        width=width,
        height=height,
    )


def window_for_client(
    client: Rect,
    *,
    border_x: int,
    border_y: int,
    title_bar_height: int,
) -> Rect:
    """把客户区矩形换算为包含边框和标题栏的窗口矩形。"""
    if border_x < 0 or border_y < 0 or title_bar_height < 0:
        raise ValueError("窗口边距不能为负数")
    return Rect(
        x=client.x - border_x,
        y=client.y - title_bar_height,
        width=client.width + border_x * 2,
        height=client.height + title_bar_height + border_y,
    )


def destination_at(
    frames: tuple[ScreenFrame, ...],
    seconds: float,
    viewport: Rect,
) -> Rect:
    """在相邻规范化关键帧之间线性插值出物理像素矩形。"""
    if not frames:
        raise ValueError("至少需要一个屏幕关键帧")
    if viewport.width <= 0 or viewport.height <= 0:
        raise ValueError("视口尺寸必须为正数")

    clamped_seconds = min(max(seconds, frames[0].time), frames[-1].time)
    previous = frames[0]
    following = frames[-1]

    for index in range(1, len(frames)):
        if clamped_seconds <= frames[index].time:
            previous = frames[index - 1]
            following = frames[index]
            break

    if following.time == previous.time or clamped_seconds <= previous.time:
        normalized = previous.rect
    elif clamped_seconds >= following.time:
        normalized = following.rect
    else:
        progress = (clamped_seconds - previous.time) / (
            following.time - previous.time
        )
        normalized = Rect(
            x=previous.rect.x
            + (following.rect.x - previous.rect.x) * progress,
            y=previous.rect.y
            + (following.rect.y - previous.rect.y) * progress,
            width=previous.rect.width
            + (following.rect.width - previous.rect.width) * progress,
            height=previous.rect.height
            + (following.rect.height - previous.rect.height) * progress,
        )

    return Rect(
        x=viewport.x + normalized.x * viewport.width,
        y=viewport.y + normalized.y * viewport.height,
        width=normalized.width * viewport.width,
        height=normalized.height * viewport.height,
    )
