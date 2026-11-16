"""把现有启动动画改写为带 CRT 电视机关闭收束的正式媒体。"""

from __future__ import annotations

import argparse
import subprocess
from collections.abc import Iterator
from pathlib import Path

import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageEnhance


WIDTH = 1920
HEIGHT = 1080
FPS = 60
SOURCE_END_SECONDS = 6.4
CRT_DURATION_SECONDS = 0.7
OUTPUT_DURATION_SECONDS = 7.7
SOURCE_FRAME_COUNT = round(SOURCE_END_SECONDS * FPS)
CRT_FRAME_COUNT = round(CRT_DURATION_SECONDS * FPS)
TOTAL_FRAMES = round(OUTPUT_DURATION_SECONDS * FPS)
BLACK_TAIL_FRAME_COUNT = TOTAL_FRAMES - SOURCE_FRAME_COUNT - CRT_FRAME_COUNT

VERTICAL_END_FRAME = 16
LINE_END_FRAME = 19
PINCH_END_FRAME = 36
LINE_HEIGHT = 4
MIN_DOT_SIZE = 4
WARM_WHITE = (255, 242, 228)

_FRAME_BYTES = WIDTH * HEIGHT * 3


def _smooth(value: float) -> float:
    value = min(1.0, max(0.0, value))
    return value * value * (3.0 - 2.0 * value)


def _brighten(frame: Image.Image, amount: float) -> Image.Image:
    brightened = ImageEnhance.Brightness(frame).enhance(1.0 + amount)
    if amount <= 0:
        return brightened
    tint = Image.new("RGB", brightened.size, WARM_WHITE)
    return Image.blend(brightened, tint, min(0.34, amount * 0.22))


def _centered_band(
    source: Image.Image,
    width: int,
    height: int,
    brightness: float,
) -> Image.Image:
    width = max(1, width)
    height = max(1, height)
    band = source.resize(
        (width, height),
        Image.Resampling.LANCZOS,
    )
    band = _brighten(band, brightness)
    canvas = Image.new("RGB", source.size, (0, 0, 0))
    canvas.paste(
        band,
        ((source.width - width) // 2, (source.height - height) // 2),
    )
    return canvas


def render_crt_frame(source: Image.Image, frame_index: int) -> Image.Image:
    """生成一帧电视关机式收缩，帧号从 0 到 CRT_FRAME_COUNT-1。"""
    if not 0 <= frame_index < CRT_FRAME_COUNT:
        raise ValueError("frame_index 超出 CRT 帧范围")

    image = source.convert("RGB")
    if frame_index == 0:
        return image.copy()

    if frame_index <= VERTICAL_END_FRAME:
        progress = _smooth(frame_index / VERTICAL_END_FRAME)
        height = max(1, round(image.height * (1.0 - progress)))
        return _centered_band(
            image,
            image.width,
            height,
            0.18 + progress * 0.20,
        )

    if frame_index <= LINE_END_FRAME:
        return _centered_band(
            image,
            image.width,
            LINE_HEIGHT,
            0.34,
        )

    if frame_index <= PINCH_END_FRAME:
        progress = _smooth(
            (frame_index - LINE_END_FRAME)
            / (PINCH_END_FRAME - LINE_END_FRAME)
        )
        width = max(
            MIN_DOT_SIZE,
            round(image.width * (1.0 - progress)),
        )
        return _centered_band(
            image,
            width,
            LINE_HEIGHT,
            0.34 + progress * 0.18,
        )

    fade = _smooth(
        (frame_index - PINCH_END_FRAME)
        / (CRT_FRAME_COUNT - 1 - PINCH_END_FRAME)
    )
    dot = _centered_band(
        image,
        MIN_DOT_SIZE,
        MIN_DOT_SIZE,
        0.52,
    )
    return ImageEnhance.Brightness(dot).enhance(max(0.0, 1.0 - fade))


def iter_crt_frames(source: Image.Image) -> Iterator[Image.Image]:
    for frame_index in range(CRT_FRAME_COUNT):
        yield render_crt_frame(source, frame_index)


def _ffmpeg() -> str:
    return imageio_ffmpeg.get_ffmpeg_exe()


def _iter_source_frames(video: Path) -> Iterator[Image.Image]:
    command = [
        _ffmpeg(),
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(video),
        "-vf",
        f"fps={FPS},scale={WIDTH}:{HEIGHT}:flags=lanczos",
        "-frames:v",
        str(SOURCE_FRAME_COUNT),
        "-an",
        "-sn",
        "-pix_fmt",
        "rgb24",
        "-f",
        "rawvideo",
        "pipe:1",
    ]
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if process.stdout is None:
        raise RuntimeError("无法打开 FFmpeg 视频输出管道")
    try:
        while True:
            payload = process.stdout.read(_FRAME_BYTES)
            if not payload:
                break
            if len(payload) != _FRAME_BYTES:
                raise RuntimeError("FFmpeg 返回了不完整的视频帧")
            yield Image.frombytes("RGB", (WIDTH, HEIGHT), payload)
    finally:
        process.stdout.close()
        error = (
            process.stderr.read().decode("utf-8", errors="replace")
            if process.stderr is not None
            else ""
        )
        return_code = process.wait()
        if return_code != 0:
            raise RuntimeError(f"FFmpeg 视频解码失败: {error}")


def _start_encoder(output: Path) -> subprocess.Popen[bytes]:
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        _ffmpeg(),
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-s",
        f"{WIDTH}x{HEIGHT}",
        "-r",
        str(FPS),
        "-i",
        "-",
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(output),
    ]
    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    if process.stdin is None:
        raise RuntimeError("无法打开 FFmpeg 编码输入管道")
    return process


def _write_frame(process: subprocess.Popen[bytes], frame: Image.Image) -> None:
    assert process.stdin is not None
    process.stdin.write(np.asarray(frame, dtype=np.uint8).tobytes())


def _finish_encoder(process: subprocess.Popen[bytes]) -> None:
    assert process.stdin is not None
    process.stdin.close()
    error = (
        process.stderr.read().decode("utf-8", errors="replace")
        if process.stderr is not None
        else ""
    )
    if process.wait() != 0:
        raise RuntimeError(f"FFmpeg 编码失败: {error}")


def append_crt_shutdown(
    input_video: Path,
    output_video: Path,
) -> None:
    """截取现有动画前 6.4 秒，追加 CRT 收束和黑色交接。"""
    if not input_video.is_file():
        raise FileNotFoundError(input_video)
    if input_video.resolve() == output_video.resolve():
        raise ValueError("输入视频和输出视频必须是不同路径")

    encoder = _start_encoder(output_video)
    written = 0
    last_source: Image.Image | None = None
    try:
        for frame in _iter_source_frames(input_video):
            _write_frame(encoder, frame)
            last_source = frame
            written += 1
        if last_source is None:
            raise RuntimeError("输入视频中没有可用画面")

        while written < SOURCE_FRAME_COUNT:
            _write_frame(encoder, last_source)
            written += 1

        for frame in iter_crt_frames(last_source):
            _write_frame(encoder, frame)
            written += 1

        black = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))
        for _ in range(BLACK_TAIL_FRAME_COUNT):
            _write_frame(encoder, black)
            written += 1
    finally:
        _finish_encoder(encoder)

    if written != TOTAL_FRAMES:
        raise RuntimeError(f"成片帧数不正确: {written}/{TOTAL_FRAMES}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    append_crt_shutdown(arguments.input, arguments.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
