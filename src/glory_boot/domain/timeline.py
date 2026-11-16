from glory_boot.domain.models import AppConfig


def transition_progress(config: AppConfig, media_seconds: float) -> float:
    if media_seconds <= config.transition_start:
        return 0.0
    if media_seconds >= config.transition_end:
        return 1.0
    progress = (media_seconds - config.transition_start) / (
        config.transition_end - config.transition_start
    )
    return round(progress, 9)
