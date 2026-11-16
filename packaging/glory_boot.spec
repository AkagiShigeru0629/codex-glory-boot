# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path


project_root = Path(SPECPATH).parent
resource_root = project_root / "src" / "glory_boot" / "resources"

a = Analysis(
    [str(project_root / "src" / "glory_boot" / "__main__.py")],
    pathex=[str(project_root / "src")],
    binaries=[],
    datas=[
        (str(project_root / "config" / "launcher.example.json"), "config"),
        (str(project_root / "media" / "startup.mp4"), "media"),
        (str(project_root / "media" / "poster.png"), "media"),
        (str(project_root / "media" / "wallpaper.jpg"), "media"),
        (str(project_root / "THIRD_PARTY_NOTICES.md"), "."),
        *[
            (str(resource), "glory_boot/resources")
            for resource in sorted(resource_root.glob("*"))
        ],
    ],
    hiddenimports=["PySide6.QtWebSockets"],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

# Python 安装目录中的 ICU 78 不带 Windows 系统 ICU 的 ucnv_open 转发入口；
# PySide6 在 Windows 上应使用系统 icuuc.dll，避免被同名私有库抢先加载。
_excluded_icu_names = {"icuuc.dll", "icudt78.dll"}
a.binaries = [
    entry
    for entry in a.binaries
    if Path(entry[0]).name.casefold() not in _excluded_icu_names
]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="GloryCodexBoot",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(project_root / "assets" / "app-icon.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="GloryCodexBoot",
)
