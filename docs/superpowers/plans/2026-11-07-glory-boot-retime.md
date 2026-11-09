# 荣耀开屏最终重剪实施计划

> **执行代理须知：** 必须使用 `superpowers:executing-plans` 按任务顺序执行本计划，并用复选框记录进度。当前工作区没有初始提交；本计划不包含提交、推送或真实 Codex 冷启动操作。

**目标：** 将荣耀开屏重剪为约 `5.2` 秒主画面加 `2.8` 秒登录界面结尾，消除硬切并同步启动交接、等待提示和自动测试。

**架构：** 继续使用现有 Python/Pillow/FFmpeg 渲染器处理两份本地源视频；时间分配和桥接逻辑留在 `tools/render_ten_zone_ending.py`。启动器仍只读取配置，不写死媒体时间点；等待提示只调整 UI 布局。

**技术栈：** CPython 3.14、Pillow、NumPy、imageio-ffmpeg、PySide6 6.12、pytest、PyInstaller。

**设计说明：** `docs/superpowers/specs/2026-11-07-glory-boot-retime-design.md`

## 全局约束

- 正式媒体保持 `1920×1080`、`60` 帧、`8.000` 秒 H.264。
- 前段与结尾目标比例约为 `5.2` 秒比 `2.8` 秒。
- 必须保留“确定”“返回”伪交互按钮，它们只作视觉装饰。
- DWM 时间为 `6.7–7.6` 秒，等待点为 `6.4` 秒。
- 启动逻辑只读取配置，不写死媒体时长或关键时间点。
- 先运行失败测试，再写最小实现。
- 不增加依赖、音轨、素材下载或第二套视觉系统。
- 不提交、不推送、不替换官方快捷方式、不自行启动真实 Codex。
- `.reference/`、`.venv/`、`dist/`、`assets/local/` 和日志不得进入 Git。

## 审查重点

- 源视频结尾不足目标帧数时，成片仍必须完整填满 `2.8` 秒且不重复闪跳。
- 切点亮度突变必须通过桥接降低，不能只是简单拼接。
- “确定”“返回”区域必须保持原样，底部标签替换不能污染按钮。
- 标题必须留在安全区，不能因增强可读性遮住徽记或按钮。
- 等待提示必须位于右上安全区，且不能改变视频或海报几何。

---

### 任务 1：重排时间结构并加入桥接

**文件：**

- 修改：`tools/render_ten_zone_ending.py`
- 修改：`tests/test_render_ten_zone_ending.py`

**接口：**

- 产出常量：`OPENING_DURATION = 5.2`、`ENDING_DURATION = 2.8`、`BRIDGE_DURATION = 0.30`。
- 产出 `_iter_resampled_ending(frames: Sequence[Image.Image]) -> Iterator[Image.Image]`，输出固定 `168` 帧。
- 产出 `_iter_bridge_frames(base: Image.Image, ending: Image.Image) -> Iterator[Image.Image]`，输出约 `11` 帧。
- `_render_video` 与 `_assemble_frames` 使用同一套结尾重采样和桥接行为。

- [x] **步骤 1：写时间比例失败测试**

在 `tests/test_render_ten_zone_ending.py` 中断言：

```python
assert renderer.OPENING_DURATION == pytest.approx(5.2)
assert renderer.ENDING_DURATION == pytest.approx(2.8)
assert renderer.ENDING_FRAME_COUNT == 168
```

- [x] **步骤 2：写结尾重采样失败测试**

使用至少 3 张可区分的合成帧，断言 `list(renderer._iter_resampled_ending(frames))` 长度为 `168`，首帧来自源序列开头，末帧来自源序列末尾，且最后至少 60 帧保持末帧内容。

- [x] **步骤 3：写桥接连续性失败测试**

使用亮色与暗色合成帧，将 `_iter_bridge_frames` 输出与前后帧合并，断言相邻帧平均亮度差不超过 `12`，并断言首末帧分别接近原始前后画面。

- [x] **步骤 4：更新前段阶段测试**

将七个效果阶段的采样时间改为紧凑时间线中的代表值，并保留“七个阶段全部存在”的断言。

- [x] **步骤 5：运行目标测试并确认按预期失败**

运行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_render_ten_zone_ending.py -v
```

预期：失败，因为新常量、重采样函数和桥接函数尚不存在。

- [x] **步骤 6：实现紧凑时间线和结尾重采样**

将前段阶段压缩到 `0.0–5.2` 秒；结尾源取 `glory.mp4` 的 `0.48–1.56` 秒。结尾前约 `1.35` 秒按均匀映射播放，剩余帧保持末帧并叠加轻微标题脉冲。

- [x] **步骤 7：实现亮度桥接**

在 `4.9–5.2` 秒之间对主画面与结尾首帧做平滑混合，并加入递减红色亮度层。桥接首帧接近主画面，末帧接近结尾画面。

- [x] **步骤 8：接入流式编码**

`_render_video` 先写入主画面，再写桥接帧，最后写重采样结尾；不得一次把全部 1080p 帧载入内存。

- [x] **步骤 9：运行目标测试**

运行同一 pytest 命令，预期全部通过。

---

### 任务 2：保持最终界面素材原样

**文件：**

- 修改：`tools/render_ten_zone_ending.py`
- 修改：`tests/test_render_ten_zone_ending.py`

**接口：**

- `_prepare_ending_frame(frame: Image.Image, clean_frame: Image.Image, *, reveal: float, glitch: float) -> Image.Image` 仅替换原“十区”中央标题，并保留所有其他 HUD 元素。

- [x] **步骤 1：写后半段素材保留失败测试**

使用纯色画布预置底部标签和伪按钮区域，调用 `_prepare_ending_frame` 后断言
这两个区域的像素与输入完全一致。

- [x] **步骤 2：运行目标测试并确认失败**

运行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_render_ten_zone_ending.py -v
```

预期：失败，因为此前进度中的实现仍会覆盖底部标签。

- [x] **步骤 3：恢复原有标题样式**

把标题内芯和辉光恢复为本次修改前的色值与透明度。

- [x] **步骤 4：移除底部标签替换**

删除 `_replace_bottom_label`、`_draw_bottom_label` 和相关区域绘制；`_prepare_ending_frame` 只调用 `_replace_title_region` 和 `_draw_custom_title`。

- [x] **步骤 5：运行目标测试**

运行同一 pytest 命令，预期全部通过。

---

### 任务 3：将等待提示移动到右上安全区

**文件：**

- 修改：`src/glory_boot/ui/boot_window.py`
- 修改：`tests/test_ui_smoke.py`

**接口：**

- `BootWindow.show_waiting(visible: bool)` 保持现有签名。
- 等待标签使用右上对齐，内容为 `Codex 正在启动…\nEsc 跳过`。

- [x] **步骤 1：写等待提示位置失败测试**

在 `tests/test_ui_smoke.py` 中显示等待提示后断言：

```python
assert window.waiting.alignment() & Qt.AlignmentFlag.AlignRight
assert window.waiting.alignment() & Qt.AlignmentFlag.AlignTop
assert window.waiting.contentsMargins().right() >= 32
assert window.waiting.contentsMargins().top() >= 32
```

- [x] **步骤 2：运行目标测试并确认失败**

运行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_ui_smoke.py -v
```

预期：失败，因为当前等待提示底部居中。

- [x] **步骤 3：实现右上定位**

将等待标签改为 `AlignRight | AlignTop`，保留全窗口几何以继续使用透明覆盖层，设置右侧和顶部安全边距，并保留原有视频尺寸测试。

- [x] **步骤 4：运行目标测试**

运行同一 pytest 命令，预期全部通过。

---

### 任务 4：同步配置、时间线和会话测试

**文件：**

- 修改：`config/launcher.example.json`
- 修改：`tests/test_config.py`
- 修改：`tests/test_timeline.py`
- 修改：`tests/test_session.py`

**接口：**

- 正式配置值：`hold_at=6.4`、`transition_start=6.7`、`transition_end=7.6`。
- `screen_frames` 中间关键帧时间同步为 `6.7`。
- 时间线状态机代码保持不变。

- [x] **步骤 1：写正式配置时间失败测试**

在 `tests/test_config.py` 中读取项目正式配置并断言三个时间点和中间关键帧时间。

- [x] **步骤 2：更新时间线期望但保留旧配置校验特性**

将时间线夹具改为 `6.4/6.7/7.6`，断言 `6.399` 继续、`6.4` 停留、`7.15` 过渡进度为 `0.5`。

- [x] **步骤 3：更新会话期望**

将等待测试改为 `6.4` 秒，将 DWM 注册和更新测试改为 `6.7`、`7.15` 秒，保留相同的目标矩形和透明度期望。

- [x] **步骤 4：运行目标测试并确认失败**

运行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_config.py tests\test_timeline.py tests\test_session.py -v
```

预期：正式配置断言失败，因为示例配置仍是旧时间点。

- [x] **步骤 5：修改正式配置**

只修改 `hold_at`、`transition_start` 和中间 `screen_frames.time`，保留媒体时长、矩形、透明度和等待上限。

- [x] **步骤 6：运行目标测试**

运行同一 pytest 命令，预期全部通过。

---

### 任务 5：生成正式媒体、同步文档并重建发布包

**文件：**

- 修改：`media/startup.mp4`
- 修改：`media/poster.png`
- 修改：`docs/superpowers/specs/2026-11-04-codex-glory-launch-design.md`
- 修改：`docs/superpowers/plans/2026-11-04-codex-glory-boot.md`
- 修改：`README.md`

**接口：**

- 源视频：`C:\Users\75664\Desktop\剪辑素材\glory1.mp4`、`glory.mp4`。
- 中间产物：`assets/local/output/retime-2026-11-07/lookdev.mp4`。
- 正式海报必须与新视频首帧完全一致。

- [x] **步骤 1：运行全量测试**

运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\test.ps1
```

预期：全部测试通过。

- [x] **步骤 2：重新渲染本地中间成片**

运行 `tools/render_ten_zone_ending.py`，输入两份源视频，输出到 `assets/local/output/retime-2026-11-07/`。

- [x] **步骤 3：检查时间比例与切点连续性**

用 FFmpeg 抽取总览联系表，确认结尾约从 `5.2` 秒开始、主画面亮度不再单帧突降、标题和按钮均清晰可见。

- [x] **步骤 4：替换正式媒体和海报**

将中间成片复制为 `media/startup.mp4`，从新视频第一帧生成 `media/poster.png`。

- [x] **步骤 5：运行媒体烟雾检查**

运行：

```powershell
.\.venv\Scripts\python.exe scripts\smoke_test.py --assets-only
```

预期：输出 `assets_ok duration=8.000s fps=60.000 size=1920x1080 qt_decode=ok`。

- [x] **步骤 6：同步设计、README 与执行记录**

更新设计说明中的旧 `7.17` 秒切点、结尾截图说明和伪按钮决策；在计划执行记录中追加源文件、命令、结果、剩余风险和新媒体事实。

- [x] **步骤 7：重建发布包**

依次运行 `scripts/build.ps1` 和 `scripts/package.ps1`，确认发布目录和压缩包包含新媒体。

- [x] **步骤 8：运行最终全量验证**

运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\test.ps1
.\.venv\Scripts\python.exe scripts\smoke_test.py
```

预期：测试全部通过；媒体、发布包、Qt 插件和压缩包日志隔离检查全部通过。

- [x] **步骤 9：检查工作区**

运行 `git status --short`，确认没有新增 `.venv/`、`.reference/`、日志、`dist/` 或本地源视频进入待提交范围。
