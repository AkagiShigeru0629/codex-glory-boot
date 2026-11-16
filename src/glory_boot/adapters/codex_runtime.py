import json
import os
import winreg
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn

from glory_boot.domain.skin import package_version_from_path


_PACKAGES_KEY = (
    r"Software\Classes\Local Settings\Software\Microsoft"
    r"\Windows\CurrentVersion\AppModel\Repository\Packages"
)
_EXECUTABLE_NAMES = ("ChatGPT.exe", "Codex.exe")


def _reject_constant(value: str) -> NoReturn:
    raise ValueError(f"非有限数值: {value}")


@dataclass(frozen=True, slots=True)
class CodexRuntimeInstall:
    version: str
    executable_path: str


def _version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def _runtime_from_package_root(
    package_root: str | Path,
) -> CodexRuntimeInstall | None:
    root = Path(package_root)
    version = package_version_from_path(str(root))
    if version is None:
        return None
    for executable_name in _EXECUTABLE_NAMES:
        executable = root / "app" / executable_name
        if executable.is_file():
            return CodexRuntimeInstall(version, str(executable.resolve()))
    return None


def _registered_package_roots() -> tuple[str, ...]:
    roots: list[str] = []
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _PACKAGES_KEY) as key:
            index = 0
            while True:
                try:
                    package_name = winreg.EnumKey(key, index)
                except OSError:
                    break
                index += 1
                if not package_name.startswith("OpenAI.Codex_"):
                    continue
                try:
                    with winreg.OpenKey(key, package_name) as package:
                        root, value_type = winreg.QueryValueEx(
                            package,
                            "PackageRootFolder",
                        )
                except OSError:
                    continue
                if value_type == winreg.REG_SZ and isinstance(root, str):
                    roots.append(root)
    except OSError:
        return ()
    return tuple(roots)


def latest_installed_codex_runtime(
    package_roots: Iterable[str | Path] | None = None,
) -> CodexRuntimeInstall | None:
    """从当前用户包注册信息选择版本最高的 Store 版 Codex。"""
    roots = (
        tuple(package_roots)
        if package_roots is not None
        else _registered_package_roots()
    )
    candidates = [
        install
        for root in roots
        if (install := _runtime_from_package_root(root)) is not None
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda install: _version_key(install.version))


class CodexRuntimeStore:
    """保存已观察到的 Store 版 Codex 可执行文件路径。"""

    def __init__(self, path: Path) -> None:
        self._path = path

    def save(self, executable_path: str) -> bool:
        path = Path(executable_path).resolve()
        if not path.is_file():
            return False
        version = package_version_from_path(str(path))
        if version is None:
            return False

        payload = json.dumps(
            {
                "version": version,
                "executable_path": str(path),
            },
            ensure_ascii=False,
            indent=2,
        )
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self._path.with_name(f"{self._path.name}.tmp")
            temporary.write_text(
                payload,
                encoding="utf-8",
            )
            try:
                os.replace(temporary, self._path)
            except OSError as exc:
                error_code = getattr(exc, "winerror", None) or exc.errno
                if error_code not in {17, 18}:
                    raise
                self._path.write_text(payload, encoding="utf-8")
        except OSError:
            return False
        finally:
            temporary = self._path.with_name(f"{self._path.name}.tmp")
            if temporary.exists():
                temporary.unlink(missing_ok=True)
        return True

    def load(self) -> CodexRuntimeInstall | None:
        try:
            raw: Any = json.loads(
                self._path.read_text(encoding="utf-8-sig"),
                parse_constant=_reject_constant,
            )
        except (OSError, ValueError, TypeError):
            return None
        if not isinstance(raw, dict):
            return None

        version = raw.get("version")
        executable_path = raw.get("executable_path")
        if not isinstance(version, str) or not isinstance(executable_path, str):
            return None
        path = Path(executable_path)
        if (
            not version
            or not path.is_absolute()
            or not path.is_file()
            or package_version_from_path(str(path)) != version
        ):
            return None
        return CodexRuntimeInstall(version=version, executable_path=str(path))


def refresh_runtime_store(
    store: CodexRuntimeStore,
    package_roots: Iterable[str | Path] | None = None,
) -> CodexRuntimeInstall | None:
    """优先使用已安装包刷新记录，失败时保留最后一次有效记录。"""
    latest = latest_installed_codex_runtime(package_roots)
    if latest is not None:
        store.save(latest.executable_path)
    return store.load()
