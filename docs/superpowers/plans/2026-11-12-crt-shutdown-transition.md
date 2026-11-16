# CRT 收束转场实施计划

> **执行代理须知：** 本计划由当前代理按 `superpowers:executing-plans` 在本会话中执行。每个任务先写失败测试，再写最小实现；不提交、不推送、不替换入口，真实冷启动由秋月大人确认。

**目标：** 在当前启动动画末尾加入约 `0.7` 秒的确定性 CRT 收束，把最终画面压成亮线并缩成亮点，再由 DWM 淡入真实 Codex。

**架构：** 新增独立媒体后处理工具，从当前视频截取 `0–6.4` 秒并用 42 帧生成 CRT 收束，再补足到配置时长。应用逻辑继续由配置驱动，CRT 收束位于等待点之后，DWM 使用全窗口矩形和透明度完成黑色到 Codex 的淡入。

**技术栈：** CPython 3.14、Pillow、NumPy、imageio-ffmpeg、PySide6 6.12、pytest、PyInstaller onedir。

**设计说明：** `docs/superpowers/specs/2026-11-12-crt-shutdown-transition-design.md`

## 全局约束

- 媒体时长不写死为 8 秒；当前版本配置为 `7.7` 秒，后续媒体可以继续调整。
- 时间点必须满足 `0 <= HoldAt < TransitionStart < TransitionEnd < Duration`。
- CRT 收束在 Codex 窗口框架稳定后随动画连续播放，不等待页面内容加载。
- DWM 失败时仍能通过窗口淡出回到可操作 Codex。
- 不复制 `codex-startup-animation-windows` 源码或素材。
- 不新增第三方依赖。
- 每个任务先写失败测试，再实现并运行目标测试。
- 最终运行 `powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\test.ps1`、媒体烟雾检查和打包基准。
- 不自动提交、推送、替换快捷方式或执行真实 Codex 冷启动。

## 审查重点

- Codex 未就绪时误播 CRT，导致亮点熄灭后长时间黑屏。
- CRT 收束仍显示完整最终画面，或末帧没有熄灭。
- 新视频时长与配置不一致，导致时间线提前暂停或尾部黑屏过长。
- DWM 仍按空间扩张更新，遮住 CRT 或重新出现窗口边框。
- 媒体失败、DWM 失败和 `Esc` 跳过路径被新转场阻断。

---

### 任务 1：生成确定性 CRT 收束视频

**文件：**

- 新增：`tools/append_crt_shutdown.py`
- 新增：`tests/test_append_crt_shutdown.py`

**接口：**

- `CRT_FRAME_COUNT: int = 42`
- `CRT_DURATION_SECONDS: float = 0.7`
- `render_crt_frame(source: Image.Image, frame_index: int) -> Image.Image`
- `iter_crt_frames(source: Image.Image) -> Iterator[Image.Image]`
- `append_crt_shutdown(input_video: Path, output_video: Path) -> None`

**消费：** 当前 `media/startup.mp4`、Pillow、NumPy、imageio-ffmpeg。

**产出：** `1920×1080`、60 帧、H.264 的 `7.7` 秒成片；CRT 收束共 42 帧。

- [x] **步骤 1：写失败测试**

新增测试，断言常量、`render_crt_frame` 的尺寸、亮度压制曲线、亮线/亮点收缩和黑场终帧。

- [x] **步骤 2：运行失败测试**

运行：`.\.venv\Scripts\python.exe -m pytest tests\test_append_crt_shutdown.py -v`

预期：模块不存在或接口缺失。

- [x] **步骤 3：实现帧生成和编码**

新增工具：截取源视频前 `6.4` 秒，生成 42 帧 CRT 收束，再写入黑色帧直到 `7.7` 秒；不依赖 `assets/local/`。

- [x] **步骤 4：运行目标测试**

运行：`.\.venv\Scripts\python.exe -m pytest tests\test_append_crt_shutdown.py -v`

预期：全部通过。

### 任务 2：同步配置、DWM 淡入和最终停留

**文件：**

- 修改：`config/launcher.example.json`
- 修改：`src/glory_boot/services/session.py`
- 修改：`tests/test_config.py`
- 修改：`tests/test_session.py`
- 修改：`tests/test_timeline.py`

**接口：**

- 当前配置：`Duration=7.7`、`HoldAt=6.4`、`TransitionStart=7.1`、`TransitionEnd=7.6`。
- `screen_frames`：`7.1` 秒全窗口矩形且透明度 `0`，`7.6` 秒全窗口矩形且透明度 `1`。
- `FINAL_FRAME_HOLD_SECONDS: float = 0.2`。

**消费：** 任务 1 的新视频规格。

**产出：** 黑色收束结束后 DWM 透明淡入真实 Codex，视频结束后 0.2 秒交接。

- [x] **步骤 1：写失败测试**

断言示例配置时间点、DWM 目标矩形不收缩、最终停留 `0.2` 秒，以及自定义时长仍可正常工作。

- [x] **步骤 2：运行失败测试**

运行：`.\.venv\Scripts\python.exe -m pytest tests\test_config.py tests\test_session.py tests\test_timeline.py -v`

预期：配置时长、关键帧和最终停留仍是旧值。

- [x] **步骤 3：更新配置和状态机常量**

只改示例配置、最终停留常量和相关测试夹具；不修改领域时间线公式。

- [x] **步骤 4：运行目标测试**

运行：`.\.venv\Scripts\python.exe -m pytest tests\test_config.py tests\test_session.py tests\test_timeline.py -v`

预期：全部通过。

### 任务 3：生成正式媒体并验证

**文件：**

- 修改：`media/startup.mp4`
- 修改：`scripts/smoke_test.py`
- 新增：`assets/local/output/crt-shutdown/source-backup.mp4`（仅本地、被 Git 忽略）

**接口：**

- 使用 `tools/append_crt_shutdown.py` 从当前正式媒体生成新成片。
- 备份只用于本地回退，不进入构建、提交或发布包。

**产出：** 可播放的 `7.7` 秒 H.264 正式媒体。

- [x] **步骤 1：更新媒体规格失败断言**

将烟雾检查的目标时长改为从当前设计契约得到的 `7.7 ± 0.1` 秒，并保留尺寸、帧率、Qt 解码和海报检查。

- [x] **步骤 2：运行失败检查**

运行：`.\.venv\Scripts\python.exe scripts\smoke_test.py --assets-only`

预期：现有 `8.0` 秒媒体失败。

- [x] **步骤 3：备份旧媒体并生成新成片**

把旧 `media/startup.mp4` 复制到 Git 忽略的本地备份目录，再运行新工具覆盖正式媒体。

- [x] **步骤 4：运行媒体检查**

运行：`.\.venv\Scripts\python.exe scripts\smoke_test.py --assets-only`

预期：`7.7` 秒、60 帧、1920×1080、Qt 解码正常。

### 任务 4：全量验证、打包和文档同步

**文件：**

- 修改：`README.md`
- 修改：`docs/superpowers/specs/2026-11-07-glory-boot-retime-design.md`
- 修改：`docs/superpowers/plans/2026-11-12-crt-shutdown-transition.md`
- 修改：`tests/test_repository_contract.py`

**接口：**

- 记录实际测试数量、媒体时长、打包基准和压缩包 SHA-256。
- 保留旧媒体参数为历史记录，并明确当前事实。

- [x] **步骤 1：运行全量自动测试**

运行：`powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\test.ps1`

预期：全部通过，`compileall` 通过。

- [x] **步骤 2：重建 onedir 并运行烟雾检查**

运行：`powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build.ps1`

再运行：`.\.venv\Scripts\python.exe scripts\smoke_test.py`

预期：媒体、资源和压缩包契约通过。

- [x] **步骤 3：执行打包基准**

运行：`powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\package.ps1 -Benchmark`

记录首个可见窗口、媒体首帧、启动请求、退出码和新 SHA-256。

- [x] **步骤 4：同步当前文档**

更新 README、媒体设计说明和本计划执行记录；明确基准不包含真实 Codex 等待。

- [x] **步骤 5：检查工作区**

运行：`git status --short` 和 `git diff --check`

确认没有备份媒体、日志、构建产物、缓存或本地素材进入待提交范围。

## 执行记录

| 日期 | 项目 | 结果 |
| --- | --- | --- |
| 2026-11-12 | CRT 帧生成 | 新增 `tools/append_crt_shutdown.py`；目标测试 `5` 通过 |
| 2026-11-12 | 配置与交接 | 当前媒体 `7.7` 秒；`HoldAt=6.4`、`TransitionStart=7.1`、`TransitionEnd=7.6`；最终停留 `0.2` 秒 |
| 2026-11-12 | 正式媒体 | H.264、`1920×1080`、60 帧、`7.700` 秒、Qt 解码正常 |
| 2026-11-12 | 全量测试 | `289` 通过、`0` 失败 |
| 2026-11-12 | 发布烟雾检查 | 多媒体插件、媒体和压缩包日志隔离检查通过 |
| 2026-11-12 | 打包基准 | 首个可见窗口 `357.7 ms`、媒体首帧 `561.9 ms`、Codex 启动请求 `363.2 ms` |
| 2026-11-12 | 压缩包 | `dist/GloryCodexBoot-win-x64.zip`，SHA-256 `58c68136d1cdbd23ac650dc3e202fee4465fab8e96acd6bcd90bf4f0fd037e6f` |
| 2026-11-16 | 长时间黑场回归 | 真实日志显示 Codex 未确认就绪时，时间线虽返回 `HOLD`，播放器却没有停在 `HoldAt`，继续播到 CRT 黑场；现已在实际暂停点同步等待界面，并保留内容就绪后的收束 | `300` 通过；旧日志从末帧暂停到交接约 `8.4 s`，新路径不再进入该黑场等待 |
| 2026-11-16 | 连续播放修订 | 录屏确认 `12–18 s` 最终画面冻结来自 `HoldAt` 主动暂停；移除 `hold_at`、`HOLD/RESUME`、内容日志和壁纸就绪门控，窗口框架连续稳定后动画直接播完，Codex 页面后续加载不再阻塞开屏 | `302` 通过；目标测试先失败后通过；`compileall` 通过 | 需在重新打包后由秋月大人完成一次真实冷启动视觉验收 |
