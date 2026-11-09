from dataclasses import dataclass
from enum import StrEnum

from glory_boot.domain.models import AppConfig


class PlaybackAction(StrEnum):
    CONTINUE = "continue"
    HOLD = "hold"
    RESUME = "resume"
    TIMEOUT = "timeout"


@dataclass(frozen=True, slots=True)
class TimelineDecision:
    action: PlaybackAction
    transition_progress: float


def _transition_progress(config: AppConfig, media_seconds: float) -> float:
    if media_seconds <= config.transition_start:
        return 0.0
    if media_seconds >= config.transition_end:
        return 1.0
    progress = (media_seconds - config.transition_start) / (
        config.transition_end - config.transition_start
    )
    return round(progress, 9)


def evaluate_timeline(
    config: AppConfig,
    media_seconds: float,
    app_ready: bool,
    waited_seconds: float,
) -> TimelineDecision:
    """根据媒体时间、窗口状态和累计等待时间作出确定决策。"""
    if waited_seconds < 0:
        raise ValueError("waited_seconds 不能为负数")

    progress = _transition_progress(config, media_seconds)
    if waited_seconds >= config.max_wait_seconds and not app_ready:
        return TimelineDecision(PlaybackAction.TIMEOUT, progress)
    if media_seconds >= config.hold_at and not app_ready:
        return TimelineDecision(PlaybackAction.HOLD, progress)
    if media_seconds == config.hold_at and app_ready and waited_seconds > 0:
        return TimelineDecision(PlaybackAction.RESUME, progress)
    return TimelineDecision(PlaybackAction.CONTINUE, progress)
