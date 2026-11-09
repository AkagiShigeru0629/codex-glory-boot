import pytest

from glory_boot.adapters.app_activation import ApplicationActivationBackend


class FakeActivator:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def activate(self, app_id: str, arguments: str) -> int:
        self.calls.append((app_id, arguments))
        return 9876


def test_backend_delegates_arguments_and_returns_process_id() -> None:
    activator = FakeActivator()
    backend = ApplicationActivationBackend(activator=activator)

    result = backend.launch(
        "OpenAI.Codex_2p2nqsd0c76g0!App",
        "--remote-debugging-port=50123",
    )

    assert result == 9876
    assert activator.calls == [
        (
            "OpenAI.Codex_2p2nqsd0c76g0!App",
            "--remote-debugging-port=50123",
        )
    ]


def test_backend_rejects_empty_app_id_and_overlong_arguments() -> None:
    backend = ApplicationActivationBackend(activator=FakeActivator())

    with pytest.raises(ValueError):
        backend.launch("", "")
    with pytest.raises(ValueError):
        backend.launch("OpenAI.Codex_x!App", "x" * 4097)
