# 第三方组件与参考项目声明

本文件记录项目直接使用或依赖的第三方组件。发布包应同时保留各组件随附的许可证文本和版权声明。

## PySide6 6.12.0

- 用途：窗口、事件循环、QtMultimedia 媒体播放、QtNetwork 与 QtWebSockets 本地调试连接。
- 许可证：LGPL-3.0-only 或 GPL-2.0-only 或 GPL-3.0-only；本项目采用 LGPLv3 路径规划发布。
- 归属：The Qt Company 及 Qt for Python 贡献者。
- 义务：保留版权与许可证信息；以动态链接方式分发 Qt 库；提供替换共享库所需信息。
- 来源：<https://pypi.org/project/PySide6/6.12.0/>

## PyInstaller 6.22.3

- 用途：生成 Windows `onedir` 发布目录。
- 许可证：GNU GPL 第 2 版或更高版本，并附允许构建、分发非自由程序的特殊例外。
- 归属：PyInstaller Development Team。
- 义务：保留 PyInstaller 许可与例外文本。
- 来源：<https://pypi.org/project/pyinstaller/6.22.3/>

## Pillow 13.0.0

- 用途：生成海报、动画帧和视觉素材。
- 许可证：MIT-CMU。
- 归属：Pillow 贡献者及原始 Imaging 库贡献者。
- 义务：保留版权与许可文本。
- 来源：<https://pypi.org/project/pillow/13.0.0/>

## NumPy 2.5.4

- 用途：确定性帧生成和像素合成。
- 许可证：BSD-3-Clause，并包含 0BSD、MIT、Zlib 和 CC0-1.0 许可的组件。
- 归属：NumPy Developers。
- 义务：保留 NumPy 分发包中的版权和许可证信息。
- 来源：<https://pypi.org/project/numpy/2.5.4/>

## imageio-ffmpeg 0.8.1

- 用途：调用 FFmpeg 编码 H.264 动画。
- 许可证：imageio-ffmpeg 为 BSD-2-Clause；随包 FFmpeg 构建的实际许可证以其分发包说明为准。
- 归属：imageio 项目、FFmpeg 项目及对应构建贡献者。
- 义务：保留 imageio-ffmpeg 和随包 FFmpeg 构建的许可证、版权与源码获取信息。
- 来源：<https://pypi.org/project/imageio-ffmpeg/0.8.1/>

## dragon-codex-boot

- 用途：仅学习启动时序、窗口交接和工程组织思路；Python 产品代码独立实现。
- 许可证：MIT。
- 归属：`yushua0808-cpu` 及项目贡献者。
- 来源：<https://github.com/yushua0808-cpu/dragon-codex-boot>

未复制 `yanami-sec/codex-startup-animation-windows` 的源码，因为该参考项目没有明确许可证。

## 正式视觉素材

- 当前首帧海报和 8 秒动画由项目内 Python 代码程序化绘制。
- 正式媒体不包含原作角色、动画截图、游戏画面或官方 Logo。
- `media/wallpaper.jpg` 是经秋月大人允许提交的本地测试壁纸；公开分发前仍需确认来源与授权，或替换为已获授权的素材。
- 发布包不读取也不包含 `assets/local/` 中的历史参考素材。
