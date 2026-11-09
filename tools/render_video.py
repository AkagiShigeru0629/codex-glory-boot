import argparse
import math
import subprocess
from pathlib import Path

import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont


WIDTH = 1920
HEIGHT = 1080
FPS = 60
DURATION = 8.0
TOTAL_FRAMES = int(FPS * DURATION)

GOLD = (203, 164, 87)
GOLD_LIGHT = (237, 218, 164)
IVORY = (232, 230, 216)
INK_GREEN = (14, 31, 23)
MINT = (65, 145, 105)
SCAN_GREEN = (67, 168, 112)


def _clamp(value: float) -> float:
    return min(1.0, max(0.0, value))


def _ease(value: float) -> float:
    value = _clamp(value)
    return 1 - (1 - value) ** 3


def _lerp(start: float, end: float, progress: float) -> float:
    return start + (end - start) * progress


def _font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        Path(
            r"C:\Windows\Fonts\msyhbd.ttc" if bold else r"C:\Windows\Fonts\msyh.ttc"
        ),
        Path(r"C:\Windows\Fonts\simhei.ttf"),
    ]
    for path in candidates:
        if path.is_file():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def _with_opacity(image: Image.Image, opacity: float) -> Image.Image:
    result = image.copy()
    alpha = result.getchannel("A")
    result.putalpha(alpha.point(lambda value: int(value * _clamp(opacity))))
    return result


def _create_background() -> Image.Image:
    width, height = 2040, 1148
    x = np.linspace(-1.0, 1.0, width, dtype=np.float32)[None, :]
    y = np.linspace(-1.0, 1.0, height, dtype=np.float32)[:, None]
    distance = np.sqrt((x * 0.82) ** 2 + (y * 1.08 + 0.08) ** 2)
    radial = np.clip(1.0 - distance / 1.32, 0.0, 1.0)
    lower_glow = np.clip(1.0 - np.abs(y - 0.58) / 0.72, 0.0, 1.0)
    red = 3.5 + radial * 4.0 + lower_glow * 1.5
    green = 8.0 + radial * 16.0 + lower_glow * 7.0
    blue = 7.0 + radial * 10.0 + lower_glow * 3.0
    background = Image.fromarray(
        np.stack([red, green, blue], axis=2).clip(0, 255).astype(np.uint8),
        "RGB",
    ).convert("RGBA")

    smoke = Image.new("RGBA", background.size, (0, 0, 0, 0))
    smoke_draw = ImageDraw.Draw(smoke, "RGBA")
    random = np.random.default_rng(812_2026)
    for index in range(34):
        center_x = int(random.integers(-180, width + 180))
        center_y = int(random.integers(60, height - 40))
        radius_x = int(random.integers(150, 430))
        radius_y = int(random.integers(70, 210))
        color = (
            int(random.integers(10, 28)),
            int(random.integers(36, 74)),
            int(random.integers(24, 48)),
            int(random.integers(5, 13)),
        )
        smoke_draw.ellipse(
            (
                center_x - radius_x,
                center_y - radius_y,
                center_x + radius_x,
                center_y + radius_y,
            ),
            fill=color,
        )
        if index % 4 == 0:
            smoke_draw.arc(
                (
                    center_x - radius_x,
                    center_y - radius_y,
                    center_x + radius_x,
                    center_y + radius_y,
                ),
                int(random.integers(0, 160)),
                int(random.integers(210, 350)),
                fill=(104, 82, 43, 12),
                width=2,
            )
    smoke = smoke.filter(ImageFilter.GaussianBlur(48))
    background.alpha_composite(smoke)

    metal = Image.new("RGBA", background.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(metal, "RGBA")
    for offset in range(-7, 8):
        x_pos = width // 2 + offset * 112
        alpha = 10 + (abs(offset) % 3) * 2
        draw.line(
            (x_pos, -20, x_pos - 520, height + 20),
            fill=(155, 122, 63, alpha),
            width=1,
        )
    for y_pos in (142, 932):
        draw.line((0, y_pos, width, y_pos), fill=(99, 139, 105, 8), width=1)
    background.alpha_composite(metal)
    return background.filter(ImageFilter.GaussianBlur(0.35))


def _bezier(
    start: tuple[float, float],
    control_a: tuple[float, float],
    control_b: tuple[float, float],
    end: tuple[float, float],
    steps: int = 36,
) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for index in range(steps + 1):
        t = index / steps
        inverse = 1 - t
        x = (
            inverse**3 * start[0]
            + 3 * inverse**2 * t * control_a[0]
            + 3 * inverse * t**2 * control_b[0]
            + t**3 * end[0]
        )
        y = (
            inverse**3 * start[1]
            + 3 * inverse**2 * t * control_a[1]
            + 3 * inverse * t**2 * control_b[1]
            + t**3 * end[1]
        )
        points.append((x, y))
    return points


def _draw_emblem(image: Image.Image, seconds: float) -> None:
    assemble = _clamp((seconds - 0.5) / 1.9)
    if assemble <= 0:
        return

    layer = Image.new("RGBA", (930, 650), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer, "RGBA")
    center_x, center_y = 465, 318
    wing_reveal = _ease((seconds - 0.72) / 1.35)
    ring_reveal = _clamp((seconds - 0.58) / 1.65)
    core_reveal = _ease((seconds - 2.12) / 0.68)
    pulse = (
        _clamp((seconds - 2.35) / 0.7)
        * (0.55 + 0.45 * math.sin(max(0.0, seconds - 2.35) * 4.2) ** 2)
    )

    wing_alpha = int(225 * wing_reveal)
    if wing_alpha:
        for side in (-1, 1):
            for feather in range(4):
                start = (
                    center_x + side * (118 + feather * 11),
                    center_y - 78 + feather * 34,
                )
                end = (
                    center_x + side * (420 + feather * 39),
                    center_y - 148 + feather * 70,
                )
                control_a = (
                    center_x + side * 205,
                    center_y - 210 + feather * 30,
                )
                control_b = (
                    center_x + side * (340 + feather * 23),
                    center_y - 188 + feather * 48,
                )
                points = _bezier(start, control_a, control_b, end)
                draw.line(
                    points,
                    fill=(*GOLD, max(35, wing_alpha - feather * 24)),
                    width=7 - feather,
                    joint="curve",
                )
                draw.line(
                    [(x, y + 3) for x, y in points],
                    fill=(*GOLD_LIGHT, max(18, wing_alpha - 90 - feather * 18)),
                    width=1,
                )
            draw.arc(
                (
                    center_x - 270,
                    center_y - 174,
                    center_x + 270,
                    center_y + 142,
                ),
                198 if side < 0 else 342,
                342 if side < 0 else 486,
                fill=(*GOLD, int(wing_alpha * 0.64)),
                width=3,
            )

    ring_box = (
        center_x - 218,
        center_y - 218,
        center_x + 218,
        center_y + 218,
    )
    inner_box = (
        center_x - 184,
        center_y - 184,
        center_x + 184,
        center_y + 184,
    )
    segments = 16
    for index in range(segments):
        local = _clamp(ring_reveal * segments - index)
        if local <= 0:
            continue
        start = -90 + index * (360 / segments) + (1 - local) * 7
        end = start + (360 / segments) - 4.2
        radius_shift = int((1 - local) * 11)
        draw.arc(
            (
                ring_box[0] + radius_shift,
                ring_box[1] + radius_shift,
                ring_box[2] - radius_shift,
                ring_box[3] - radius_shift,
            ),
            start,
            end,
            fill=(*GOLD, int(235 * local)),
            width=6,
        )
        draw.arc(
            (
                inner_box[0] + radius_shift,
                inner_box[1] + radius_shift,
                inner_box[2] - radius_shift,
                inner_box[3] - radius_shift,
            ),
            start + 2.5,
            end - 2.5,
            fill=(*MINT, int(115 * local)),
            width=2,
        )
    for angle in range(0, 360, 30):
        radians = math.radians(angle)
        inner = 205
        outer = 224
        x1 = center_x + math.cos(radians) * inner
        y1 = center_y + math.sin(radians) * inner
        x2 = center_x + math.cos(radians) * outer
        y2 = center_y + math.sin(radians) * outer
        draw.line((x1, y1, x2, y2), fill=(*GOLD_LIGHT, int(185 * ring_reveal)), width=3)

    if core_reveal > 0:
        shield = [
            (center_x, center_y - 162),
            (center_x + 104, center_y - 92),
            (center_x + 83, center_y + 83),
            (center_x, center_y + 151),
            (center_x - 83, center_y + 83),
            (center_x - 104, center_y - 92),
        ]
        draw.polygon(
            shield,
            fill=(12, 31, 23, int(205 * core_reveal)),
            outline=(*GOLD, int(235 * core_reveal)),
        )
        inner_shield = [
            (center_x, center_y - 139),
            (center_x + 83, center_y - 78),
            (center_x + 63, center_y + 65),
            (center_x, center_y + 126),
            (center_x - 63, center_y + 65),
            (center_x - 83, center_y - 78),
        ]
        draw.line(
            inner_shield + [inner_shield[0]],
            fill=(*GOLD_LIGHT, int(155 * core_reveal)),
            width=2,
        )
        star = []
        for point_index in range(16):
            angle = math.radians(-90 + point_index * 22.5)
            radius = 76 if point_index % 2 == 0 else 31
            star.append(
                (
                    center_x + math.cos(angle) * radius,
                    center_y + math.sin(angle) * radius,
                )
            )
        draw.polygon(
            star,
            fill=(*GOLD_LIGHT, int(235 * core_reveal)),
            outline=(*GOLD, int(255 * core_reveal)),
        )
        draw.ellipse(
            (
                center_x - 16,
                center_y - 16,
                center_x + 16,
                center_y + 16,
            ),
            fill=(*INK_GREEN, int(230 * core_reveal)),
            outline=(*GOLD_LIGHT, int(230 * core_reveal)),
            width=2,
        )

    scale = _lerp(0.83, 1.0, _ease(assemble))
    scaled_size = (
        max(1, int(layer.width * scale)),
        max(1, int(layer.height * scale)),
    )
    scaled = layer.resize(scaled_size, Image.Resampling.LANCZOS)
    scaled = _with_opacity(scaled, _ease(assemble))
    paste_x = WIDTH // 2 - scaled.width // 2
    paste_y = 460 - scaled.height // 2

    if pulse > 0:
        mask = scaled.getchannel("A").filter(ImageFilter.GaussianBlur(26))
        glow = Image.new("RGBA", scaled.size, (*GOLD, 0))
        glow.putalpha(mask.point(lambda value: int(value * pulse * 0.54)))
        image.alpha_composite(glow, (paste_x, paste_y))
    image.alpha_composite(scaled, (paste_x, paste_y))


def _draw_data_stream(
    draw: ImageDraw.ImageDraw,
    seconds: float,
    intensity: float,
) -> None:
    if intensity <= 0:
        return
    for index in range(56):
        x = (index * 197 + int(seconds * (12 + index % 7) * 6)) % WIDTH
        y = (index * 149 + int(seconds * 31)) % HEIGHT
        length = 18 + (index * 23) % 128
        alpha = int((12 + index % 9 * 3) * intensity)
        color = (92, 154, 104, alpha) if index % 5 else (173, 139, 76, alpha)
        draw.line((x, y, x, y + length), fill=color, width=1)
        if index % 8 == 0:
            draw.ellipse(
                (x - 3, y - 3, x + 3, y + 3),
                fill=(*SCAN_GREEN, min(120, alpha * 3)),
            )


def _draw_scan_layer(image: Image.Image, seconds: float, opacity: float) -> None:
    if opacity <= 0:
        return
    scan = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(scan, "RGBA")
    y = int((seconds * 188) % (HEIGHT + 160)) - 80
    draw.rectangle(
        (0, y, WIDTH, y + 2),
        fill=(*SCAN_GREEN, int(42 * opacity)),
    )
    draw.rectangle(
        (0, y + 3, WIDTH, y + 18),
        fill=(*MINT, int(9 * opacity)),
    )
    for line_y in range(0, HEIGHT, 6):
        draw.line((0, line_y, WIDTH, line_y), fill=(0, 0, 0, 8))
    image.alpha_composite(scan)


def _draw_status_panel(seconds: float) -> Image.Image:
    panel = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(panel, "RGBA")
    left, top, right, bottom = 286, 914, 1634, 1023
    reveal = _ease((seconds - 4.25) / 1.0)
    if reveal <= 0:
        return panel

    draw.rounded_rectangle(
        (left, top, right, bottom),
        radius=12,
        fill=(4, 11, 9, int(188 * reveal)),
        outline=(*GOLD, int(125 * reveal)),
        width=2,
    )
    draw.line(
        (left + 18, top + 10, left + 250, top + 10),
        fill=(*GOLD_LIGHT, int(210 * reveal)),
        width=3,
    )
    draw.line(
        (right - 250, bottom - 10, right - 18, bottom - 10),
        fill=(*GOLD, int(180 * reveal)),
        width=2,
    )

    crest = [(338, 958), (361, 943), (384, 958), (379, 988), (338, 988)]
    draw.polygon(
        crest,
        fill=(*INK_GREEN, int(235 * reveal)),
        outline=(*GOLD, int(210 * reveal)),
    )
    draw.text(
        (407, 939),
        "荣耀启动协议",
        font=STATUS_TITLE_FONT,
        fill=(*IVORY, int(245 * reveal)),
        anchor="la",
    )
    draw.text(
        (408, 985),
        "GLORY / CODEX ZERO-WAIT LINK",
        font=STATUS_LABEL_FONT,
        fill=(*MINT, int(210 * reveal)),
        anchor="la",
    )

    pulse = 0.5 + 0.5 * math.sin(seconds * 5.5)
    dot_color = (*SCAN_GREEN, int((165 + pulse * 85) * reveal))
    draw.ellipse((1270, 956, 1286, 972), fill=dot_color)
    draw.text(
        (1302, 940),
        "CODEX 正在唤醒",
        font=STATUS_TEXT_FONT,
        fill=(*IVORY, int(238 * reveal)),
        anchor="la",
    )
    draw.text(
        (1302, 986),
        "ESC  跳过动画",
        font=STATUS_LABEL_FONT,
        fill=(*GOLD_LIGHT, int(190 * reveal)),
        anchor="la",
    )

    progress = int((840 + 60 * math.sin(seconds * 0.8)) % 840)
    draw.line(
        (530, bottom - 7, 530 + progress, bottom - 7),
        fill=(*SCAN_GREEN, int(125 * reveal)),
        width=2,
    )
    return panel


def _transition_rect(seconds: float) -> tuple[float, float, float, float] | None:
    if seconds < 6.8:
        return None
    progress = _clamp((seconds - 6.8) / 0.8)
    eased = _ease(progress)
    x = _lerp(0.28, 0.0, eased) * WIDTH
    y = _lerp(0.12, 0.0, eased) * HEIGHT
    width = _lerp(0.44, 1.0, eased) * WIDTH
    height = _lerp(0.76, 1.0, eased) * HEIGHT
    return x, y, width, height


def _draw_transition(draw: ImageDraw.ImageDraw, seconds: float) -> None:
    rect = _transition_rect(seconds)
    if rect is None:
        return
    x, y, width, height = rect
    right = x + width
    bottom = y + height
    progress = _clamp((seconds - 6.8) / 0.8)
    fade = 1.0 - progress

    draw.rectangle((0, 0, WIDTH, y), fill=(2, 7, 5, int(96 * fade)))
    draw.rectangle((0, bottom, WIDTH, HEIGHT), fill=(2, 7, 5, int(96 * fade)))
    draw.rectangle((0, y, x, bottom), fill=(2, 7, 5, int(96 * fade)))
    draw.rectangle((right, y, WIDTH, bottom), fill=(2, 7, 5, int(96 * fade)))
    draw.rectangle(
        (x, y, right, bottom),
        outline=(*GOLD_LIGHT, int(235 * (1 - progress * 0.45))),
        width=max(2, int(7 * (1 - progress) + 2)),
    )
    corner = 86
    for corner_x, corner_y, dx, dy in (
        (x, y, 1, 1),
        (right, y, -1, 1),
        (x, bottom, 1, -1),
        (right, bottom, -1, -1),
    ):
        draw.line(
            (corner_x, corner_y, corner_x + dx * corner, corner_y),
            fill=(*SCAN_GREEN, int(220 * (1 - progress * 0.35))),
            width=4,
        )
        draw.line(
            (corner_x, corner_y, corner_x, corner_y + dy * corner),
            fill=(*SCAN_GREEN, int(220 * (1 - progress * 0.35))),
            width=4,
        )


BACKGROUND = _create_background()
TITLE_FONT = _font(104, bold=True)
SUBTITLE_FONT = _font(24)
TAGLINE_FONT = _font(32)
STATUS_TITLE_FONT = _font(30, bold=True)
STATUS_TEXT_FONT = _font(24)
STATUS_LABEL_FONT = _font(17)


def render_frame(seconds: float) -> Image.Image:
    pan_x = int(28 + 26 * math.sin(seconds * 0.38))
    pan_y = int(28 + 12 * math.cos(seconds * 0.27))
    image = BACKGROUND.crop((pan_x, pan_y, pan_x + WIDTH, pan_y + HEIGHT)).copy()
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay, "RGBA")

    _draw_data_stream(draw, seconds, _clamp((seconds - 0.08) / 0.9))
    _draw_emblem(image, seconds)

    title_reveal = _ease((seconds - 4.15) / 0.95)
    if title_reveal > 0:
        draw.text(
            (WIDTH // 2, 103),
            "荣耀",
            font=TITLE_FONT,
            fill=(*IVORY, int(255 * title_reveal)),
            anchor="mm",
        )
        draw.line(
            (WIDTH // 2 - 142, 168, WIDTH // 2 + 142, 168),
            fill=(*GOLD, int(210 * title_reveal)),
            width=2,
        )
        draw.text(
            (WIDTH // 2, 200),
            "GLORY // CODEX",
            font=SUBTITLE_FONT,
            fill=(*GOLD_LIGHT, int(205 * title_reveal)),
            anchor="mm",
        )
        draw.text(
            (WIDTH // 2, 730),
            "以荣耀之名，唤醒智能核心",
            font=TAGLINE_FONT,
            fill=(*IVORY, int(225 * title_reveal)),
            anchor="mm",
        )

    _draw_scan_layer(
        image,
        seconds,
        _clamp((seconds - 0.2) / 0.8) * (1 - _clamp((seconds - 6.8) / 0.8)),
    )
    image.alpha_composite(overlay)

    status_panel = _draw_status_panel(seconds)
    image.alpha_composite(status_panel)

    transition_overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    transition_draw = ImageDraw.Draw(transition_overlay, "RGBA")
    _draw_transition(transition_draw, seconds)
    image.alpha_composite(transition_overlay)
    return image.convert("RGB")


def render_poster(output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    render_frame(4.8).save(output, optimize=True)


def render_video(output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
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
        raise RuntimeError("无法打开 FFmpeg 输入管道")
    try:
        for frame_index in range(TOTAL_FRAMES):
            frame = np.asarray(render_frame(frame_index / FPS), dtype=np.uint8)
            process.stdin.write(frame.tobytes())
    finally:
        process.stdin.close()
    stderr = (
        process.stderr.read().decode("utf-8", errors="replace")
        if process.stderr
        else ""
    )
    return_code = process.wait()
    if return_code != 0:
        raise RuntimeError(f"FFmpeg 编码失败: {stderr}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--poster", type=Path, default=Path("media/poster.png"))
    parser.add_argument("--video", type=Path, default=Path("media/startup.mp4"))
    arguments = parser.parse_args()
    render_poster(arguments.poster)
    render_video(arguments.video)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
