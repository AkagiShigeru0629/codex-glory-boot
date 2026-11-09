import pytest

from glory_boot.domain.policy import (
    HandoffPolicy,
    HandoffReason,
)


@pytest.mark.parametrize(
    "reason",
    [HandoffReason.COMPLETED, HandoffReason.SKIPPED],
)
def test_normal_completion_and_skip_reveal_codex(
    reason: HandoffReason,
) -> None:
    decision = HandoffPolicy().decide(reason, window_available=True)

    assert decision.reveal_existing_window is True
    assert decision.show_error is False
    assert decision.exit_launcher is True


@pytest.mark.parametrize(
    "reason",
    [HandoffReason.MEDIA_FAILED, HandoffReason.DWM_UNAVAILABLE],
)
def test_safe_failure_hands_off_to_available_codex(
    reason: HandoffReason,
) -> None:
    decision = HandoffPolicy().decide(reason, window_available=True)

    assert decision.reveal_existing_window is True
    assert decision.show_error is False
    assert decision.exit_launcher is True


@pytest.mark.parametrize(
    "reason",
    [HandoffReason.MEDIA_FAILED, HandoffReason.DWM_UNAVAILABLE],
)
def test_safe_failure_reports_when_codex_is_not_available(
    reason: HandoffReason,
) -> None:
    decision = HandoffPolicy().decide(reason, window_available=False)

    assert decision.reveal_existing_window is False
    assert decision.show_error is True
    assert decision.exit_launcher is True


@pytest.mark.parametrize(
    ("window_available", "expected_reveal", "expected_error"),
    [
        (True, True, False),
        (False, False, True),
    ],
)
def test_timeout_depends_on_window_availability(
    window_available: bool,
    expected_reveal: bool,
    expected_error: bool,
) -> None:
    decision = HandoffPolicy().decide(
        HandoffReason.TIMEOUT,
        window_available=window_available,
    )

    assert decision.reveal_existing_window is expected_reveal
    assert decision.show_error is expected_error
    assert decision.exit_launcher is True


def test_activation_failure_reports_error_and_exits() -> None:
    decision = HandoffPolicy().decide(
        HandoffReason.ACTIVATION_FAILED,
        window_available=True,
    )

    assert decision.reveal_existing_window is False
    assert decision.show_error is True
    assert decision.exit_launcher is True
