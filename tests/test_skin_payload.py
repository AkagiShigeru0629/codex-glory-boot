import re
from pathlib import Path

import pytest

from glory_boot.services.skin_payload import (
    MAX_WALLPAPER_BYTES,
    build_skin_payload,
    load_wallpaper,
)


ROOT = Path(__file__).resolve().parents[1]


def _wallpaper(tmp_path: Path, *, payload: bytes | None = None) -> Path:
    path = tmp_path / "wallpaper.png"
    path.write_bytes(payload or b"\x89PNG\r\n\x1a\n")
    return path


@pytest.mark.parametrize(
    "payload",
    [
        b"\x89PNG\r\n\x1a\n",
        b"\xff\xd8\xff\xe0example\xff\xd9",
        b"RIFF\x04\x00\x00\x00WEBP",
    ],
)
def test_supported_wallpaper_signatures_are_accepted(
    tmp_path: Path,
    payload: bytes,
) -> None:
    path = _wallpaper(tmp_path, payload=payload)

    assert load_wallpaper(str(path)) == payload


def test_only_supported_wallpaper_formats_are_accepted(tmp_path: Path) -> None:
    path = tmp_path / "wallpaper.gif"
    path.write_bytes(b"GIF89a")

    with pytest.raises(ValueError):
        load_wallpaper(str(path))


def test_wallpaper_size_limit_is_enforced(tmp_path: Path) -> None:
    path = _wallpaper(tmp_path)
    with path.open("r+b") as handle:
        handle.truncate(MAX_WALLPAPER_BYTES + 1)

    with pytest.raises(ValueError, match="20 MiB"):
        load_wallpaper(str(path))


def test_payload_has_one_marker_and_fixed_restore(tmp_path: Path) -> None:
    payload = build_skin_payload(ROOT, str(_wallpaper(tmp_path)))

    assert payload.install_expression.count("glory-boot-skin-style") == 1
    assert "__gloryBootSkin" in payload.install_expression
    assert "__gloryBootSkin?.dispose" in payload.restore_expression
    assert "data-glory-boot-skin" in payload.install_expression
    assert "globalThis.__gloryBootSkin" in payload.detect_expression
    assert '"--glory-boot-wash", "0.58"' in payload.install_expression
    for forbidden in ("innerText", "localStorage", "document.cookie"):
        assert forbidden not in payload.install_expression


def test_payload_does_not_redesign_controls() -> None:
    stylesheet = (
        ROOT / "src" / "glory_boot" / "resources" / "skin.css"
    ).read_text(encoding="utf-8")

    for forbidden in ("font-family", "font-size", "pointer-events:"):
        assert forbidden not in stylesheet
    assert re.search(r"^\s*display\s*:", stylesheet, re.MULTILINE) is None
    assert re.search(r"^\s*position\s*:", stylesheet, re.MULTILINE) is None


def test_stylesheet_covers_current_version_content_surfaces() -> None:
    stylesheet = (
        ROOT / "src" / "glory_boot" / "resources" / "skin.css"
    ).read_text(encoding="utf-8")

    assert "--color-surface: transparent" in stylesheet
    assert "main.bg-surface" in stylesheet
    assert '[class*="MainContentSurface-"]' in stylesheet
    assert '[class*="ConversationSidebar-"]' in stylesheet
    assert '[class*="ComposerLayoutRoot-"]' in stylesheet
    assert ":has(.ProseMirror)" in stylesheet


def test_assistant_content_has_opaque_reading_surface() -> None:
    stylesheet = (
        ROOT / "src" / "glory_boot" / "resources" / "skin.css"
    ).read_text(encoding="utf-8")
    rule = re.search(
        r'\[class\*="MarkdownRoot-"\]:not\(\.rich-text-user-turn\)'
        r"\s*\{[^}]*background-color:\s*#faf8fb !important;",
        stylesheet,
        re.DOTALL,
    )

    assert rule is not None


def test_tool_and_file_cards_use_near_opaque_surface() -> None:
    stylesheet = (
        ROOT / "src" / "glory_boot" / "resources" / "skin.css"
    ).read_text(encoding="utf-8")
    rule = re.search(
        r'\[class\*="resource-card"\]\s*\{[^}]*'
        r"background-color:\s*#faf8fb !important;",
        stylesheet,
        re.DOTALL,
    )

    assert rule is not None


def test_stylesheet_keeps_project_sidebar_legible_over_wallpaper() -> None:
    stylesheet = (
        ROOT / "src" / "glory_boot" / "resources" / "skin.css"
    ).read_text(encoding="utf-8")

    app_panel = re.search(
        r"\.app-shell-left-panel\s*\{[^}]*"
        r"background-color:\s*rgb\(250 248 251 /\s*([0-9.]+)\)",
        stylesheet,
        re.DOTALL,
    )
    conversation_sidebar = re.search(
        r'\[class\*="ConversationSidebar-"\]\s*\{[^}]*'
        r"background-color:\s*transparent !important;",
        stylesheet,
        re.DOTALL,
    )

    assert app_panel is not None
    assert conversation_sidebar is not None
    app_alpha = float(app_panel.group(1))

    assert 0.16 <= app_alpha <= 0.20
    assert "color: #1a1c1f" in stylesheet
    assert (
        ':is(button, a, span, svg) {\n    color: #1a1c1f !important;'
        in stylesheet
    )


def test_stylesheet_uses_light_translucent_surfaces() -> None:
    stylesheet = (
        ROOT / "src" / "glory_boot" / "resources" / "skin.css"
    ).read_text(encoding="utf-8")
    composer = re.search(
        r'\[class\*="ComposerLayoutRoot-"\]\s*\{[^}]*'
        r"background-color:\s*#ffffff !important;"
        r"[^}]*backdrop-filter:\s*blur\(12px\)"
        r"[^}]*color:\s*#1a1c1f",
        stylesheet,
        re.DOTALL,
    )

    assert "color-scheme: light;" in stylesheet
    assert "--color-text: #1a1c1f !important;" in stylesheet
    assert composer is not None


def test_plus_button_menu_uses_clear_reading_surface() -> None:
    stylesheet = (
        ROOT / "src" / "glory_boot" / "resources" / "skin.css"
    ).read_text(encoding="utf-8")
    rule = re.search(
        r'\[data-composer-overlay-floating-ui="true"\]\s+'
        r'\[class\*="suggestionMenu-"\]\s*\{[^}]*'
        r"background-color:\s*rgb\(250 248 251 /\s*0\.96\)",
        stylesheet,
        re.DOTALL,
    )

    assert rule is not None
