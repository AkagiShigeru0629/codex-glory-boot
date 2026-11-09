import subprocess
import tomllib
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "relative_path",
    [
        ".venv/",
        ".reference/",
        "assets/local/",
        "build/",
        "dist/",
        "logs/",
        ".pytest_cache/",
        "__pycache__/",
        ".superpowers/",
    ],
)
def test_generated_and_private_directories_are_ignored(
    relative_path: str,
) -> None:
    result = subprocess.run(
        ["git", "check-ignore", "--quiet", relative_path],
        cwd=ROOT,
        check=False,
    )

    assert result.returncode == 0, f"{relative_path} 没有被 Git 忽略"


def test_required_project_metadata_exists() -> None:
    for relative_path in (
        "pyproject.toml",
        "README.md",
        "THIRD_PARTY_NOTICES.md",
        "scripts/bootstrap.ps1",
        "scripts/test.ps1",
        "src/glory_boot/__init__.py",
    ):
        assert (ROOT / relative_path).is_file(), f"缺少 {relative_path}"


def test_project_pins_python_and_install_dependencies() -> None:
    pyproject_path = ROOT / "pyproject.toml"
    assert pyproject_path.is_file()

    pyproject = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    project = pyproject["project"]

    assert project["requires-python"] == ">=3.14,<3.15"
    assert project["dependencies"] == ["PySide6==6.12.0"]
    assert project["optional-dependencies"]["dev"] == [
        "pytest==9.2.0",
        "PyInstaller==6.22.3",
        "Pillow==13.0.0",
        "NumPy==2.5.4",
        "imageio-ffmpeg==0.8.1",
    ]


def test_third_party_license_declarations_are_present() -> None:
    notices_path = ROOT / "THIRD_PARTY_NOTICES.md"
    assert notices_path.is_file()

    notices = notices_path.read_text(encoding="utf-8")
    for required_name in (
        "PySide6",
        "PyInstaller",
        "Pillow",
        "NumPy",
        "imageio-ffmpeg",
        "dragon-codex-boot",
    ):
        assert required_name in notices
