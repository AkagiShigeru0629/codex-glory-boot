import json
from pathlib import Path

import pytest

from glory_boot.adapters.codex_runtime import CodexRuntimeStore
from glory_boot.adapters.skin_profiles import (
    load_skin_profiles,
    parse_skin_profiles,
)
from glory_boot.domain.skin import SkinProfile


def _store_executable(root: Path, version: str) -> Path:
    path = (
        root
        / f"OpenAI.Codex_{version}_x64__2p2nqsd0c76g0"
        / "app"
        / "ChatGPT.exe"
    )
    path.parent.mkdir(parents=True)
    path.write_bytes(b"MZ")
    return path


def test_parse_skin_profiles_accepts_registered_capabilities() -> None:
    result = parse_skin_profiles(
        {
            "profiles": [
                {
                    "package_version": "26.1103.4239.0",
                    "required_selectors": ["#root"],
                    "required_tokens": ["--color-surface"],
                }
            ]
        }
    )

    assert result == (
        SkinProfile(
            "26.1103.4239.0",
            ("#root",),
            ("--color-surface",),
        ),
    )


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {},
        {"profiles": "invalid"},
        {
            "profiles": [
                {
                    "package_version": "",
                    "required_selectors": ["#root"],
                    "required_tokens": ["--color-surface"],
                }
            ]
        },
        {
            "profiles": [
                {
                    "package_version": "26.1103.4239.0",
                    "required_selectors": [],
                    "required_tokens": ["--color-surface"],
                }
            ]
        },
    ],
)
def test_parse_skin_profiles_rejects_invalid_shapes(payload: object) -> None:
    with pytest.raises(ValueError):
        parse_skin_profiles(payload)


def test_bundled_profile_file_is_safe_by_default() -> None:
    assert load_skin_profiles() == ()


def test_runtime_store_round_trip_checks_executable_exists(
    tmp_path: Path,
) -> None:
    executable = _store_executable(tmp_path, "26.1103.4239.0")
    store = CodexRuntimeStore(tmp_path / "state" / "codex-runtime.json")

    assert store.save(str(executable)) is True
    install = store.load()

    assert install is not None
    assert install.version == "26.1103.4239.0"
    assert install.executable_path == str(executable.resolve())


def test_runtime_store_rejects_missing_or_invalid_path(tmp_path: Path) -> None:
    store = CodexRuntimeStore(tmp_path / "codex-runtime.json")
    executable = _store_executable(tmp_path, "26.1103.4239.0")
    assert store.save(str(executable)) is True
    executable.unlink()

    assert store.load() is None
    assert store.save(str(tmp_path / "plain" / "ChatGPT.exe")) is False


def test_runtime_store_ignores_corrupt_json(tmp_path: Path) -> None:
    path = tmp_path / "codex-runtime.json"
    path.write_text("{", encoding="utf-8")

    assert CodexRuntimeStore(path).load() is None


def test_runtime_state_schema_does_not_include_user_content(
    tmp_path: Path,
) -> None:
    executable = _store_executable(tmp_path, "26.1103.4239.0")
    path = tmp_path / "codex-runtime.json"
    store = CodexRuntimeStore(path)
    store.save(str(executable))

    payload = json.loads(path.read_text(encoding="utf-8"))

    assert set(payload) == {"version", "executable_path"}
