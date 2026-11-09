from dataclasses import dataclass
from enum import StrEnum


class HandoffReason(StrEnum):
    COMPLETED = "completed"
    SKIPPED = "skipped"
    MEDIA_FAILED = "media_failed"
    DWM_UNAVAILABLE = "dwm_unavailable"
    TIMEOUT = "timeout"
    ACTIVATION_FAILED = "activation_failed"


@dataclass(frozen=True, slots=True)
class HandoffDecision:
    reveal_existing_window: bool
    show_error: bool
    exit_launcher: bool


class HandoffPolicy:
    """把统一交接原因映射为界面可执行的简单决策。"""

    def decide(
        self,
        reason: HandoffReason,
        *,
        window_available: bool = False,
    ) -> HandoffDecision:
        if reason is HandoffReason.ACTIVATION_FAILED:
            return HandoffDecision(
                reveal_existing_window=False,
                show_error=True,
                exit_launcher=True,
            )

        if reason is HandoffReason.SKIPPED and not window_available:
            return HandoffDecision(
                reveal_existing_window=False,
                show_error=False,
                exit_launcher=True,
            )

        if reason in {
            HandoffReason.COMPLETED,
            HandoffReason.SKIPPED,
            HandoffReason.MEDIA_FAILED,
            HandoffReason.DWM_UNAVAILABLE,
            HandoffReason.TIMEOUT,
        }:
            return HandoffDecision(
                reveal_existing_window=window_available,
                show_error=not window_available,
                exit_launcher=True,
            )

        raise ValueError(f"未知交接原因: {reason!r}")
