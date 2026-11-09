import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn

from glory_boot.domain.skin import package_version_from_path


def _reject_constant(value: str) -> NoReturn:
    raise ValueError(f"非有限数值: {value}")


@dataclass(frozen=True, slots=True)
class CodexRuntimeInstall:
    version: str
    executable_path: str


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

        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self._path.with_name(f"{self._path.name}.tmp")
            temporary.write_text(
                json.dumps(
                    {
                        "version": version,
                        "executable_path": str(path),
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            os.replace(temporary, self._path)
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
