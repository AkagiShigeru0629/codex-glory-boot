import pytest

from glory_boot.domain.skin import (
    SkinProfile,
    package_version_from_path,
    select_skin_profile,
)


def test_package_version_is_read_from_store_path() -> None:
    path = (
        r"C:\Program Files\WindowsApps"
        r"\OpenAI.Codex_26.924.22138.0_x64__x\ChatGPT.exe"
    )

    assert package_version_from_path(path) == "26.924.22138.0"


@pytest.mark.parametrize(
    "path",
    [
        "",
        r"C:\Apps\OpenAI.Codex_x64__x\ChatGPT.exe",
        r"C:\Apps\OpenAI.Codex_26.924_x64__x\ChatGPT.exe",
        r"C:\Apps\Other_26.924.22138.0_x64__x\ChatGPT.exe",
    ],
)
def test_invalid_package_path_returns_no_version(path: str) -> None:
    assert package_version_from_path(path) is None


def test_exact_version_selects_registered_profile() -> None:
    profile = SkinProfile(
        "26.924.22138.0",
        ("#root",),
        ("--color-surface",),
    )

    assert select_skin_profile((profile,), "26.924.22138.0") == profile


def test_registered_same_major_series_selects_profile() -> None:
    profile = SkinProfile(
        "26.*",
        ("#root", "body"),
        ("--color-surface",),
    )

    assert select_skin_profile((profile,), "26.1111.2228.0") == profile
    assert select_skin_profile((profile,), "27.1.0.0") is None


def test_exact_profile_has_priority_over_series_profile() -> None:
    series = SkinProfile(
        "26.*",
        ("#root",),
        ("--color-surface",),
    )
    exact = SkinProfile(
        "26.1111.2228.0",
        ("#root", "body"),
        ("--color-surface",),
    )

    assert select_skin_profile((series, exact), "26.1111.2228.0") == exact


def test_unknown_or_missing_version_is_not_selected() -> None:
    profile = SkinProfile(
        "26.924.22138.0",
        ("#root",),
        ("--color-surface",),
    )

    assert select_skin_profile((profile,), "27.0.0.0") is None
    assert select_skin_profile((profile,), None) is None
    assert select_skin_profile((), "26.924.22138.0") is None
