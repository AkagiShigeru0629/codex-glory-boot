import os
from datetime import date
from pathlib import Path

from glory_boot.services.codex_readiness import CodexReadinessProbe


PRIMARY_MARKER = (
    "[startup][renderer] app routes mounted after 16593ms "
    "rendererWindowAppearance=primary"
)


def _write_log(
    root: Path,
    *,
    log_date: date,
    text: str,
    modified_at: float,
) -> Path:
    folder = root / f"{log_date.year:04d}" / f"{log_date.month:02d}" / (
        f"{log_date.day:02d}"
    )
    folder.mkdir(parents=True)
    path = folder / "codex-desktop-test-17132-t0-i1-130858-0.log"
    path.write_text(text, encoding="utf-8")
    os.utime(path, (modified_at, modified_at))
    return path


def test_readiness_probe_detects_primary_renderer_mount(tmp_path: Path) -> None:
    day = date(2026, 11, 7)
    _write_log(
        tmp_path,
        log_date=day,
        text=f"info startup\n{PRIMARY_MARKER}\n",
        modified_at=101.0,
    )
    probe = CodexReadinessProbe(
        tmp_path,
        launched_at=100.0,
        today=lambda: day,
    )

    assert probe.is_primary_mounted() is True


def test_readiness_probe_ignores_non_primary_and_stale_logs(
    tmp_path: Path,
) -> None:
    day = date(2026, 11, 7)
    _write_log(
        tmp_path,
        log_date=day,
        text="app routes mounted rendererWindowAppearance=avatarOverlay\n",
        modified_at=101.0,
    )
    old = tmp_path / "2026" / "11" / "06"
    old.mkdir(parents=True)
    old_log = old / "codex-desktop-test-17132-t0-i1-120000-0.log"
    old_log.write_text(PRIMARY_MARKER, encoding="utf-8")
    os.utime(old_log, (50.0, 50.0))
    probe = CodexReadinessProbe(
        tmp_path,
        launched_at=100.0,
        today=lambda: day,
    )

    assert probe.is_primary_mounted() is False


def test_readiness_probe_detects_marker_appended_after_start(tmp_path: Path) -> None:
    day = date(2026, 11, 7)
    path = _write_log(
        tmp_path,
        log_date=day,
        text="renderer starting\n",
        modified_at=101.0,
    )
    probe = CodexReadinessProbe(
        tmp_path,
        launched_at=100.0,
        today=lambda: day,
    )

    assert probe.is_primary_mounted() is False
    with path.open("a", encoding="utf-8") as stream:
        stream.write(PRIMARY_MARKER + "\n")
    assert probe.is_primary_mounted() is True
