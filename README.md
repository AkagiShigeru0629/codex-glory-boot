# Codex 荣耀零等待启动器

这是面向 Windows 10/11 x64 和 Microsoft Store 版 Codex 的独立 Python 启动器。
当前实现范围包括首帧海报、荣耀主题动画、并行启动 Codex、按 Codex 客户区校准一次窗口、自适应等待和桌面窗口管理器（DWM）交接。

第二阶段 A 的窗口适配已经实现，等待真实 Codex 的多显示器与 DPI 人工验收。第二阶段 B 的可选应用内壁纸已经完成自动实现和打包，但默认关闭且尚无实机验证版本；完整 Codex 用户界面皮肤不在当前范围内。

## 环境

- CPython 3.14
- PySide6 6.12
- Windows 10/11 x64

所有依赖安装在项目内 `.venv`，不修改系统 Python。

## 开发命令

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\bootstrap.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\test.ps1
```

生成发布目录与压缩包：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\package.ps1
```

## 专用入口

构建完成后可创建桌面专用入口：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\install.ps1
```

恢复脚本根据安装时记录的 SHA-256 删除专用入口；如果快捷方式在安装后被修改，会拒绝自动删除：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\restore.ps1
```

替换已有官方入口必须使用 `-ReplaceOfficial`，并通过 `-ShortcutPath` 明确指定目标。恢复时会重建原快捷方式的路径、参数、图标和工作目录。

## 当前验证结果

以下只记录最近一次明确验证的结果。发布包测量值、文件体积和 SHA-256 只对当次构建有效，不作为后续构建的固定状态；完整历史证据见更新计划。

- 2026-11-09 自动测试：261 通过、0 失败。
- 本地演示媒体：1920×1080、60 帧、8.000 秒 H.264；约 5.2 秒后进入“荣耀丨codex”结尾，等待点、交接区间分别为 6.4 秒、6.7–7.6 秒。
- 2026-11-09 已运行窗口复用修复后的打包基准：首个可见窗口 `268.5 ms`、媒体首帧 `451.2 ms`、Codex 启动请求 `270.6 ms`。
- 当前压缩包 SHA-256 为 `54dc0cc9273cdc278287a8e0dc4aa729eb560614e85200dd1124cb8bd367ffc5`。
- 当前媒体时长、时间点和关键帧以 `config/launcher.example.json` 和设计说明为准，启动逻辑不写死 8 秒。
- 后续重新打包时必须重新测量性能与 SHA-256，不得沿用本次构建数据。

打包基准使用无外部启动副作用的后端，只验证初始窗口、媒体和启动请求时序，不覆盖真实 Codex 窗口发现与几何校准。真实 Store 版 Codex 冷启动、普通窗口、最大化窗口、多显示器、负坐标和不同 DPI 仍需在完全退出 Codex 后人工验收。

## 可选应用内壁纸

- 默认关闭；普通启动、基准启动和显式关闭皮肤时不会申请调试端口。
- `--disable-skin` 可在单次启动中强制关闭皮肤。
- 只有同时存在已登记的 Codex 版本配置、存在壁纸文件，且本机记录的 Store 安装版本与配置完全匹配时，才使用 `127.0.0.1` 随机端口。
- 版本记录由安装脚本或 `scripts/sync-codex-runtime.ps1` 从正在运行的 Store 版 Codex 路径生成；如果可执行文件已因更新消失，记录自动失效并保持皮肤关闭。
- 当前 `skin_profiles.json` 保持空列表，尚未声称任何真实 Codex 版本兼容。
- 页面内按 `Ctrl+Alt+Shift+R` 恢复原生外观；页面重载或完全重启 Codex 也会清除注入状态。

## 架构摘要

- `domain/` 使用不可变数据类和纯函数，决定停留、恢复、超时、几何和目标矩形，可完全离屏测试。
- `services/` 用线程安全状态发送 Codex 启动请求；明确失败时等待 1 秒重试，请求看似成功但 8 秒内没有主窗口时再次激活，最多三次。主窗口出现后停止重复激活；250 ms `QTimer` 触发后台窗口探测，短暂漏检不会重置稳定窗口，日志挂载标记优先，窗口持续存在 8 秒后作为自动交接兜底。
- `adapters/` 集中封装 Win32、DWM 和快捷方式事务。窗口按进程名、包路径、窗口类、可见性、客户区和响应性筛选。
- `ui/` 读取上次有效的 Codex 客户区或当前显示器安全默认矩形，先设置物理窗口位置再显示海报；Codex 窗口稳定后只校准一次，并让媒体视口和 DWM 交接共用该矩形。
- Codex 已运行时，专用入口在显示动画前聚焦现有窗口并退出，避免先播放动画再跳转或重复启动。
- DWM 缩略图在过渡区间持续更新；注册或更新失败时改为窗口淡出。所有交接原因由同一策略决定退出、报错或激活窗口。
- 动画始终完整播放；结束后至少保留最终画面 2.5 秒，Codex 主界面尚未挂载时继续等待，超时后才执行回退。
- 播放位置到达 `duration - 50 ms` 时主动暂停在视频自身的最后一帧，不进入 `EndOfMedia`，也不增加额外图片或覆盖层。
- 最终交接先聚焦 Codex，再让启动器在 360 ms 内平滑淡出；`Esc` 跳过也走同一淡出流程。
- PyInstaller 使用 `onedir`。Windows 系统 ICU 负责提供 Qt 所需的 `ucnv_open`，发布规格会排除不兼容的同名私有 ICU。

架构讲解时可强调三个关键取舍：海报首绘与 Codex 启动并行、领域状态机与平台 API 解耦、DWM 失败仍保证回到可操作的 Codex。

Microsoft Store 包的稳定入口是 `OpenAI.Codex_2p2nqsd0c76g0!App`。新版桌面主程序名为 `ChatGPT.exe`，旧版本可能使用 `Codex.exe`，配置同时兼容两者，并通过 `OpenAI.Codex_` 包路径前缀排除同名程序。

## 目录

- `src/glory_boot/domain/`：不依赖 Qt、文件系统和 Windows API 的纯领域逻辑。
- `src/glory_boot/services/`：媒体、启动、会话和日志编排。
- `src/glory_boot/adapters/`：Qt、Win32、DWM、快捷方式等外部边界。
- `src/glory_boot/ui/`：窗口显示和用户输入。
- `scripts/`：环境、测试、构建、安装、恢复和媒体工具入口。
- `tests/`：自动化测试。

## 恢复

启动器不会修改 Codex 安装目录。专用入口和可选官方入口替换均可通过安装记录恢复。

## 素材与许可

当前本地演示海报和视频包含原作“荣耀”标志及游戏界面视觉元素，不得上传到公开仓库或对外分发。公开仓库应使用 `tools/render_video.py` 生成的无争议占位媒体，或替换为已取得授权的素材；替换后必须重新打包与验证。

`tools/render_video.py` 保留程序化渲染能力，但当前本地成片已经使用外部素材，不能用该脚本证明现有媒体不含官方素材。`assets/local/` 中的参考与来源登记已被 Git 忽略，但当前构建会把 `media/` 中的媒体复制进发布包，因此公开前必须同时检查仓库内容和发布包。
第三方组件与参考项目声明见 `THIRD_PARTY_NOTICES.md`。项目整体开源许可证尚未决定。
