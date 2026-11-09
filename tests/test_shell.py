import hashlib
import json
from pathlib import Path

import pytest

from glory_boot.adapters.shell import (
    ShortcutConflictError,
    ShortcutManager,
    ShortcutRecord,
)


def _record(path: Path) -> ShortcutRecord:
    return ShortcutRecord(
        path=str(path),
        target=r"D:\codex项目\codex开屏\dist\GloryCodexBoot\GloryCodexBoot.exe",
        arguments="",
        icon=str(path.with_suffix(".ico")),
        working_directory=r"D:\codex项目\codex开屏\dist\GloryCodexBoot",
    )


def _create_fake_shortcut(record: ShortcutRecord) -> None:
    Path(record.path).write_bytes(
        json.dumps(
            {
                "target": record.target,
                "arguments": record.arguments,
                "icon": record.icon,
            },
            ensure_ascii=False,
        ).encode("utf-8")
    )


def test_install_is_repeatable_and_records_sha256(tmp_path: Path) -> None:
    shortcut = tmp_path / "桌面" / "Codex 荣耀启动.lnk"
    manager = ShortcutManager(tmp_path / "state" / "shortcut.json")
    record = _record(shortcut)

    first = manager.install(record, create=_create_fake_shortcut)
    second = manager.install(record, create=_create_fake_shortcut)

    expected_hash = hashlib.sha256(shortcut.read_bytes()).hexdigest()
    assert first == second
    assert first.shortcut_sha256 == expected_hash
    assert first.target == record.target
    assert first.arguments == record.arguments
    assert first.icon == record.icon


def test_restore_removes_only_the_recorded_shortcut(tmp_path: Path) -> None:
    shortcut = tmp_path / "桌面" / "Codex 荣耀启动.lnk"
    manager = ShortcutManager(tmp_path / "state" / "shortcut.json")
    manager.install(_record(shortcut), create=_create_fake_shortcut)

    manager.restore()
    manager.restore()

    assert shortcut.exists() is False
    assert manager.state_path.exists() is False


def test_install_rejects_unrelated_existing_shortcut(tmp_path: Path) -> None:
    shortcut = tmp_path / "桌面" / "Codex 荣耀启动.lnk"
    shortcut.parent.mkdir()
    shortcut.write_bytes(b"unrelated")
    calls: list[ShortcutRecord] = []
    manager = ShortcutManager(tmp_path / "state" / "shortcut.json")

    with pytest.raises(ShortcutConflictError):
        manager.install(
            _record(shortcut),
            create=lambda record: calls.append(record),
        )

    assert calls == []
    assert shortcut.read_bytes() == b"unrelated"


def test_restore_refuses_to_delete_modified_shortcut(tmp_path: Path) -> None:
    shortcut = tmp_path / "桌面" / "Codex 荣耀启动.lnk"
    manager = ShortcutManager(tmp_path / "state" / "shortcut.json")
    manager.install(_record(shortcut), create=_create_fake_shortcut)
    shortcut.write_bytes(b"modified")

    with pytest.raises(ShortcutConflictError):
        manager.restore()

    assert shortcut.read_bytes() == b"modified"
