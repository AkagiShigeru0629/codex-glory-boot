import argparse
import sys
from pathlib import Path
from zipfile import ZipFile

import imageio_ffmpeg
from PIL import Image
from PySide6.QtCore import QEventLoop, QTimer, QUrl
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtWidgets import QApplication


ROOT = Path(__file__).resolve().parents[1]


def check_assets() -> None:
    video_path = ROOT / "media" / "startup.mp4"
    poster_path = ROOT / "media" / "poster.png"
    if not video_path.is_file():
        raise AssertionError(f"缺少视频: {video_path}")
    if not poster_path.is_file():
        raise AssertionError(f"缺少海报: {poster_path}")

    reader = imageio_ffmpeg.read_frames(str(video_path), pix_fmt="rgb24")
    metadata = next(reader)
    try:
        width, height = metadata["size"]
        fps = float(metadata["fps"])
        duration = float(metadata["duration"])
    finally:
        reader.close()

    assert (width, height) == (1920, 1080), (width, height)
    assert abs(fps - 60) < 0.01, fps
    assert abs(duration - 7.7) <= 0.1, duration
    with Image.open(poster_path) as poster:
        assert poster.size == (1920, 1080), poster.size
        assert poster.mode == "RGB", poster.mode

    app = QApplication.instance() or QApplication([])
    player = QMediaPlayer()
    loop = QEventLoop()
    state = {"ready": False, "error": ""}

    def loaded(status: QMediaPlayer.MediaStatus) -> None:
        if status in {
            QMediaPlayer.MediaStatus.LoadedMedia,
            QMediaPlayer.MediaStatus.BufferedMedia,
        }:
            state["ready"] = True
            loop.quit()

    def failed(_error: QMediaPlayer.Error, message: str) -> None:
        state["error"] = message
        loop.quit()

    player.mediaStatusChanged.connect(loaded)
    player.errorOccurred.connect(failed)
    player.setSource(QUrl.fromLocalFile(str(video_path)))
    QTimer.singleShot(5000, loop.quit)
    loop.exec()
    player.stop()
    app.processEvents()
    if not state["ready"]:
        raise AssertionError(
            state["error"] or "QtMultimedia 未能在 5 秒内解码 H.264 视频"
        )

    print(
        f"assets_ok duration={duration:.3f}s fps={fps:.3f} "
        f"size={width}x{height} qt_decode=ok"
    )


def check_package() -> None:
    package = ROOT / "dist" / "GloryCodexBoot"
    executable = package / "GloryCodexBoot.exe"
    if not executable.is_file():
        raise AssertionError("发布目录不存在，先运行 build.ps1")

    required_suffixes = {
        ("media", "startup.mp4"),
        ("media", "poster.png"),
        ("media", "wallpaper.jpg"),
        ("assets", "app-icon.png"),
        ("assets", "app-icon.ico"),
        ("config", "launcher.example.json"),
        ("LICENSE",),
        ("THIRD_PARTY_NOTICES.md",),
        ("_internal", "glory_boot", "resources", "skin.css"),
        ("_internal", "glory_boot", "resources", "skin.js"),
        ("_internal", "glory_boot", "resources", "skin_profiles.json"),
        ("_internal", "PySide6", "Qt6WebSockets.dll"),
        ("_internal", "PySide6", "QtWebSockets.pyd"),
    }
    for parts in required_suffixes:
        path = package.joinpath(*parts)
        if not path.is_file():
            raise AssertionError(f"发布包缺少文件: {path}")

    multimedia_plugins = list(package.rglob("*mediaplugin*.dll"))
    if not multimedia_plugins:
        raise AssertionError("发布包缺少 Qt 多媒体插件")
    print(f"package_ok multimedia_plugins={len(multimedia_plugins)}")


def check_archive() -> None:
    archive = ROOT / "dist" / "GloryCodexBoot-win-x64.zip"
    if not archive.is_file():
        raise AssertionError("发布压缩包不存在，先运行 package.ps1")

    with ZipFile(archive) as package:
        log_entries = [
            name for name in package.namelist() if name.casefold().startswith("logs/")
        ]
    if log_entries:
        raise AssertionError(f"发布压缩包包含运行日志: {log_entries[0]}")
    print("archive_ok logs=excluded")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--assets-only", action="store_true")
    arguments = parser.parse_args(argv)
    try:
        check_assets()
        if not arguments.assets_only:
            check_package()
            check_archive()
    except AssertionError as exc:
        print(f"smoke_test_failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
