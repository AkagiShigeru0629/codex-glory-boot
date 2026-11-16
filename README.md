# Codex 荣耀启动器

面向 Windows 10/11 x64 上 Microsoft Store 版 Codex 的独立启动器。

## 环境

直接运行发布版：

- Windows 10/11 x64
- Microsoft Store 版 Codex

从源码运行或构建：

- CPython 3.14
- PowerShell
- PySide6 6.12 等依赖安装在项目内 `.venv`

## 启动

发布包位于 GitHub Releases。下载并解压 `GloryCodexBoot-win-x64.zip` 后，运行其中的 `GloryCodexBoot.exe`。如果当前版本尚未提供发布附件，可按下方源码步骤构建。

首次从源码运行时，先初始化项目环境：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\bootstrap.ps1
```

构建并运行发布版：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build.ps1
.\dist\GloryCodexBoot\GloryCodexBoot.exe
```

也可以创建桌面快捷方式：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\install.ps1
```

安装后双击桌面的“Codex 荣耀启动”即可。

## 使用方法

启动前请完全退出 Codex，否则启动器只会聚焦已经打开的 Codex，不会播放开屏动画。

- 点击启动器入口后，Codex 会在后台启动并播放开屏动画。
- 按 `Esc` 可以跳过动画。
- 如果应用内壁纸出现异常，按 `Ctrl+Alt+Shift+R` 可恢复 Codex 原生外观。
- 壁纸注入失败不会阻止 Codex 正常启动和使用。

## 卸载

恢复或删除由安装脚本创建的桌面快捷方式：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\restore.ps1
```

如需彻底删除启动器，再删除解压后的发布目录。启动器不会修改或卸载 Codex。

## 许可证与素材来源

项目源代码采用 [MIT License](LICENSE)，允许复制、修改、分发和商业使用，但须保留版权与许可声明。

视频、壁纸素材来源于官方。第三方组件与参考项目声明见 `THIRD_PARTY_NOTICES.md`。
