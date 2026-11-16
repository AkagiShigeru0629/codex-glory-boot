from dataclasses import replace

import pytest

from glory_boot.domain.models import AppConfig, Rect, ScreenFrame
from glory_boot.domain.timeline import transition_progress


@pytest.fixture
def config() -> AppConfig:
    return AppConfig(
        app_id="OpenAI.Codex_2p2nqsd0c76g0!App",
        process_names=("Codex.exe",),
        process_path_fragment="OpenAI.Codex_",
        video_path="startup.mp4",
        poster_path="poster.png",
        duration=8.0,
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
    assert transition_progress(config, media_seconds) == expected_progress


def test_timeline_follows_configured_cut_instead_of_fixed_eight_seconds(
    config: AppConfig,
) -> None:
    customized = replace(
        config,
        duration=10.0,
        transition_start=3.0,
        transition_end=4.0,
        max_wait_seconds=12.0,
    )

    assert transition_progress(customized, 2.999) == 0.0
    assert transition_progress(customized, 3.5) == 0.5
    assert transition_progress(customized, 4.0) == 1.0
