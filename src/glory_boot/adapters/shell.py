import hashlib
import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path


class ShortcutConflictError(OSError):
    """快捷方式目标与本启动器记录不一致。"""


@dataclass(frozen=True, slots=True)
class ShortcutRecord:
    path: str
    target: str
    arguments: str
    icon: str
    working_directory: str


@dataclass(frozen=True, slots=True)
class ShortcutBackup:
    path: str
    target: str
    arguments: str
    icon: str
    working_directory: str
    shortcut_sha256: str

    def matches(self, record: ShortcutRecord) -> bool:
        return (
            self.path == record.path
            and self.target == record.target
            and self.arguments == record.arguments
            and self.icon == record.icon
            and self.working_directory == record.working_directory
        )


class ShortcutManager:
    def __init__(self, state_path: Path) -> None:
        self.state_path = state_path

    def install(
        self,
        record: ShortcutRecord,
        *,
        create: Callable[[ShortcutRecord], None],
        replace: bool = False,
    ) -> ShortcutBackup:
        shortcut_path = Path(record.path)
        existing = self._load_backup()

        if shortcut_path.exists() and not replace:
            if existing is None or not existing.matches(record):
                raise ShortcutConflictError(
                    f"拒绝覆盖没有本启动器记录的快捷方式: {shortcut_path}"
                )

        shortcut_path.parent.mkdir(parents=True, exist_ok=True)
        create(record)
        if not shortcut_path.is_file():
            raise OSError(f"快捷方式创建后不存在: {shortcut_path}")

        backup = ShortcutBackup(
            **asdict(record),
            shortcut_sha256=self._sha256(shortcut_path),
        )
        self._write_backup(backup)
        return backup

    def restore(
        self,
        *,
        remove: Callable[[Path], None] | None = None,
    ) -> None:
        backup = self._load_backup()
        if backup is None:
            return

        shortcut_path = Path(backup.path)
        if shortcut_path.is_file():
            actual_hash = self._sha256(shortcut_path)
            if actual_hash != backup.shortcut_sha256:
                raise ShortcutConflictError(
                    f"快捷方式安装后被修改，拒绝自动删除: {shortcut_path}"
                )
            if remove is None:
                shortcut_path.unlink()
            else:
                remove(shortcut_path)

        self.state_path.unlink(missing_ok=True)

    def _load_backup(self) -> ShortcutBackup | None:
        if not self.state_path.is_file():
            return None
        try:
            raw = json.loads(self.state_path.read_text(encoding="utf-8"))
            return ShortcutBackup(**raw)
        except (json.JSONDecodeError, TypeError, KeyError) as exc:
            raise ShortcutConflictError(
                f"快捷方式备份记录损坏: {self.state_path}"
            ) from exc

    def _write_backup(self, backup: ShortcutBackup) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.state_path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(asdict(backup), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(self.state_path)

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
