from dataclasses import replace

import pytest

from glory_boot.domain.models import AppConfig, Rect, ScreenFrame
from glory_boot.domain.timeline import (
    PlaybackAction,
    evaluate_timeline,
)


@pytest.fixture
def config() -> AppConfig:
    return AppConfig(
        app_id="OpenAI.Codex_2p2nqsd0c76g0!App",
        process_names=("Codex.exe",),
        process_path_fragment="OpenAI.Codex_",
        video_path="startup.mp4",
        poster_path="poster.png",
        duration=8.0,
        hold_at=6.4,
        transition_start=6.7,
        transition_end=7.6,
        max_wait_seconds=60.0,
        volume=0.35,
        screen_frames=(
            ScreenFrame(0.0, Rect(0.3, 0.2, 0.4, 0.6), 0.75),
            ScreenFrame(7.6, Rect(0.0, 0.0, 1.0, 1.0), 1.0),
        ),
    )


@pytest.mark.parametrize(
    ("media_seconds", "app_ready", "waited_seconds", "expected_action"),
    [
        (6.399, False, 0.0, PlaybackAction.CONTINUE),
        (6.4, False, 0.0, PlaybackAction.HOLD),
        (6.4, True, 0.0, PlaybackAction.CONTINUE),
        (6.4, True, 4.0, PlaybackAction.RESUME),
        (6.7, True, 0.0, PlaybackAction.CONTINUE),
        (7.6, True, 0.0, PlaybackAction.CONTINUE),
        (8.0, True, 0.0, PlaybackAction.CONTINUE),
        (6.4, False, 60.0, PlaybackAction.TIMEOUT),
    ],
)
def test_evaluate_timeline_actions(
    config: AppConfig,
    media_seconds: float,
    app_ready: bool,
    waited_seconds: float,
    expected_action: PlaybackAction,
) -> None:
    decision = evaluate_timeline(
        config,
        media_seconds=media_seconds,
        app_ready=app_ready,
        waited_seconds=waited_seconds,
    )

    assert decision.action == expected_action


@pytest.mark.parametrize(
    ("media_seconds", "expected_progress"),
    [
        (6.699, 0.0),
        (6.7, 0.0),
        (7.15, 0.5),
        (7.6, 1.0),
        (8.0, 1.0),
    ],
)
def test_transition_progress_is_normalized(
    config: AppConfig,
    media_seconds: float,
    expected_progress: float,
) -> None:
    decision = evaluate_timeline(
        config,
        media_seconds=media_seconds,
        app_ready=True,
        waited_seconds=0.0,
    )

    assert decision.transition_progress == expected_progress


def test_late_codex_holds_for_twelve_seconds_then_resumes_without_skipping(
    config: AppConfig,
) -> None:
    at_hold = evaluate_timeline(
        config,
        media_seconds=6.4,
        app_ready=False,
        waited_seconds=0.0,
    )
    after_twelve_seconds = evaluate_timeline(
        config,
        media_seconds=6.4,
        app_ready=False,
        waited_seconds=5.7,
    )
    when_ready = evaluate_timeline(
        config,
        media_seconds=6.4,
        app_ready=True,
        waited_seconds=5.7,
    )
    transition_started = evaluate_timeline(
        config,
        media_seconds=6.7,
        app_ready=True,
        waited_seconds=5.7,
    )
    transition_midpoint = evaluate_timeline(
        config,
        media_seconds=7.15,
        app_ready=True,
        waited_seconds=5.7,
    )

    assert at_hold.action == PlaybackAction.HOLD
    assert after_twelve_seconds.action == PlaybackAction.HOLD
    assert when_ready.action == PlaybackAction.RESUME
    assert when_ready.transition_progress == 0.0
    assert transition_started.action == PlaybackAction.CONTINUE
    assert transition_started.transition_progress == 0.0
    assert transition_midpoint.transition_progress == 0.5


def test_evaluate_timeline_rejects_negative_wait(config: AppConfig) -> None:
    with pytest.raises(ValueError, match="waited_seconds"):
        evaluate_timeline(
            config,
            media_seconds=6.4,
            app_ready=False,
            waited_seconds=-0.1,
        )


def test_timeline_follows_configured_cut_instead_of_fixed_eight_seconds(
    config: AppConfig,
) -> None:
    customized = replace(
        config,
        duration=10.0,
        hold_at=2.0,
        transition_start=3.0,
        transition_end=4.0,
        max_wait_seconds=12.0,
    )

    assert evaluate_timeline(
        customized,
        media_seconds=1.999,
        app_ready=False,
        waited_seconds=0.0,
    ).action == PlaybackAction.CONTINUE
    assert evaluate_timeline(
        customized,
        media_seconds=2.0,
        app_ready=False,
        waited_seconds=0.0,
    ).action == PlaybackAction.HOLD
    assert evaluate_timeline(
        customized,
        media_seconds=3.5,
        app_ready=True,
        waited_seconds=0.0,
    ).transition_progress == 0.5
    assert evaluate_timeline(
        customized,
        media_seconds=4.0,
        app_ready=True,
        waited_seconds=0.0,
    ).transition_progress == 1.0
