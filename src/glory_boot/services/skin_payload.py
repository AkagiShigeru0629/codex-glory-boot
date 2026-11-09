import base64
import json
from dataclasses import dataclass
from pathlib import Path


MAX_WALLPAPER_BYTES = 20 * 1024 * 1024
_RESOURCE_ROOT = Path(__file__).resolve().parents[1] / "resources"
_DETECT_EXPRESSION = """(() => {
    const state = globalThis.__gloryBootSkin;
    return Boolean(
        state?.installed &&
        state?.wallpaperUrl &&
        document.getElementById("glory-boot-skin-style") &&
        document.documentElement.getAttribute("data-glory-boot-skin") === "active" &&
        getComputedStyle(document.body).backgroundImage.includes("blob:")
    );
})()"""
_RESTORE_EXPRESSION = """(() => {
    return globalThis.__gloryBootSkin?.dispose() ?? true;
})()"""


@dataclass(frozen=True, slots=True)
class SkinPayload:
    install_expression: str
    detect_expression: str
    restore_expression: str


def _wallpaper_mime(data: bytes) -> str:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    raise ValueError("壁纸必须是 PNG、JPEG 或 WebP")


def load_wallpaper(path: str) -> bytes:
    """读取经过签名和大小校验的本地壁纸。"""
    wallpaper_path = Path(path)
    if wallpaper_path.stat().st_size > MAX_WALLPAPER_BYTES:
        raise ValueError("壁纸不能超过 20 MiB")
    data = wallpaper_path.read_bytes()
    if not data:
        raise ValueError("壁纸文件为空")
    _wallpaper_mime(data)
    return data


def build_skin_payload(root: Path, wallpaper_path: str) -> SkinPayload:
    """构建固定安装、检测和恢复表达式。"""
    wallpaper = Path(wallpaper_path)
    if not wallpaper.is_absolute():
        wallpaper = root / wallpaper
    data = load_wallpaper(str(wallpaper))
    stylesheet = (_RESOURCE_ROOT / "skin.css").read_text(encoding="utf-8")
    script = (_RESOURCE_ROOT / "skin.js").read_text(encoding="utf-8")
    install = (
        script.replace("__SKIN_CSS_JSON__", json.dumps(stylesheet))
        .replace(
            "__WALLPAPER_BASE64_JSON__",
            json.dumps(base64.b64encode(data).decode("ascii")),
        )
        .replace(
            "__WALLPAPER_MIME_JSON__",
            json.dumps(_wallpaper_mime(data)),
        )
    )
    return SkinPayload(
        install_expression=install,
        detect_expression=_DETECT_EXPRESSION,
        restore_expression=_RESTORE_EXPRESSION,
    )
