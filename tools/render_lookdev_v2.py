"""生成第二版开屏视觉样片，不接入正式启动流程。"""

from __future__ import annotations

import argparse
import math
import subprocess
from collections.abc import Sequence
from pathlib import Path

import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont


WIDTH = 1920
HEIGHT = 1080
FPS = 30
DURATION = 8.0
TOTAL_FRAMES = int(FPS * DURATION)

RED = (197, 28, 31)
RED_LIGHT = (255, 76, 55)
GOLD = (231, 188, 53)
GOLD_LIGHT = (255, 226, 144)
IVORY = (248, 240, 224)
INK = (8, 8, 9)


def _clamp(value: float) -> float:
    return min(1.0, max(0.0, value))


def _smooth(value: float) -> float:
    value = _clamp(value)
    return value * value * (3.0 - 2.0 * value)


def _stage(seconds: float, start: float, end: float) -> float:
    return _smooth((seconds - start) / (end - start))


def _font(size: int, *, mono: bool = False, bold: bool = False) -> ImageFont.FreeTypeFont:
    if mono:
        candidates = [
            Path(r"C:\Windows\Fonts\consola.ttf"),
            Path(r"C:\Windows\Fonts\bahnschrift.ttf"),
        ]
    elif bold:
        candidates = [
            Path(r"C:\Windows\Fonts\msyhbd.ttc"),
            Path(r"C:\Windows\Fonts\simhei.ttf"),
        ]
    else:
        candidates = [
            Path(r"C:\Windows\Fonts\msyh.ttc"),
            Path(r"C:\Windows\Fonts\simhei.ttf"),
        ]
    for path in candidates:
        if path.is_file():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


TITLE_FONT = _font(20, mono=True)
STATUS_FONT = _font(24, bold=True)
CAPTION_FONT = _font(18)
MICRO_FONT = _font(15, mono=True)
FINAL_FONT = _font(92, bold=True)

TEN_ZONE_SOURCE_START = 0.72
TEN_ZONE_SOURCE_END = 1.56
TEN_ZONE_START = 6.92
TEN_ZONE_END = 7.76


def _cover(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    source_ratio = image.width / image.height
    target_ratio = size[0] / size[1]
    if source_ratio > target_ratio:
        new_width = round(image.height * target_ratio)
        left = (image.width - new_width) // 2
        image = image.crop((left, 0, left + new_width, image.height))
    else:
        new_height = round(image.width / target_ratio)
        top = (image.height - new_height) // 2
        image = image.crop((0, top, image.width, top + new_height))
    return image.resize(size, Image.Resampling.LANCZOS).convert("RGB")


def _camera_crop(base: Image.Image, seconds: float) -> Image.Image:
    push = _smooth(seconds / 3.2)
    release = _smooth((seconds - 5.4) / 1.4)
    scale = 0.965 + 0.055 * push - 0.015 * release
    shake = 0.0
    for burst, strength in ((1.28, 1.5), (4.72, 1.0), (6.67, 1.8)):
        distance = abs(seconds - burst)
        if distance < 0.12:
            envelope = 1.0 - distance / 0.12
            shake += strength * envelope
    drift_x = math.sin(seconds * 0.72) * 7.0 + math.sin(seconds * 18.0) * shake
    drift_y = math.cos(seconds * 0.51) * 4.0 + math.cos(seconds * 15.0) * shake
    crop_width = round(WIDTH / scale)
    crop_height = round(HEIGHT / scale)
    center_x = WIDTH / 2 + drift_x
    center_y = HEIGHT / 2 + drift_y
    left = max(0, min(WIDTH - crop_width, round(center_x - crop_width / 2)))
    top = max(0, min(HEIGHT - crop_height, round(center_y - crop_height / 2)))
    return base.crop((left, top, left + crop_width, top + crop_height)).resize(
        (WIDTH, HEIGHT),
        Image.Resampling.BICUBIC,
    )


def _color_grade(image: Image.Image, seconds: float) -> Image.Image:
    pixels = np.asarray(image, dtype=np.float32) / 255.0
    luminance = (
        pixels[:, :, 0] * 0.2126
        + pixels[:, :, 1] * 0.7152
        + pixels[:, :, 2] * 0.0722
    )
    pixels = (pixels - 0.5) * 1.13 + 0.5
    pixels[:, :, 0] += 0.018 + 0.012 * math.sin(seconds * 2.2)
    pixels[:, :, 1] *= 0.965
    pixels[:, :, 2] *= 0.96
    shadow = np.clip(1.0 - luminance * 2.5, 0.0, 1.0)[:, :, None]
    pixels = pixels + shadow * np.array([0.045, 0.002, 0.004], dtype=np.float32)
    return Image.fromarray(
        (np.clip(pixels, 0.0, 1.0) * 255.0).astype(np.uint8),
        "RGB",
    )


def _make_vignette() -> Image.Image:
    y, x = np.ogrid[-1.0:1.0:HEIGHT * 1j, -1.0:1.0:WIDTH * 1j]
    radius = np.sqrt((x * 0.86) ** 2 + (y * 1.05) ** 2)
    alpha = np.clip((radius - 0.46) / 0.72, 0.0, 1.0) ** 1.75
    layer = np.zeros((HEIGHT, WIDTH, 4), dtype=np.uint8)
    layer[:, :, 3] = (alpha * 198).astype(np.uint8)
    return Image.fromarray(layer, "RGBA")


def _make_sweep_mask(phase: float) -> Image.Image:
    y, x = np.ogrid[0.0:1.0:HEIGHT * 1j, 0.0:1.0:WIDTH * 1j]
    diagonal = x * 0.72 + y * 0.28
    center = -0.18 + phase * 1.36
    band = np.exp(-((diagonal - center) / 0.042) ** 2)
    secondary = np.exp(-((diagonal - center + 0.065) / 0.012) ** 2) * 0.45
    alpha = np.clip((band + secondary) * 128.0, 0.0, 128.0).astype(np.uint8)
    mask = np.zeros((HEIGHT, WIDTH, 4), dtype=np.uint8)
    mask[:, :, :3] = GOLD_LIGHT
    mask[:, :, 3] = alpha
    return Image.fromarray(mask, "RGBA")


def _make_particles() -> list[tuple[float, float, float, float, int]]:
    random = np.random.default_rng(20261105)
    return [
        (
            float(random.uniform(0.0, WIDTH)),
            float(random.uniform(0.0, HEIGHT)),
            float(random.uniform(0.8, 2.6)),
            float(random.uniform(5.0, 24.0)),
            int(random.integers(0, 3)),
        )
        for _ in range(92)
    ]


VIGNETTE = _make_vignette()
PARTICLES = _make_particles()
SWEEPS = [_make_sweep_mask(index / 20) for index in range(21)]


def _draw_particles(image: Image.Image, seconds: float, intensity: float) -> None:
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer, "RGBA")
    for base_x, base_y, radius, speed, kind in PARTICLES:
        x = (base_x + math.sin(seconds * 0.45 + base_y) * 19.0) % WIDTH
        y = (base_y - seconds * speed) % HEIGHT
        pulse = 0.55 + 0.45 * math.sin(seconds * 2.4 + base_x * 0.013)
        color = RED_LIGHT if kind == 0 else GOLD_LIGHT if kind == 1 else IVORY
        alpha = int((16 + 62 * pulse) * intensity)
        if kind == 0:
            draw.line((x - radius * 3, y, x + radius * 3, y), fill=(*color, alpha), width=1)
        else:
            draw.ellipse(
                (x - radius, y - radius, x + radius, y + radius),
                fill=(*color, alpha),
            )
    glow = layer.filter(ImageFilter.GaussianBlur(7))
    image.alpha_composite(glow)
    image.alpha_composite(layer)


def _draw_scan_bands(image: Image.Image, seconds: float) -> None:
    open_amount = 1.0 - _stage(seconds, 0.0, 0.7)
    glitch_amount = 0.0
    for center, half_width in ((1.22, 0.17), (4.74, 0.12), (6.67, 0.22)):
        distance = abs(seconds - center)
        if distance < half_width:
            glitch_amount = max(glitch_amount, 1.0 - distance / half_width)
    intensity = max(open_amount, glitch_amount * 0.56)
    if intensity <= 0.0:
        return
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer, "RGBA")
    random = np.random.default_rng(1221)
    for index in range(18):
        y = int((index * 67 + int(seconds * 193)) % HEIGHT)
        thickness = int(random.integers(1, 3 + max(1, int(glitch_amount * 13))))
        x1 = int(random.integers(0, WIDTH // 3))
        x2 = int(random.integers(WIDTH // 2, WIDTH))
        alpha = int((24 + random.integers(0, 45)) * intensity)
        draw.rectangle((x1, y, x2, y + thickness), fill=(*RED, alpha))
        if index % 4 == 0:
            draw.rectangle((0, y + 8, WIDTH, y + 9), fill=(*RED_LIGHT, alpha // 3))
    image.alpha_composite(layer.filter(ImageFilter.GaussianBlur(0.4)))


def _channel_shift(image: Image.Image, offset: int, amount: float) -> Image.Image:
    if offset <= 0 or amount <= 0:
        return image
    red, green, blue = image.split()
    red = ImageChops.offset(red, offset, 0)
    blue = ImageChops.offset(blue, -offset, 0)
    shifted = Image.merge("RGB", (red, green, blue))
    return Image.blend(image, shifted, 0.26 * amount)


def _glitch_slices(image: Image.Image, seconds: float) -> Image.Image:
    strength = 0.0
    for center, half_width in ((1.22, 0.16), (4.72, 0.14), (6.69, 0.24)):
        distance = abs(seconds - center)
        if distance < half_width:
            strength = max(strength, 1.0 - distance / half_width)
    if strength <= 0.0:
        return image

    result = image.copy()
    random = np.random.default_rng(int(seconds * 1000) + 991)
    for _ in range(7 + int(strength * 9)):
        top = int(random.integers(40, HEIGHT - 80))
        height = int(random.integers(3, 22))
        shift = int(random.normal(0.0, 18.0 + 42.0 * strength))
        strip = image.crop((0, top, WIDTH, min(HEIGHT, top + height)))
        result.paste(strip, (shift, top))
    result = _channel_shift(result, max(2, int(7 * strength)), strength)
    strip_layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(strip_layer, "RGBA")
    for _ in range(8):
        y = int(random.integers(50, HEIGHT - 50))
        draw.rectangle(
            (0, y, WIDTH, y + 1),
            fill=(*RED_LIGHT, int(75 * strength)),
        )
    return Image.alpha_composite(result.convert("RGBA"), strip_layer)


def _draw_hud(image: Image.Image, seconds: float) -> None:
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer, "RGBA")
    fade = _stage(seconds, 0.0, 0.55) * (1.0 - _stage(seconds, 6.75, 7.1))
    if fade <= 0.0:
        return

    draw.line((54, 48, 112, 48), fill=(*RED_LIGHT, int(210 * fade)), width=3)
    draw.text(
        (54, 62),
        "GLORY // ZERO-WAIT LINK",
        font=TITLE_FONT,
        fill=(*IVORY, int(218 * fade)),
    )
    draw.text(
        (54, 94),
        "CODEX STARTUP PROTOCOL",
        font=MICRO_FONT,
        fill=(*GOLD, int(165 * fade)),
    )

    right_x = WIDTH - 54
    draw.line((right_x - 96, 48, right_x, 48), fill=(*GOLD, int(178 * fade)), width=2)
    draw.text(
        (right_x, 61),
        "12:04 / 00:08",
        font=MICRO_FONT,
        fill=(*IVORY, int(165 * fade)),
        anchor="ra",
    )
    draw.text(
        (right_x, 91),
        "SYNC CHANNEL / ACTIVE",
        font=MICRO_FONT,
        fill=(*RED_LIGHT, int(150 * fade)),
        anchor="ra",
    )

    status_reveal = _stage(seconds, 3.75, 4.45) * fade
    if status_reveal > 0.0:
        pulse = 0.55 + 0.45 * math.sin(seconds * 5.4) ** 2
        draw.rectangle((54, 972, 61, 1012), fill=(*RED, int(220 * status_reveal)))
        draw.ellipse(
            (78, 986, 92, 1000),
            fill=(*GOLD, int((155 + 90 * pulse) * status_reveal)),
        )
        draw.text(
            (111, 974),
            "CODEX 正在唤醒",
            font=STATUS_FONT,
            fill=(*IVORY, int(242 * status_reveal)),
        )
        draw.text(
            (112, 1008),
            "建立启动通道 · ESC 跳过动画",
            font=CAPTION_FONT,
            fill=(*GOLD_LIGHT, int(178 * status_reveal)),
        )
        progress = 492 * _smooth(seconds / 6.3)
        draw.line(
            (760, 1006, 760 + progress, 1006),
            fill=(*RED_LIGHT, int(175 * status_reveal)),
            width=3,
        )

    draw.line(
        (WIDTH - 472, 1024, WIDTH - 54, 1024),
        fill=(*GOLD, int(72 * fade)),
        width=1,
    )
    for x in (WIDTH - 340, WIDTH - 270, WIDTH - 200):
        draw.rectangle(
            (x, 1017, x + 42, 1021),
            fill=(*RED, int(46 * fade)),
        )
    image.alpha_composite(layer)


def _apply_handoff(image: Image.Image, seconds: float) -> Image.Image:
    progress = _stage(seconds, 6.8, 7.6)
    if progress <= 0.0:
        return image
    result = Image.new("RGBA", image.size, (*INK, 255))
    bands = 18
    random = np.random.default_rng(8812)
    for index in range(bands):
        top = round(index * HEIGHT / bands)
        bottom = round((index + 1) * HEIGHT / bands)
        strip = image.crop((0, top, WIDTH, bottom)).convert("RGBA")
        delay = (index % 5) * 0.035
        local = _smooth((progress - delay) / max(0.22, 1.0 - delay))
        direction = -1 if index % 2 else 1
        shift = int(direction * (30 + random.integers(0, 95)) * local)
        alpha = int(255 * (1.0 - local))
        strip.putalpha(alpha)
        result.alpha_composite(strip, (shift, top))
        if 0.05 < local < 0.82:
            draw = ImageDraw.Draw(result, "RGBA")
            draw.line(
                (0, top, WIDTH, top),
                fill=(*RED_LIGHT, int(150 * (1.0 - local))),
                width=2 if index % 3 == 0 else 1,
            )
    if progress > 0.78:
        finish = _stage(progress, 0.78, 1.0)
        draw = ImageDraw.Draw(result, "RGBA")
        center_y = HEIGHT // 2
        draw.line(
            (WIDTH // 2 - 190, center_y, WIDTH // 2 + 190, center_y),
            fill=(*GOLD, int(210 * finish)),
            width=2,
        )
        draw.text(
            (WIDTH // 2, center_y - 30),
            "CODEX",
            font=FINAL_FONT,
            fill=(*IVORY, int(245 * finish)),
            anchor="ms",
        )
        draw.text(
            (WIDTH // 2, center_y + 42),
            "工作区已就绪",
            font=CAPTION_FONT,
            fill=(*GOLD_LIGHT, int(190 * finish)),
            anchor="ma",
        )
    return result.convert("RGB")


def _ten_zone_frame_index(seconds: float, frame_count: int) -> int | None:
    if frame_count <= 0 or not TEN_ZONE_START <= seconds < TEN_ZONE_END:
        return None
    progress = (seconds - TEN_ZONE_START) / (TEN_ZONE_END - TEN_ZONE_START)
    return min(frame_count - 1, max(0, round(progress * (frame_count - 1))))


def _apply_ten_zone(
    image: Image.Image,
    seconds: float,
    frames: Sequence[Image.Image],
) -> Image.Image:
    if not frames:
        return image
    index = _ten_zone_frame_index(seconds, len(frames))
    if index is None:
        return image

    fade_in = _smooth((seconds - TEN_ZONE_START) / 0.08)
    fade_out = 1.0 - _smooth((seconds - 7.62) / 0.14)
    opacity = fade_in * fade_out
    if opacity <= 0.0:
        return image
    return Image.blend(image, frames[index].convert("RGB"), opacity)


def _load_ten_zone_frames(video: Path) -> tuple[Image.Image, ...]:
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(video),
        "-ss",
        str(TEN_ZONE_SOURCE_START),
        "-t",
        str(TEN_ZONE_SOURCE_END - TEN_ZONE_SOURCE_START),
        "-vf",
        f"scale={WIDTH}:{HEIGHT}:flags=lanczos",
        "-an",
        "-sn",
        "-pix_fmt",
        "rgb24",
        "-f",
        "rawvideo",
        "pipe:1",
    ]
    process = subprocess.run(command, capture_output=True)
    if process.returncode != 0:
        error = process.stderr.decode("utf-8", errors="replace")
        raise RuntimeError(f"无法提取十区画面: {error}")

    frame_bytes = WIDTH * HEIGHT * 3
    if not process.stdout or len(process.stdout) % frame_bytes:
        raise RuntimeError("十区画面帧数据不完整")
    frames = tuple(
        Image.frombytes(
            "RGB",
            (WIDTH, HEIGHT),
            process.stdout[offset : offset + frame_bytes],
        )
        for offset in range(0, len(process.stdout), frame_bytes)
    )
    if not frames:
        raise RuntimeError("十区视频中没有可用画面")
    return frames


def render_frame(
    base: Image.Image,
    seconds: float,
    ten_zone_frames: Sequence[Image.Image] = (),
) -> Image.Image:
    image = _camera_crop(base, seconds)
    image = _color_grade(image, seconds)

    brightness = 0.72 + 0.28 * _stage(seconds, 0.0, 0.72)
    if 1.15 <= seconds <= 1.6:
        brightness += 0.08 * math.sin((seconds - 1.15) / 0.45 * math.pi)
    image = ImageEnhance.Brightness(image).enhance(brightness)
    image = ImageEnhance.Contrast(image).enhance(1.06)

    glow = image.filter(ImageFilter.GaussianBlur(23))
    glow = ImageEnhance.Brightness(glow).enhance(1.32)
    red_glow = Image.new("RGB", image.size, RED)
    red_glow = Image.blend(Image.new("RGB", image.size, INK), red_glow, 0.28)
    image = Image.blend(image, ImageChops.screen(image, glow), 0.15)
    image = Image.blend(image, ImageChops.screen(image, red_glow), 0.035)

    if 1.02 <= seconds <= 2.18:
        phase = (seconds - 1.02) / 1.16
        sweep = SWEEPS[min(len(SWEEPS) - 1, max(0, round(phase * (len(SWEEPS) - 1))))]
        image = Image.alpha_composite(image.convert("RGBA"), sweep).convert("RGB")
    if 5.45 <= seconds <= 6.18:
        phase = (seconds - 5.45) / 0.73
        sweep = SWEEPS[min(len(SWEEPS) - 1, max(0, round(phase * (len(SWEEPS) - 1))))]
        sweep = Image.eval(sweep, lambda value: int(value * 0.72))
        image = Image.alpha_composite(image.convert("RGBA"), sweep).convert("RGB")

    rgba = image.convert("RGBA")
    _draw_particles(rgba, seconds, 0.75 + 0.25 * _stage(seconds, 0.2, 1.3))
    _draw_scan_bands(rgba, seconds)
    rgba.alpha_composite(VIGNETTE)
    _draw_hud(rgba, seconds)
    image = rgba.convert("RGB")
    image = _glitch_slices(image, seconds).convert("RGB")
    return _apply_ten_zone(
        _apply_handoff(image, seconds),
        seconds,
        ten_zone_frames,
    )


def _render_video(
    base: Image.Image,
    output: Path,
    ten_zone_frames: Sequence[Image.Image] = (),
) -> None:
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    command = [
        ffmpeg,
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
        "17",
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
        raise RuntimeError("无法打开 FFmpeg 输入管道")
    try:
        for frame_index in range(TOTAL_FRAMES):
            frame = render_frame(base, frame_index / FPS, ten_zone_frames)
            process.stdin.write(np.asarray(frame, dtype=np.uint8).tobytes())
    finally:
        process.stdin.close()
    error = process.stderr.read().decode("utf-8", errors="replace") if process.stderr else ""
    return_code = process.wait()
    if return_code != 0:
        raise RuntimeError(f"FFmpeg 编码失败: {error}")


def _render_contact_sheet(
    base: Image.Image,
    output: Path,
    ten_zone_frames: Sequence[Image.Image] = (),
) -> None:
    times = (0.35, 3.25, 7.15, 7.85)
    frames = [
        render_frame(base, seconds, ten_zone_frames)
        for seconds in times
    ]
    gap = 20
    sheet = Image.new("RGB", (WIDTH, HEIGHT * 4 + gap * 3), (3, 3, 4))
    for index, frame in enumerate(frames):
        sheet.paste(frame, (0, index * (HEIGHT + gap)))
    sheet.save(output, optimize=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--ten-zone-video", type=Path)
    arguments = parser.parse_args()
    arguments.out_dir.mkdir(parents=True, exist_ok=True)

    source = Image.open(arguments.source).convert("RGB")
    base = _cover(source, (WIDTH, HEIGHT))
    ten_zone_frames = (
        _load_ten_zone_frames(arguments.ten_zone_video)
        if arguments.ten_zone_video
        else ()
    )
    render_frame(base, 0.35, ten_zone_frames).save(
        arguments.out_dir / "lookdev-poster.png",
        optimize=True,
    )
    _render_contact_sheet(
        base,
        arguments.out_dir / "lookdev-keyframes.png",
        ten_zone_frames,
    )
    _render_video(
        base,
        arguments.out_dir / "lookdev-preview.mp4",
        ten_zone_frames,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
