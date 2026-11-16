import json
from pathlib import Path

import pytest
from PIL import Image

from glory_boot.adapters.codex_runtime import (
    CodexRuntimeStore,
    latest_installed_codex_runtime,
    refresh_runtime_store,
)
from glory_boot.adapters.skin_profiles import (
    load_skin_profiles,
    parse_skin_profiles,
)
from glory_boot.domain.skin import SkinProfile, select_skin_profile


ROOT = Path(__file__).resolve().parents[1]


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


def test_bundled_profile_registers_verified_candidate_version() -> None:
    profiles = load_skin_profiles()

    assert select_skin_profile(profiles, "26.1111.2228.0") == SkinProfile(
        "26.1111.2228.0",
        ("#root", "body", '[class*="ComposerLayoutRoot-"]'),
        ("--color-surface",),
    )
    assert select_skin_profile(profiles, "26.1112.1.0") == SkinProfile(
        "26.*",
        ("#root", "body", '[class*="ComposerLayoutRoot-"]'),
        ("--color-surface",),
    )


def test_latest_installed_runtime_prefers_newest_package(
    tmp_path: Path,
) -> None:
    old = _store_executable(tmp_path, "26.1103.4239.0")
    current = _store_executable(tmp_path, "26.1106.6628.0")

    result = latest_installed_codex_runtime(
        (old.parent.parent, current.parent.parent)
    )

    assert result is not None
    assert result.version == "26.1106.6628.0"
    assert result.executable_path == str(current.resolve())


def test_refresh_runtime_store_replaces_stale_install_record(
    tmp_path: Path,
) -> None:
    old = _store_executable(tmp_path / "packages", "26.1103.4239.0")
    current = _store_executable(
        tmp_path / "packages",
        "26.1106.6628.0",
    )
    store = CodexRuntimeStore(tmp_path / "state" / "codex-runtime.json")
    assert store.save(str(old)) is True

    refreshed = refresh_runtime_store(
        store,
        (old.parent.parent, current.parent.parent),
    )

    assert refreshed is not None
    assert refreshed.version == "26.1106.6628.0"
    assert store.load() == refreshed


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


def test_runtime_store_falls_back_when_atomic_replace_crosses_volume(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executable = _store_executable(tmp_path, "26.1106.6628.0")
    store = CodexRuntimeStore(tmp_path / "state" / "codex-runtime.json")

    def reject_replace(_source: object, _destination: object) -> None:
        raise OSError(17, "跨卷移动")

    monkeypatch.setattr("os.replace", reject_replace)

    assert store.save(str(executable)) is True
    install = store.load()
    assert install is not None
    assert install.version == "26.1106.6628.0"


def test_runtime_store_ignores_corrupt_json(tmp_path: Path) -> None:
    path = tmp_path / "codex-runtime.json"
    path.write_text("{", encoding="utf-8")

    assert CodexRuntimeStore(path).load() is None


def test_runtime_store_accepts_windows_powershell_utf8_bom(
    tmp_path: Path,
) -> None:
    executable = _store_executable(tmp_path, "26.1103.4239.0")
    path = tmp_path / "codex-runtime.json"
    path.write_text(
        json.dumps(
            {
                "version": "26.1103.4239.0",
                "executable_path": str(executable.resolve()),
            }
        ),
        encoding="utf-8-sig",
    )

    install = CodexRuntimeStore(path).load()

    assert install is not None
    assert install.version == "26.1103.4239.0"


def test_runtime_state_schema_does_not_include_user_content(
    tmp_path: Path,
) -> None:
    executable = _store_executable(tmp_path, "26.1103.4239.0")
    path = tmp_path / "codex-runtime.json"
    store = CodexRuntimeStore(path)
    store.save(str(executable))

    payload = json.loads(path.read_text(encoding="utf-8"))

    assert set(payload) == {"version", "executable_path"}


def test_default_wallpaper_uses_selected_local_artwork() -> None:
    wallpaper = ROOT / "media" / "wallpaper.jpg"

    with Image.open(wallpaper) as image:
        assert image.format == "JPEG"
        assert image.mode == "RGB"
        assert image.size == (655, 469)
