"""把十区画面改写成荣耀丨codex，并替换原片中的 Codex 黑屏结尾。"""

from __future__ import annotations

import argparse
import math
import subprocess
from collections.abc import Iterator, Sequence
from pathlib import Path

import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont


WIDTH = 1920
HEIGHT = 1080
FPS = 60
DURATION = 8.0
TOTAL_FRAMES = round(FPS * DURATION)

OPENING_DURATION = 5.2
ENDING_DURATION = DURATION - OPENING_DURATION
BRIDGE_DURATION = 0.3
ENDING_FRAME_COUNT = round(FPS * ENDING_DURATION)
BRIDGE_FRAME_COUNT = round(FPS * BRIDGE_DURATION)
ENDING_MOTION_DURATION = 1.35
ENDING_MOTION_FRAME_COUNT = round(FPS * ENDING_MOTION_DURATION)

TEN_ZONE_SOURCE_START = 0.48
TEN_ZONE_SOURCE_END = 1.56
CLEAN_SOURCE_TIME = 0.64
TITLE_TEXT = "荣耀丨codex"
TITLE_REGION = (600, 350, 1360, 655)
TITLE_SAFE_REGION = (660, 385, 1260, 630)

RED = (255, 55, 48)
RED_DARK = (72, 2, 7)
WARM_WHITE = (252, 236, 224)

_FRAME_BYTES = WIDTH * HEIGHT * 3
_OPENING_SWEEPS = (
    (1.44, 2.02, 1, "gold"),
    (2.02, 2.25, -1, "white"),
)
_OPENING_STAGES = (
    (0.00, 0.72, "converge"),
    (0.72, 1.44, "ring"),
    (1.44, 2.16, "sweep"),
    (2.16, 2.95, "glitch"),
    (2.95, 3.74, "burst"),
    (3.74, 4.53, "scan"),
    (4.53, 5.02, "charge"),
)

_particle_random = np.random.default_rng(202611051)
OPENING_PARTICLES = tuple(
    (
        float(_particle_random.uniform(0.02, 0.98)),
        float(_particle_random.uniform(0.04, 0.96)),
        float(_particle_random.uniform(0.006, 0.024)),
        float(_particle_random.uniform(0.0, math.tau)),
        int(_particle_random.integers(1, 3)),
        int(_particle_random.integers(0, 3)),
    )
    for _ in range(88)
)


def _smooth(value: float) -> float:
    value = min(1.0, max(0.0, value))
    return value * value * (3.0 - 2.0 * value)


def _title_font(size: int) -> ImageFont.FreeTypeFont:
    candidates = (
        Path(r"C:\Windows\Fonts\simhei.ttf"),
        Path(r"C:\Windows\Fonts\msyhbd.ttc"),
    )
    for path in candidates:
        if path.is_file():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def _fit_title_font() -> ImageFont.FreeTypeFont:
    left, top, right, bottom = TITLE_SAFE_REGION
    max_width = max(80, right - left - 70)
    max_height = max(40, bottom - top - 52)
    for size in range(120, 31, -2):
        font = _title_font(size)
        box = font.getbbox(TITLE_TEXT, stroke_width=4)
        if box[2] - box[0] <= max_width and box[3] - box[1] <= max_height:
            return font
    return _title_font(32)


def _opening_scale(seconds: float) -> float:
    if seconds < 0.8:
        return 1.0
    progress = _smooth((seconds - 0.8) / (2.4 - 0.8))
    return 1.0 + 0.025 * progress


def _opening_stage(seconds: float) -> str:
    for start, end, name in _OPENING_STAGES:
        if start <= seconds < end:
            return name
    return _OPENING_STAGES[-1][2]


def _opening_camera(image: Image.Image, seconds: float) -> Image.Image:
    scale = _opening_scale(seconds)
    crop_width = max(1, min(WIDTH, round(WIDTH / scale)))
    crop_height = max(1, min(HEIGHT, round(HEIGHT / scale)))
    left = max(0, (WIDTH - crop_width) // 2)
    top = max(0, (HEIGHT - crop_height) // 2)
    return image.crop((left, top, left + crop_width, top + crop_height)).resize(
        (WIDTH, HEIGHT),
        Image.Resampling.BICUBIC,
    )


def _event_strength(seconds: float, start: float, end: float) -> float:
    if not start <= seconds <= end:
        return 0.0
    wave = max(0.0, math.sin(math.pi * (seconds - start) / (end - start)))
    return wave**0.7


def _draw_opening_ring(
    image: Image.Image,
    seconds: float,
) -> None:
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer, "RGBA")
    center_x = WIDTH // 2
    center_y = round(HEIGHT * 0.43)
    radius_x = round(WIDTH * 0.365)
    radius_y = round(HEIGHT * 0.405)
    rotation = seconds * 6.0

    for index in range(24):
        reveal = _smooth((seconds - 0.10 - index * 0.055) / 0.28)
        if reveal <= 0.0:
            continue
        start = rotation + index * 15
        pulse = 0.62 + 0.38 * math.sin(seconds * 4.2 + index * 0.7) ** 2
        color = RED if index % 3 else (255, 196, 83)
        draw.arc(
            (
                center_x - radius_x,
                center_y - radius_y,
                center_x + radius_x,
                center_y + radius_y,
            ),
            start=start,
            end=start + 8.5,
            fill=(*color, int(105 * reveal * pulse)),
            width=2,
        )

    for index in range(16):
        reveal = _smooth((seconds - 0.45 - index * 0.05) / 0.3)
        if reveal <= 0.0:
            continue
        angle = math.radians(rotation * 0.35 + index * 22.5)
        inner_x = center_x + math.cos(angle) * (radius_x + 22)
        inner_y = center_y + math.sin(angle) * (radius_y + 22)
        outer_x = center_x + math.cos(angle) * (radius_x + 38)
        outer_y = center_y + math.sin(angle) * (radius_y + 38)
        draw.line(
            (inner_x, inner_y, outer_x, outer_y),
            fill=(*RED, int(75 * reveal)),
            width=2 if index % 4 == 0 else 1,
        )

    for pulse_center in (1.28, 1.68):
        age = seconds - pulse_center
        if not 0.0 <= age <= 0.48:
            continue
        progress = _smooth(age / 0.48)
        ring_x = round(WIDTH * (0.16 + 0.36 * progress))
        ring_y = round(HEIGHT * (0.13 + 0.34 * progress))
        alpha = round(138 * (1.0 - progress))
        draw.ellipse(
            (
                center_x - ring_x,
                center_y - ring_y,
                center_x + ring_x,
                center_y + ring_y,
            ),
            outline=(*RED, alpha),
            width=max(1, round(4 * (1.0 - progress))),
        )

    ray_rotation = seconds * 10.0
    for index in range(18):
        angle = math.radians(ray_rotation + index * 20)
        inner_radius = min(WIDTH, HEIGHT) * 0.23
        outer_radius = min(WIDTH, HEIGHT) * (0.39 + 0.025 * math.sin(seconds * 2.0))
        alpha = 18 + 16 * (0.5 + 0.5 * math.sin(seconds * 3.4 + index))
        draw.line(
            (
                center_x + math.cos(angle) * inner_radius,
                center_y + math.sin(angle) * inner_radius,
                center_x + math.cos(angle) * outer_radius,
                center_y + math.sin(angle) * outer_radius,
            ),
            fill=(255, 179, 74, int(alpha)),
            width=1,
        )

    image.alpha_composite(layer)


def _draw_opening_convergence(image: Image.Image, seconds: float) -> None:
    progress = _smooth(seconds / 0.95)
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer, "RGBA")
    center_x = WIDTH / 2
    center_y = HEIGHT * 0.43
    random = np.random.default_rng(6105)
    for index in range(72):
        angle = random.uniform(0.0, math.tau)
        start_radius = min(WIDTH, HEIGHT) * random.uniform(0.42, 0.72)
        end_radius = min(WIDTH, HEIGHT) * random.uniform(0.02, 0.07)
        radius = start_radius + (end_radius - start_radius) * progress
        local = max(0.0, min(1.0, (progress - index / 130) / 0.72))
        x = center_x + math.cos(angle) * radius
        y = center_y + math.sin(angle) * radius
        trail = 9 + 22 * (1.0 - progress)
        dx = math.cos(angle) * trail
        dy = math.sin(angle) * trail
        color = (255, 197, 92) if index % 4 == 0 else RED
        alpha = round(36 + 92 * local)
        draw.line((x - dx, y - dy, x, y), fill=(*color, alpha), width=2)
        draw.ellipse((x - 2, y - 2, x + 2, y + 2), fill=(*color, alpha))
    image.alpha_composite(layer)


def _draw_opening_particles(image: Image.Image, seconds: float) -> None:
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer, "RGBA")
    for base_x, base_y, speed, phase, radius, kind in OPENING_PARTICLES:
        y = (base_y - seconds * speed) % 1.0
        x = (base_x + math.sin(seconds * 0.8 + phase) * 0.0035) % 1.0
        pixel_x = x * WIDTH
        pixel_y = y * HEIGHT
        alpha = int(24 + 44 * (0.5 + 0.5 * math.sin(seconds * 3.1 + phase)))
        color = RED if kind == 0 else (255, 198, 88) if kind == 1 else WARM_WHITE
        draw.ellipse(
            (
                pixel_x - radius,
                pixel_y - radius,
                pixel_x + radius,
                pixel_y + radius,
            ),
            fill=(*color, alpha),
        )
        if kind == 0 and int(seconds * 8 + phase) % 7 == 0:
            draw.line(
                (pixel_x, pixel_y, pixel_x + 18, pixel_y + 3),
                fill=(*RED, alpha // 2),
                width=1,
            )
    image.alpha_composite(layer)


def _draw_opening_sweeps(image: Image.Image, seconds: float) -> None:
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer, "RGBA")
    for start, end, direction, color_name in _OPENING_SWEEPS:
        strength = _event_strength(seconds, start, end)
        if strength <= 0.0:
            continue
        progress = (seconds - start) / (end - start)
        center_x = (-0.16 + 1.32 * progress) * WIDTH
        if direction < 0:
            center_x = WIDTH - center_x
        color = (
            (255, 216, 143)
            if color_name == "gold"
            else (255, 228, 220)
            if color_name == "white"
            else RED
        )
        for offset in range(-96, 97, 5):
            falloff = 1.0 - abs(offset) / 96
            alpha = max(0, round(38 * strength * falloff))
            if alpha <= 0:
                continue
            x = center_x + offset * direction
            draw.line(
                (x, -20, x + 116, HEIGHT + 20),
                fill=(*color, alpha),
                width=3 if abs(offset) < 32 else 2,
            )
        draw.line(
            (center_x, 0, center_x + 116, HEIGHT),
            fill=(*color, round(118 * strength)),
            width=2,
        )

    image.alpha_composite(layer)


def _draw_opening_burst(image: Image.Image, seconds: float) -> None:
    progress = _smooth((seconds - 4.20) / 1.05)
    strength = math.sin(math.pi * progress)
    center_x = WIDTH // 2
    center_y = round(HEIGHT * 0.43)
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer, "RGBA")
    for offset, color in ((-0.18, RED), (0.0, (255, 208, 118)), (0.18, RED)):
        local = max(0.0, min(1.0, progress + offset))
        radius_x = round(WIDTH * (0.08 + 0.40 * local))
        radius_y = round(HEIGHT * (0.07 + 0.37 * local))
        alpha = round(150 * (1.0 - local) * strength)
        draw.ellipse(
            (
                center_x - radius_x,
                center_y - radius_y,
                center_x + radius_x,
                center_y + radius_y,
            ),
            outline=(*color, alpha),
            width=max(1, round(5 * (1.0 - local))),
        )

    random = np.random.default_rng(4205)
    for _ in range(36):
        angle = random.uniform(0.0, math.tau)
        inner = min(WIDTH, HEIGHT) * (0.10 + 0.20 * progress)
        outer = inner + min(WIDTH, HEIGHT) * random.uniform(0.035, 0.13) * strength
        draw.line(
            (
                center_x + math.cos(angle) * inner,
                center_y + math.sin(angle) * inner,
                center_x + math.cos(angle) * outer,
                center_y + math.sin(angle) * outer,
            ),
            fill=(255, 194, 86, round(80 + 95 * strength)),
            width=2,
        )
    draw.rectangle(
        (0, 0, WIDTH, HEIGHT),
        fill=(255, 177, 91, round(22 * strength)),
    )
    image.alpha_composite(layer)


def _apply_opening_glitch(image: Image.Image, seconds: float) -> Image.Image:
    strength = 0.0
    for center, half_width in ((3.42, 0.22), (3.86, 0.18)):
        distance = abs(seconds - center)
        if distance < half_width:
            strength = max(strength, 1.0 - distance / half_width)
    if strength <= 0.0:
        return image

    result = image.copy()
    random = np.random.default_rng(round(seconds * 1000) + 2187)
    for _ in range(4 + round(7 * strength)):
        top = int(random.integers(35, HEIGHT - 80))
        height = int(random.integers(5, 24))
        shift = int(random.normal(0.0, 12.0 + 34.0 * strength))
        strip = image.crop((0, top, WIDTH, min(HEIGHT, top + height)))
        result.paste(strip, (shift, top))
    red, green, blue = result.split()
    red = ImageChops.offset(red, round(6 * strength), 0)
    blue = ImageChops.offset(blue, -round(4 * strength), 0)
    shifted = Image.merge("RGB", (red, green, blue))
    return Image.blend(result, shifted, 0.30 * strength)


def _draw_opening_side_rails(image: Image.Image, seconds: float) -> None:
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer, "RGBA")
    reveal = _smooth((seconds - 0.25) / 0.8)
    if reveal <= 0.0:
        return
    active = int((seconds * 9) % 18)
    for side, x in (("left", 54), ("right", WIDTH - 54)):
        draw.line(
            (x, 112, x, HEIGHT - 94),
            fill=(*RED, int(52 * reveal)),
            width=1,
        )
        for index in range(18):
            y = 124 + index * 45
            if y > HEIGHT - 98:
                break
            length = 20 if index == active else 9
            direction = 1 if side == "left" else -1
            draw.line(
                (x, y, x + direction * length, y),
                fill=(*RED, int((135 if index == active else 62) * reveal)),
                width=2 if index == active else 1,
            )
        draw.text(
            (x, HEIGHT - 70),
            f"NODE {int(seconds * 10):02d}",
            font=_title_font(15),
            fill=(*WARM_WHITE, int(118 * reveal)),
            anchor="ma",
        )
    image.alpha_composite(layer)


def _draw_opening_scan(image: Image.Image, seconds: float) -> None:
    progress = _smooth((seconds - 5.30) / 1.10)
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer, "RGBA")
    scan_y = round(HEIGHT * (0.04 + 0.92 * progress))
    for offset in range(-28, 29, 2):
        alpha = max(0, round(74 * (1.0 - abs(offset) / 28)))
        draw.line(
            (0, scan_y + offset, WIDTH, scan_y + offset),
            fill=(*RED, alpha),
            width=2,
        )
    draw.line(
        (0, scan_y, WIDTH, scan_y),
        fill=(*WARM_WHITE, 152),
        width=2,
    )
    for index in range(22):
        x = round(index * WIDTH / 21)
        height = 8 + 28 * (0.5 + 0.5 * math.sin(seconds * 5.0 + index))
        draw.line(
            (x, scan_y + 34, x, scan_y + 34 + height),
            fill=(*RED, 62),
            width=1,
        )
    image.alpha_composite(layer)


def _draw_opening_charge(image: Image.Image, seconds: float) -> None:
    progress = _smooth((seconds - 6.40) / 0.80)
    center_x = WIDTH // 2
    center_y = round(HEIGHT * 0.43)
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer, "RGBA")
    random = np.random.default_rng(6403)
    for index in range(26):
        angle = random.uniform(0.0, math.tau)
        outer = min(WIDTH, HEIGHT) * random.uniform(0.34, 0.58)
        inner = min(WIDTH, HEIGHT) * random.uniform(0.16, 0.28)
        points = []
        for step in range(6):
            radius = outer + (inner - outer) * step / 5
            jitter = 0.0 if step in (0, 5) else random.normal(0.0, 10.0)
            points.append(
                (
                    center_x + math.cos(angle) * radius + jitter,
                    center_y + math.sin(angle) * radius + jitter * 0.7,
                )
            )
        color = (255, 203, 102) if index % 3 == 0 else RED
        draw.line(
            points,
            fill=(*color, round(58 + 120 * progress)),
            width=2,
        )
    radius = round(52 + 24 * progress)
    draw.ellipse(
        (
            center_x - radius,
            center_y - radius,
            center_x + radius,
            center_y + radius,
        ),
        outline=(*WARM_WHITE, round(85 + 100 * progress)),
        width=3,
    )
    image.alpha_composite(layer)


def _render_opening_frame(frame: Image.Image, seconds: float) -> Image.Image:
    """在保留荣耀主画面的前提下增加分层动态，并锁定开场尺度。"""
    image = _opening_camera(frame.convert("RGB"), seconds)
    reveal = _smooth((seconds - 0.02) / 0.36)
    heartbeat = 0.012 * math.sin(seconds * math.tau * 1.8) ** 2
    image = ImageEnhance.Brightness(image).enhance((0.92 + 0.08 * reveal) + heartbeat)
    image = ImageEnhance.Contrast(image).enhance(1.015)

    rgba = image.convert("RGBA")
    stage = _opening_stage(seconds)
    if stage == "converge":
        _draw_opening_convergence(rgba, seconds)
    elif stage == "ring":
        _draw_opening_ring(rgba, seconds)
        _draw_opening_particles(rgba, seconds)
    elif stage == "sweep":
        _draw_opening_sweeps(rgba, seconds)
        _draw_opening_particles(rgba, seconds)
    elif stage == "glitch":
        _draw_opening_particles(rgba, seconds)
    elif stage == "burst":
        _draw_opening_burst(rgba, seconds)
        _draw_opening_particles(rgba, seconds)
    elif stage == "scan":
        _draw_opening_side_rails(rgba, seconds)
        _draw_opening_scan(rgba, seconds)
    elif stage == "charge":
        _draw_opening_ring(rgba, seconds)
        _draw_opening_charge(rgba, seconds)
    return _apply_opening_glitch(rgba.convert("RGB"), seconds)


def _replace_title_region(frame: Image.Image, clean_frame: Image.Image) -> Image.Image:
    """用标题出现前的同场景画面覆盖旧“十区”，保留柔和接缝。"""
    result = frame.convert("RGBA")
    clean = clean_frame.convert("RGBA")
    left, top, right, bottom = TITLE_REGION
    feather = 28
    paste_region = (
        max(0, left - feather),
        max(0, top - feather),
        min(WIDTH, right + feather),
        min(HEIGHT, bottom + feather),
    )
    mask = Image.new("L", result.size, 0)
    ImageDraw.Draw(mask).rectangle(paste_region, fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(feather))
    ImageDraw.Draw(mask).rectangle((left, top, right, bottom), fill=255)
    result.paste(
        clean.crop(paste_region),
        paste_region[:2],
        mask.crop(paste_region),
    )
    return result.convert("RGB")


def _title_pattern(size: tuple[int, int], mask: Image.Image) -> Image.Image:
    pattern = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(pattern, "RGBA")
    for y in range(0, size[1], 5):
        draw.line((0, y, size[0], y), fill=(*RED, 132), width=1)
    for x in range(0, size[0], 9):
        draw.line((x, 0, x, size[1]), fill=(*RED, 64), width=1)

    random = np.random.default_rng(20261105)
    left, top, right, bottom = TITLE_SAFE_REGION
    for _ in range(900):
        x = int(random.integers(max(0, left - 4), min(size[0], right + 4)))
        y = int(random.integers(max(0, top - 4), min(size[1], bottom + 4)))
        if mask.getpixel((x, y)) < 220:
            continue
        radius = 1 if int(random.integers(0, 5)) else 2
        draw.ellipse(
            (x - radius, y - radius, x + radius, y + radius),
            fill=(*WARM_WHITE, int(random.integers(205, 255))),
        )

    pattern.putalpha(ImageChops.multiply(pattern.getchannel("A"), mask))
    return pattern


def _draw_custom_title(
    image: Image.Image,
    *,
    reveal: float,
    glitch: float,
) -> Image.Image:
    """绘制与十区界面一致的红色点阵/扫描标题。"""
    reveal = min(1.0, max(0.0, reveal))
    if reveal <= 0.0:
        return image.copy()

    left, top, right, bottom = TITLE_SAFE_REGION
    center = ((left + right) // 2, (top + bottom) // 2)
    font = _fit_title_font()
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer, "RGBA")

    glow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow, "RGBA")
    glow_draw.text(
        center,
        TITLE_TEXT,
        font=font,
        fill=(*RED, 132),
        stroke_width=8,
        stroke_fill=(*RED, 72),
        anchor="mm",
    )
    layer.alpha_composite(glow.filter(ImageFilter.GaussianBlur(8)))

    draw.text(
        center,
        TITLE_TEXT,
        font=font,
        fill=(*RED_DARK, 178),
        stroke_width=4,
        stroke_fill=(*RED, 255),
        anchor="mm",
    )

    mask = Image.new("L", image.size, 0)
    ImageDraw.Draw(mask).text(center, TITLE_TEXT, font=font, fill=255, anchor="mm")
    layer.alpha_composite(_title_pattern(image.size, mask))

    if glitch > 0.0:
        random = np.random.default_rng(20261105)
        for _ in range(3 + round(4 * glitch)):
            strip_top = int(random.integers(top + 18, bottom - 28))
            strip_height = int(random.integers(8, 24))
            shift = int(random.normal(0.0, 12.0 + 24.0 * glitch))
            strip = layer.crop((left, strip_top, right, strip_top + strip_height))
            layer.alpha_composite(strip, (left + shift, strip_top))

    if reveal < 1.0:
        layer.putalpha(layer.getchannel("A").point(lambda value: round(value * reveal)))
    return Image.alpha_composite(image.convert("RGBA"), layer).convert("RGB")


def _prepare_ending_frame(
    frame: Image.Image,
    clean_frame: Image.Image,
    *,
    reveal: float,
    glitch: float,
) -> Image.Image:
    prepared = _replace_title_region(frame, clean_frame)
    return _draw_custom_title(prepared, reveal=reveal, glitch=glitch)


def _iter_prepared_ending_frames(
    frames: Sequence[Image.Image],
    clean_frame: Image.Image | None,
    *,
    ending_count: int,
) -> Iterator[Image.Image]:
    reveal_frames = min(max(1, round(0.23 * FPS)), ending_count)
    for index, frame in enumerate(
        _resample_ending_frames(frames, ending_count)
    ):
        reveal = _smooth((index + 1) / reveal_frames)
        if clean_frame is None:
            yield _draw_custom_title(frame.copy(), reveal=reveal, glitch=0.0)
        else:
            yield _prepare_ending_frame(
                frame,
                clean_frame,
                reveal=reveal,
                glitch=0.0,
            )


def _resample_ending_frames(
    frames: Sequence[Image.Image],
    output_count: int,
) -> Iterator[Image.Image]:
    """把短结尾素材重采样到目标时长，并在动作结束后稳定停留。"""
    if not frames:
        raise ValueError("结尾画面不能为空")
    if output_count <= 0:
        return

    motion_count = min(output_count, ENDING_MOTION_FRAME_COUNT)
    if motion_count == 1 or len(frames) == 1:
        for _ in range(output_count):
            yield frames[-1].copy()
        return

    for index in range(motion_count):
        source_index = round(index * (len(frames) - 1) / (motion_count - 1))
        yield frames[source_index].copy()
    for _ in range(motion_count, output_count):
        yield frames[-1].copy()


def _iter_resampled_ending(
    frames: Sequence[Image.Image],
) -> Iterator[Image.Image]:
    yield from _resample_ending_frames(frames, ENDING_FRAME_COUNT)


def _iter_bridge_frames(
    base: Image.Image,
    ending: Image.Image,
    *,
    frame_count: int = BRIDGE_FRAME_COUNT,
) -> Iterator[Image.Image]:
    """用线性混合和轻微红闪桥接两种不同亮度的画面。"""
    if frame_count <= 0:
        return
    base = base.convert("RGB")
    ending = ending.convert("RGB")
    for index in range(frame_count):
        progress = (index + 1) / frame_count
        blended = Image.blend(base, ending, progress)
        flash_alpha = round(18 * math.sin(math.pi * progress))
        if flash_alpha:
            flash = Image.new("RGBA", blended.size, (*RED, flash_alpha))
            blended = Image.alpha_composite(blended.convert("RGBA"), flash).convert(
                "RGB"
            )
        yield blended


def _assemble_frames(
    base_frames: Sequence[Image.Image],
    ending_frames: Sequence[Image.Image],
    clean_frame: Image.Image | None = None,
) -> list[Image.Image]:
    if not base_frames or not ending_frames:
        raise ValueError("基础画面和十区画面都不能为空")

    ending_count = min(ENDING_FRAME_COUNT, TOTAL_FRAMES)
    bridge_count = min(BRIDGE_FRAME_COUNT, max(1, ending_count // 4))
    base_count = max(1, TOTAL_FRAMES - ending_count - bridge_count)
    selected_base = list(base_frames[:base_count])
    if not selected_base:
        raise ValueError("基础画面数量不足")
    while len(selected_base) < base_count:
        selected_base.append(selected_base[-1].copy())

    ending_iterator = _iter_prepared_ending_frames(
        ending_frames,
        clean_frame,
        ending_count=ending_count,
    )
    first_ending = next(ending_iterator)
    result = selected_base + list(
        _iter_bridge_frames(
            selected_base[-1],
            first_ending,
            frame_count=bridge_count,
        )
    )
    result.append(first_ending)
    result.extend(ending_iterator)

    return result[:TOTAL_FRAMES]


def _ffmpeg() -> str:
    return imageio_ffmpeg.get_ffmpeg_exe()


def _iter_video_frames(
    video: Path,
    *,
    start: float,
    duration: float,
) -> Iterator[Image.Image]:
    command = [
        _ffmpeg(),
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(video),
        "-ss",
        f"{start:.6f}",
        "-t",
        f"{duration:.6f}",
        "-vf",
        f"fps={FPS},scale={WIDTH}:{HEIGHT}:flags=lanczos",
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
        if return_code != 0 and "Broken pipe" not in error:
            raise RuntimeError(f"FFmpeg 视频解码失败: {error}")


def _load_ending_frames(video: Path) -> tuple[Image.Image, ...]:
    frames = tuple(
        _iter_video_frames(
            video,
            start=TEN_ZONE_SOURCE_START,
            duration=TEN_ZONE_SOURCE_END - TEN_ZONE_SOURCE_START,
        )
    )
    if not frames:
        raise RuntimeError("十区视频中没有可用画面")
    return frames


def _load_clean_frame(video: Path) -> Image.Image:
    frame = next(
        _iter_video_frames(
            video,
            start=CLEAN_SOURCE_TIME,
            duration=1.0 / FPS,
        ),
        None,
    )
    if frame is None:
        raise RuntimeError("无法取得标题出现前的干净底图")
    return frame


def _start_encoder(output: Path) -> subprocess.Popen[bytes]:
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


def _render_video(
    base_video: Path,
    ending_frames: Sequence[Image.Image],
    clean_frame: Image.Image,
    output: Path,
) -> None:
    ending_count = min(ENDING_FRAME_COUNT, TOTAL_FRAMES)
    bridge_count = min(BRIDGE_FRAME_COUNT, max(1, ending_count // 4))
    base_target = max(0, TOTAL_FRAMES - ending_count - bridge_count)
    process = _start_encoder(output)
    written = 0
    last_base: Image.Image | None = None
    try:
        for frame in _iter_video_frames(
            base_video,
            start=0.0,
            duration=base_target / FPS,
        ):
            if written >= base_target:
                break
            _write_frame(process, _render_opening_frame(frame, written / FPS))
            last_base = frame
            written += 1
        if last_base is None:
            raise RuntimeError("基础视频中没有可用画面")
        while written < base_target:
            _write_frame(
                process,
                _render_opening_frame(last_base, written / FPS),
            )
            written += 1

        ending_iterator = _iter_prepared_ending_frames(
            ending_frames,
            clean_frame,
            ending_count=ending_count,
        )
        first_ending = next(ending_iterator)
        rendered_base = _render_opening_frame(last_base, written / FPS)
        for bridge in _iter_bridge_frames(
            rendered_base,
            first_ending,
            frame_count=bridge_count,
        ):
            _write_frame(process, bridge)
            written += 1

        _write_frame(process, first_ending)
        written += 1
        for ending in ending_iterator:
            _write_frame(process, ending)
            written += 1
    finally:
        _finish_encoder(process)

    if written != TOTAL_FRAMES:
        raise RuntimeError(f"成片帧数不正确: {written}/{TOTAL_FRAMES}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-video", type=Path, required=True)
    parser.add_argument("--ten-zone-video", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    arguments = parser.parse_args()

    if not arguments.base_video.is_file():
        raise FileNotFoundError(arguments.base_video)
    if not arguments.ten_zone_video.is_file():
        raise FileNotFoundError(arguments.ten_zone_video)
    arguments.out_dir.mkdir(parents=True, exist_ok=True)

    clean_frame = _load_clean_frame(arguments.ten_zone_video)
    ending_frames = _load_ending_frames(arguments.ten_zone_video)
    _render_video(
        arguments.base_video,
        ending_frames,
        clean_frame,
        arguments.out_dir / "lookdev.mp4",
    )
    ending = _replace_title_region(ending_frames[-1], clean_frame)
    _draw_custom_title(ending, reveal=1.0, glitch=0.0).save(
        arguments.out_dir / "ending-frame.png",
        optimize=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
