# Codex 荣耀 Python 零等待启动实施计划

> **历史说明：** 冷启动“立即显示首帧”的显示时机已于 2026-11-12 被 `2026-11-09-phase2a-window-adaptation.md` 的任务 8 改为等待 Codex 主窗口稳定后再显示和播放；本文件其余执行记录保留为历史证据。

> **执行代理须知：** 必须使用 `superpowers:subagent-driven-development` 或 `superpowers:executing-plans`，按任务顺序执行本计划，并用复选框记录进度。

**目标：** 使用全 Python 构建 Windows 启动器：先显示荣耀动画首帧，同时异步启动 Codex；Codex 晚到时停留，就绪后通过桌面窗口管理器（Desktop Window Manager，DWM）无缝交接。

**架构：** PySide6 负责无边框窗口、QtMultimedia 视频和界面事件；纯 Python 领域层负责配置、时间线、几何和交接策略；`ctypes` 适配器集中封装 Win32/DWM；`QProcess` 非阻塞启动 Codex。发布使用 PyInstaller 的 `onedir` 模式。

**技术栈：** CPython 3.14、PySide6 6.12、QtMultimedia、`ctypes`、`QProcess`、`QTimer`、pytest、Pillow、NumPy、imageio-ffmpeg、PyInstaller 6.22。

**设计说明：** `docs/superpowers/specs/2026-11-04-codex-glory-launch-design.md`

## 全局约束

- 产品业务逻辑、测试代码、媒体生成和 Windows 适配使用 Python；PowerShell 只作为环境、测试、打包、安装和恢复的轻量入口。
- 运行环境固定为 CPython 3.14，依赖安装在项目内 `.venv`。
- 支持 Windows 10/11 x64 和 Microsoft Store 版 Codex。
- 当前正式媒体的分辨率、帧率、时长和时间点记录在设计说明与 `config/launcher.example.json` 中；启动逻辑不得写死具体时长。
- 配置必须满足 `0 <= HoldAt < TransitionStart < TransitionEnd < Duration`，关键帧必须位于媒体时长内。
- 首帧目标为 `<= 800 ms`，必须在打包版本中记录实测值。
- 使用 PyInstaller 的 `onedir` 模式，禁止默认使用 `onefile`。
- 不修改 Codex 安装目录、包文件、账号状态或聊天数据。
- `.reference/` 及项目文档登记的本地只读参考目录均为只读，不进入构建、不提交、不修改、不删除。
- 不复制没有明确许可证的源码；PySide6 和其他依赖的许可写入第三方声明。
- 原作角色、标志和合照只进入被 Git 忽略的 `assets/local/`。
- 未取得明确同意，不提交、不推送、不替换官方快捷方式、不开始新阶段。
- 行为、媒体流程或发布契约变化时，必须同步更新测试；不得把已知失败记录为可接受的残留风险。

## 文件结构

- `pyproject.toml`：包元数据、运行依赖、开发依赖和 pytest 配置。
- `src/glory_boot/__init__.py`：版本与公开入口。
- `src/glory_boot/main.py`：进程计时、配置加载、Qt 应用和顶层异常处理。
- `src/glory_boot/config.py`：JSON 配置读取、路径解析和校验。
- `src/glory_boot/diagnostics.py`：单实例互斥量、阶段计时和结构化日志。
- `src/glory_boot/domain/models.py`：不可变配置、矩形和关键帧模型。
- `src/glory_boot/domain/geometry.py`：DPI（每英寸像素比）、多显示器和客户区几何。
- `src/glory_boot/domain/timeline.py`：播放、停留、恢复、过渡和超时决策。
- `src/glory_boot/domain/policy.py`：故障与交接策略。
- `src/glory_boot/adapters/win32.py`：窗口、进程路径、DPI 和置顶封装。
- `src/glory_boot/adapters/dwm.py`：缩略图注册、更新和释放。
- `src/glory_boot/adapters/shell.py`：快捷入口和恢复。
- `src/glory_boot/services/codex_launcher.py`：`QProcess` 启动请求和去重。
- `src/glory_boot/services/media.py`：媒体播放器状态封装。
- `src/glory_boot/services/session.py`：并行启动、自适应等待和交接编排。
- `src/glory_boot/ui/boot_window.py`：海报、视频控件和用户输入。
- `src/glory_boot/ui/application.py`：窗口生命周期和单实例界面。
- `config/launcher.example.json`：默认配置。
- `scripts/bootstrap.ps1`：创建 `.venv` 并安装锁定依赖。
- `scripts/test.ps1`：运行 pytest 和仓库约束检查。
- `scripts/build.ps1`：使用 PyInstaller 配置构建 `onedir`。
- `scripts/install.ps1`：创建专用启动入口。
- `scripts/restore.ps1`：恢复本项目入口。
- `scripts/package.ps1`：生成压缩包和 SHA-256 校验值。
- `scripts/smoke_test.py`：媒体元数据、包内容和启动基准。
- `packaging/glory_boot.spec`：PyInstaller 配置。
- `tools/render_video.py`：用 Pillow/NumPy 合成帧并通过 imageio-ffmpeg 编码。
- `tests/conftest.py`：测试路径和 Qt 离屏环境。
- `tests/test_repository_contract.py`：忽略项、第三方声明和入口结构。
- `tests/test_config.py`：配置接受与拒绝用例。
- `tests/test_geometry.py`：显示器、DPI、客户区和最终覆盖。
- `tests/test_timeline.py`：提前就绪、晚到、停留、恢复和超时。
- `tests/test_policy.py`：媒体、DWM、激活失败与交接映射。
- `tests/test_launcher.py`：启动请求只发送一次且不阻塞调用方。
- `tests/test_ui_smoke.py`：离屏环境下的海报、媒体失败和 `Esc`。
- `media/startup.mp4`：当前正式动画。
- `media/poster.png`：首帧海报。
- `THIRD_PARTY_NOTICES.md`：参考项目、PySide6 和媒体工具许可。
- `README.md`：环境、运行、测试、打包、恢复和架构讲解。

## 重点审查项

- Codex 已在运行时不得重复启动，动画结束后必须交接现有主窗口。
- Codex 冷启动超过配置的 `HoldAt` 时动画仍完整播放；未就绪则停在最终帧，不应露出黑屏或提前关闭启动器。
- 多显示器、负坐标、DPI 缩放和非 16:9 窗口不得导致播放器越界或残留黑边。
- PySide6 或 QtMultimedia 插件缺失、视频损坏时必须仍能启动或恢复 Codex。
- PyInstaller 打包后的首帧不得明显慢于源码运行，并且 Qt 多媒体插件必须完整。

## 执行记录

| 日期 | 任务 | 状态 | 改动 | 验证 | 剩余风险 |
| --- | --- | --- | --- | --- | --- |
| 2026-11-04 | Python 方案修订 | 完成 | 约束、设计和计划改为全 Python | 完成依赖版本与许可调研 | 安装包首帧尚未验证 |
| 2026-11-04 | 依赖与源码基准 | 完成 | 创建项目内 `.venv`，安装 Python 3.14 兼容依赖 | PySide6 最小窗口首绘平均 379.6 毫秒；含媒体控件平均 600.1 毫秒 | 尚未构建 PyInstaller `onedir` 基准 |
| 2026-11-04 | 文档中文化 | 完成 | 计划标题、字段、任务和步骤全部改为中文；约束中增加文档语言规则 | 排除只读参考目录与 `.venv` 后检查全部项目 Markdown | 暂无 |
| 2026-11-04 | 任务 1：Python 项目骨架与依赖基线 | 完成 | 新增忽略规则、项目元数据、许可声明、引导与测试脚本、包入口 | `scripts/bootstrap.ps1` 成功；`scripts/test.ps1` 为 12 通过、0 失败；`.venv` 约 861 MiB | 当前没有初始提交，改动只能通过工作区差异审查 |
| 2026-11-04 | 任务 2：不可变配置与几何计算 | 完成 | 新增 `AppConfig`、`ScreenFrame`、`Rect`、JSON 加载校验和物理像素几何 | 目标测试 35 通过；全量测试 47 通过、0 失败 | 正式媒体文件尚未生成，示例配置只能在测试夹具中通过文件存在性校验 |
| 2026-11-04 | 任务 3：自适应时间线与交接策略 | 完成 | 新增播放动作、过渡进度、超时决策和全部交接原因映射 | 时间线与策略测试 24 通过；全量测试 71 通过、0 失败 | 交接策略尚未连接真实窗口和 DWM 服务 |
| 2026-11-04 | 任务 4：Win32 与 DWM 适配器 | 完成 | 新增唯一窗口筛选、响应性与激活封装、DWM 注册更新释放 | 适配器测试 13 通过；全量测试 84 通过、0 失败；未操作真实 Codex | 尚未在真实窗口上执行 DWM 集成验收 |
| 2026-11-04 | 任务 5：首帧海报、媒体播放与并发启动 | 自动测试完成 | 新增惰性媒体控件、线程安全一次性启动、阶段计时、进程入口和离屏界面 | 启动与界面测试 7 通过；全量测试增至 97 通过 | 基准需等任务 8 生成正式媒体后执行 |
| 2026-11-04 | 任务 6：自适应停留、DWM 交接与恢复 | 完成 | 新增 250 毫秒会话状态机、稳定窗口确认、DWM 过渡与淡出回退、统一交接 | 会话测试 6 通过；全量测试 97 通过、0 失败 | 真实 DWM 和激活行为仍需完整冷启动验收 |
| 2026-11-04 | 任务 5：启动基准补测 | 完成 | 接入媒体首帧和启动请求阶段，基准模式不产生外部启动副作用 | 源码基准：首帧 87.1 毫秒、媒体 100.0 毫秒、启动请求 88.0 毫秒 | 数值为离屏源码模式，不等同真实窗口冷启动 |
| 2026-11-04 | 任务 7：可恢复入口与打包 | 完成 | 新增快捷方式事务、安装/恢复、PyInstaller `onedir`、ZIP 与 SHA-256 | 全量测试 105 通过；发布包 267 个文件、约 153.2 MiB；压缩包 69,385,025 字节 | 专用入口已安装，官方入口未替换 |
| 2026-11-04 | 任务 8：官方媒体与自动验收 | 自动部分完成 | 使用官方宣传素材生成海报和 8 秒 H.264 视频；修复 ICU 入口冲突；兼容 Store 版 `ChatGPT.exe` | 媒体 1920×1080、60 fps、8.000 秒；Qt 解码通过；打包首帧 501.1 毫秒、媒体首帧 744.0 毫秒 | 需在用户的交互桌面完成真实 Store 版冷启动验收 |
| 2026-11-04 | 任务 8：成品抠图接入与发布重测 | 自动部分完成 | 使用秋月大人确定的两张成品抠图 `ye-xiu-characters.png`、`su-mucheng-characters.png` 重新生成正式海报和 8 秒视频，并重建 `onedir` 发布包 | 全量测试 107 通过；媒体与 Qt 解码通过；首次冷缓存可见窗口 613.3 毫秒、媒体首帧 866.9 毫秒；重复启动可见窗口 443.8 毫秒、媒体首帧 644.6 毫秒；压缩包 SHA-256 为 `46f9ab95d24ea5706f8bda8744675f0efcba7938020628ce42f93cde66574d3a` | 真实 Store 版冷启动仍需人工验收；媒体首帧首次冷缓存略超 800 毫秒，但首帧海报及时可见 |
| 2026-11-04 | 视觉要求归属调整 | 完成 | 从项目级 `AGENTS.md` 移除具体人物构图；将可迭代的开屏构图、色板、素材与分镜统一放入设计说明，并改为无人物黑金墨绿科技风 | 全量测试 107 通过；旧人物构图关键词已从项目约束、设计和计划中移除 | 新视觉媒体尚未生成，现有发布包仍为上一版人物画面；新会话或重启客户端后验证修改后的 `AGENTS.md` |
| 2026-11-04 | 专用桌面入口安装 | 完成 | 经秋月大人授权创建专用入口，不替换官方入口 | 快捷方式目标、工作目录、图标、模式与 SHA-256 均核对通过 | 冷启动验收需先完全退出当前 Codex |
| 2026-11-04 | 任务 8：无人物黑金墨绿媒体重制 | 自动部分完成 | 重写 `tools/render_video.py`，程序化绘制徽记、翼状弧线、黑玻璃状态条和墨绿烟雾；新增渲染器私有素材解耦与深色色板测试；替换正式海报和 8 秒视频，重建发布包 | 目标测试 2 通过；全量测试 109 通过；媒体 1920×1080、60 fps、8.000 秒、Qt 解码通过；打包可见窗口 430.6 ms、媒体首帧 655.4 ms、启动请求 433.9 ms；压缩包 SHA-256 为 `11495791f31e68a2d6c68407ead76919a3e9b4e6c8572a8b0eaf7ec9a417076d` | 真实 Store 版冷启动、等待画面、DWM 交接和 `Esc` 仍需秋月大人在交互桌面验收 |
| 2026-11-04 | 发布包日志隔离 | 完成 | 修改 `scripts/package.ps1`，压缩前清除发布目录中的运行日志；修改 `scripts/smoke_test.py` 检查 ZIP 不含 `logs/` | 日志断言先失败于 `logs/benchmark.json`，修复后全量烟雾检查通过：`archive_ok logs=excluded` | 尚无 |
| 2026-11-05 | v2 十区黑场迭代 | 样片完成 | 修改 `tools/render_lookdev_v2.py`，支持从外部视频提取 `0.72–1.56s` 共 21 帧，在 `6.92–7.76s` 接入交接黑场；新增 `tests/test_render_lookdev_v2.py`；本地输出 `assets/local/output/lookdev-v2-ten-zone/lookdev-preview.mp4` | v2 目标测试 3 通过；抽取帧数 21、尺寸 1920×1080；成片 1920×1080、30 fps、8.000 秒；逐帧核对 `6.94s` 接入、`7.05–7.68s` 保留十区弹出与闪切、`7.78s` 后回到 CODEX 就绪收尾；全量为 111 通过、1 个既有失败 | 既有 `tests/test_render_video.py` 仍要求已废弃的本地 Logo 素材，与当前程序化徽记实现不一致；样片尚未替换正式 `media/startup.mp4` |
| 2026-11-05 | 荣耀丨codex 结尾改写样片 | 样片完成，待目视验收 | 新增 `tools/render_ten_zone_ending.py` 和 `tests/test_render_ten_zone_ending.py`；保留 `glory1.mp4` 主画面，约 `7.17s` 接入 `glory.mp4` 的十区段；用标题出现前底图清除旧“十区”；标题缩小到背景中央框安全区，改为方块字形、细红描边、暗色内芯和稀疏点阵高光；删除 Codex 黑屏结尾并停在改写后的荣耀画面；更新设计说明 | 目标测试 5 通过；样片 1920×1080、30 fps、8.000 秒、240 帧；末帧平均 RGB 为 `26.20/5.16/7.14`、非黑区域占 35.16%；全量测试 116 通过、1 个既有失败 | 中央主标题已替换，画面底部小字“荣耀十区”仍保留；当前样片为 30 fps，正式 `media/startup.mp4`（60 fps）尚未替换，需秋月大人目视确认后再决定 |
| 2026-11-05 | 前六秒分层动效修订 | 样片完成，待目视验收 | 锁定前 0.8 秒画面尺度；增加柔和起亮、分段环形点亮、侧边数据轨道、五段扫描光带、能量脉冲和少量上升粒子，保留四边故障切线与十区结尾 | 专项测试 8 通过；成片 1920×1080、30 fps、8.000 秒、240 帧；全量测试 119 通过、1 个既有失败 | 动效均为确定性程序化叠加；需秋月大人确认强度与方向，正式 `media/startup.mp4` 尚未替换 |
| 2026-11-05 | 前六秒七阶段效果重排 | 样片完成，待目视验收 | 不再全程叠加同一组光效，改为粒子汇聚、环形校准、双段光刃、数字故障、能量爆发、纵向扫描锁定、蓄力交接七个阶段；保留三次推进与回拉及固定开场尺度 | 专项测试 10 通过；成片 1920×1080、30 fps、8.000 秒、240 帧；全量测试 121 通过、1 个既有失败 | 各阶段主视觉效果已分开；仍需秋月大人目视判断节奏与强度，正式 `media/startup.mp4` 尚未替换 |
| 2026-11-05 | 正式媒体接入启动器 | 程序资源已替换 | 将七阶段动画按正式规格重制为 60 fps、480 帧，替换 `media/startup.mp4`；从成片首帧生成 `media/poster.png`；旧媒体备份到本地忽略目录；重建 `dist/GloryCodexBoot` 和发布压缩包 | 专项测试 11 通过；全量测试 123 通过、1 个既有失败；媒体烟雾检查通过：8.000 秒、60 fps、1920×1080、Qt 解码正常；发布包包含 2 个 Qt 多媒体插件且压缩包不含日志；打包版离屏基准：可见窗口 93.99 ms、媒体请求 94.85 ms、媒体首帧 115.71 ms、启动请求 95.23 ms；压缩包 SHA-256 为 `d710e454eb6f24051a02c10d088bee194be400f9c256b85c0ea56dc671a70b29` | 未自行启动真实 Codex；真实桌面冷启动、晚启动停留、DWM 交接和 `Esc` 仍需秋月大人人工验收 |
| 2026-11-06 | 过期媒体契约与验证状态同步 | 完成 | 将固定 8 秒和默认时间点从项目长期规则降级为设计、配置和当前媒体事实；把旧本地 Logo 测试替换为程序化徽记与无私有素材依赖测试；增加非 8 秒配置的时间线回归用例；README 改为带日期的最近验证结果；清理项目规则中的阶段路线图和机器专属参考路径 | `tests/test_render_video.py` 2 通过；非 8 秒时间线用例通过；全量测试 125 通过、0 失败；源码编译检查通过 | 当前正式媒体仍为 8 秒；未来更换媒体时必须同步配置、设计、媒体测试和本计划 |
| 2026-11-08 | 荣耀开屏最终重剪、就绪门控与自然交接 | 完成自动验证 | 使用本地 `glory1.mp4` 与 `glory.mp4` 重排为约 `5.2/2.8` 秒，增加 0.3 秒亮度桥接；结尾扩展并稳定停留；等待点与交接改为 `6.4/6.7/7.6` 秒；等待提示移至右上；后半段原有伪按钮、“荣耀十区”和 HUD 全部保留；前段仅在 0.8–2.4 秒进行一次不超过 2.5% 的缓慢靠近，之后固定构图；移除结尾标题持续横向错位故障；动画始终完整播放，在 `duration - 50 ms` 提前暂停于视频自身末帧并至少保留 2.5 秒；窗口与日志探测移至后台线程，日志挂载标记优先，持续窗口 8 秒兜底，全局 `Esc` 保证可跳过；交接先聚焦 Codex，再以 360 ms 平滑淡出启动器；同步媒体、海报、设计、配置、README 与测试 | 全量测试 147 通过、0 失败；桥接区最大采样亮度跳变约 4.04；标题等待区间画面差约 0.014；媒体 1920×1080、60 fps、8.000 秒，Qt 解码通过；海报与首帧像素差为 0；打包基准窗口 433.1 ms、媒体首帧 640.0 ms、启动请求 436.7 ms；压缩包 SHA-256 为 `e523508b787a0557d608650f55a128e2e7001ffa73e241d4e6bdb3e9485329b3` | 尚未在更新后的发布包上再次执行真实 Store 版冷启动验收；当前本地素材仍不得公开分发 |
| 2026-11-09 | 首次激活丢失与自动重试 | 完成自动验证 | 根据本地日志确认第一次点击发生在旧 Codex 完成退出前约 2 秒，Windows Shell 接受了请求但没有创建新实例；`CodexLauncher` 增加明确重试入口，`SessionController` 读取启动结果并在结构化失败后 1 秒重试，在请求看似成功但 8 秒内没有主窗口时再次激活，最多三次，主界面就绪后停止重试；额外覆盖旧 Codex 关闭窗口被误判为可复用实例的边界 | 相关启动与会话测试先失败后通过，共 28 通过；全量测试 153 通过、0 失败；媒体烟雾检查通过；重建发布包后基准窗口 449.6 ms、媒体首帧 654.6 ms、启动请求 452.3 ms；压缩包 SHA-256 为 `fb8228bc275d1c3e094fbb00591ab58961b74f908fb3e6d4dad636b6552d97d1` | 尚需从桌面专用入口复测“关闭 Codex 后立即点击一次即可启动”；发布包基准仍使用无外部启动副作用后端 |
| 2026-11-17 | 任务栏图标排查中的误改 | 已撤销 | 初期误把动画窗口任务栏图标当成应用图标和桌面快捷方式图标处理，尝试修改 `app-icon.ico` 小尺寸层；确认任务目标后恢复应用图标原状，仅保留独立运行时任务栏图标方案 | `git restore` 恢复 `app-icon.ico`；后续改用 `taskbar-icon.ico` 与窗口 AppUserModelID | 应用图标和桌面快捷方式图标保持原样 |

| 2026-11-17 | 撤除 Spec Kit | 完成 | 项目已接近完成，现有 `AGENTS.md`、设计说明和实施计划足以覆盖流程；删除本次接入生成的 `.agents/`、`.specify/` 与 `THIRD_PARTY_NOTICES.md` 中的 Spec Kit 声明，不修改业务代码、项目规则或现有计划文档 | 删除前确认目录仅包含 Spec Kit 内容；全量测试通过、发布烟雾检查通过；工作区无 Spec Kit 残留 | Spec Kit 本地 CLI 安装 `D:\codex项目\SpecKit` 未删除，仍供其他项目独立使用 |
| 2026-11-17 | 动画窗口独立任务栏图标 | 完成自动验证 | 新增可替换 `assets/taskbar-icon.ico`；动画窗口显示后通过 `WM_SETICON` 设置大、小图标，并通过窗口 `IPropertyStore` 写入 `System.AppUserModel.RelaunchIconResource` 与显式 AppUserModelID；任务栏图标与 EXE、桌面快捷方式图标解耦，关闭时清除窗口属性并释放图标句柄 | 目标测试先失败后通过；全量测试 309 通过、0 失败；发布烟雾检查通过；源任务栏图标与发布资源 SHA-256 均为 `475E5EE0A232830C37A2731B61ADA0B8CFAB76ABCA98BD12F3488F40083296FB`；已重建 `dist/GloryCodexBoot` | 任务栏外观属于 Windows 交互行为，最终仍需完整退出 Codex 后从桌面入口人工确认；发布目录中的 `assets\taskbar-icon.ico` 可直接替换，无需重新构建 |
| 2026-11-17 | 清理未使用本地素材 | 完成 | 确认项目仅有一个 `assets/local` 目录，包含两张历史人物原图、来源记录和占位文件；代码、测试、媒体生成和打包均不依赖该目录，经明确授权整体移入 Windows 回收站 | 全量测试 308 通过、0 失败；`assets/local` 已不存在，Git 忽略规则仍通过 | 素材可从回收站恢复；历史计划中的路径记录继续作为历史事实保留 |

每完成一项任务，就追加日期、文件、命令、输出、结果和风险。不得用“看起来正常”替代实际记录。

---

### 任务 1：Python 项目骨架与依赖基线

**涉及文件：**

- 新建：`.gitignore`
- 新建：`pyproject.toml`
- 新建：`README.md`
- 新建：`THIRD_PARTY_NOTICES.md`
- 新建：`scripts/bootstrap.ps1`
- 新建：`scripts/test.ps1`
- 新建：`tests/test_repository_contract.py`

**接口：**

- 产出一个可导入的 `glory_boot` 包、项目虚拟环境、固定依赖、pytest 配置和仓库忽略规则。

- [x] **步骤 1：先写会失败的仓库约束测试**

断言 `.venv/`、`.reference/`、`assets/local/`、`build/`、`dist/`、`logs/`、`.pytest_cache/` 和 `__pycache__/` 均被忽略；必需声明存在；`pyproject.toml` 声明 Python `>=3.14,<3.15`。

- [x] **步骤 2：运行测试并确认失败**

运行：`python -m pytest tests/test_repository_contract.py -v`

预期：失败，因为项目骨架尚不存在。

- [x] **步骤 3：创建项目骨架和固定依赖**

创建 `.gitignore`、`pyproject.toml`、`README.md`、`THIRD_PARTY_NOTICES.md`。运行依赖固定为 `PySide6==6.12.0`；开发依赖固定为 `pytest==9.2.0`、`PyInstaller==6.22.3`、`Pillow==13.0.0`、`NumPy==2.5.4`、`imageio-ffmpeg==0.8.1`。

- [x] **步骤 4：实现依赖引导脚本**

`scripts/bootstrap.ps1` 使用当前 CPython 3.14 创建 `.venv`、升级 pip、以可编辑模式安装项目和开发依赖，并输出精确的 `pip freeze` 结果。

- [x] **步骤 5：运行引导脚本和约束测试**

运行：`powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\bootstrap.ps1`

运行：`.\.venv\Scripts\python.exe -m pytest tests\test_repository_contract.py -v`

预期：通过。

- [x] **步骤 6：阶段检查**

汇报依赖版本、`.venv` 体积和测试结果。没有明确同意不得提交。

---

### 任务 2：不可变配置与几何计算

**涉及文件：**

- 新建：`src/glory_boot/domain/models.py`
- 新建：`src/glory_boot/domain/geometry.py`
- 新建：`src/glory_boot/config.py`
- 新建：`config/launcher.example.json`
- 新建：`tests/test_config.py`
- 新建：`tests/test_geometry.py`

**接口：**

- 产出 `ScreenFrame`、`Rect` 和 `AppConfig` 不可变数据类。
- 产出 `load_config(root: Path) -> AppConfig`、`validate_config(config: AppConfig) -> None`。
- 产出 `centered(...) -> Rect`、`window_for_client(...) -> Rect`、`destination_at(...) -> Rect`。
- `AppConfig` 字段必须与设计说明中的 JSON 键一致，进程名和关键帧使用元组。

- [x] **步骤 1：先写配置失败用例**

接受示例配置；拒绝缺失视频或海报、无效应用标识、空进程名、时间不递增、`MaxWaitSeconds < 10`、音量不在 `0..1`、非有限数值、零尺寸关键帧、重复时间以及超出规范化屏幕范围的关键帧。

- [x] **步骤 2：先写几何失败用例**

覆盖 1080p、1440p、4K、负坐标显示器、竖屏显示器、不同的窗口与客户区边距，以及最终矩形精确铺满播放器。

- [x] **步骤 3：运行测试并确认失败**

运行：`powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\test.ps1`

预期：失败，因为 `glory_boot.domain` 模块不存在。

- [x] **步骤 4：实现模型、读取、校验和几何**

使用 `dataclasses`、`pathlib`、`json`、`math.isfinite` 和规范化屏幕关键帧。`domain/` 中不得导入 PySide6 或 `ctypes`。

- [x] **步骤 5：运行目标和全量测试**

运行：`.\.venv\Scripts\python.exe -m pytest tests\test_config.py tests\test_geometry.py -v`

运行：`powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\test.ps1`

预期：通过。

- [x] **步骤 6：阶段检查**

汇报测试数量和公开数据类签名。没有明确同意不得提交。

---

### 任务 3：自适应时间线与交接策略

**涉及文件：**

- 新建：`src/glory_boot/domain/timeline.py`
- 新建：`src/glory_boot/domain/policy.py`
- 新建：`tests/test_timeline.py`
- 新建：`tests/test_policy.py`

**接口：**

- 产出 `PlaybackAction` 枚举，包含 `CONTINUE`、`HOLD`、`RESUME`、`TIMEOUT`。
- 产出 `TimelineDecision(action, transition_progress)`。
- 产出 `evaluate_timeline(config, media_seconds, app_ready, waited_seconds) -> TimelineDecision`。
- 产出 `HandoffReason`、`HandoffDecision` 和 `HandoffPolicy.decide(reason)`，包含 `reveal_existing_window`、`show_error` 和 `exit_launcher` 字段。

- [x] **步骤 1：先写时间线失败用例**

断言 6.3 秒前不停留；6.3 秒时 Codex 未就绪则停留；就绪后恢复；提前就绪不暂停；过渡进度在 6.8、7.2、7.6 秒分别为 `0.0`、`0.5`、`1.0`；60 秒时触发超时。

- [x] **步骤 2：增加晚到回归用例**

模拟 `6.3 -> HOLD`、`12.0 -> HOLD`、`就绪 -> RESUME`，断言不会跳过或重启过渡。

- [x] **步骤 3：先写交接策略失败用例**

将 `COMPLETED` 和 `SKIPPED` 映射为显示现有窗口并退出；`MEDIA_FAILED` 和 `DWM_UNAVAILABLE` 映射为安全交接；`TIMEOUT` 根据窗口是否存在决定交接或报错；`ACTIVATION_FAILED` 显示错误并退出。

- [x] **步骤 4：运行测试并确认失败**

运行：`.\.venv\Scripts\python.exe -m pytest tests\test_timeline.py tests\test_policy.py -v`

预期：失败，因为时间线和策略模块不存在。

- [x] **步骤 5：实现纯状态与策略**

所有函数必须确定、可测试，不依赖 Qt、文件系统、真实时钟或 Windows API；已等待时间由参数传入。

- [x] **步骤 6：运行测试**

运行：`powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\test.ps1`

预期：通过。

- [x] **步骤 7：阶段检查**

将时间线和策略用例追加到执行记录。没有明确同意不得提交。

---

### 任务 4：Win32 与 DWM 适配器

**涉及文件：**

- 新建：`src/glory_boot/adapters/__init__.py`
- 新建：`src/glory_boot/adapters/win32.py`
- 新建：`src/glory_boot/adapters/dwm.py`
- 新建：`tests/test_win32.py`

**接口：**

- 产出 `WindowInfo(hwnd, pid, process_path, client_rect, responsive)`。
- 产出 `find_codex_window(config: AppConfig) -> WindowInfo | None`、`is_responsive(hwnd: int) -> bool`、`focus_window(hwnd: int) -> None`。
- 产出 `DwmController.register(source_hwnd)`、`update(destination: Rect, opacity: float, visible: bool)`、`close()`。

- [x] **步骤 1：先写窗口筛选失败用例**

注入伪造窗口记录，拒绝不可见窗口、工具窗口、被系统隐藏的窗口、错误进程路径、过小客户区和无响应窗口；只接受唯一且稳定的匹配窗口。

- [x] **步骤 2：增加 DWM 生命周期用例**

使用伪造后端，断言注册只调用一次、透明度转换为 `0..255`、`close()` 只释放一个句柄，重复关闭安全。

- [x] **步骤 3：运行测试并确认失败**

运行：`.\.venv\Scripts\python.exe -m pytest tests\test_win32.py -v`

预期：失败，因为适配器不存在。

- [x] **步骤 4：实现 ctypes 定义与适配器**

Win32 结构和函数签名只定义一次；每个 `OpenProcess` 句柄都必须关闭；禁止按标题匹配窗口。

- [x] **步骤 5：运行测试**

运行：`powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\test.ps1`

预期：通过，而且不打开、不关闭真实 Codex 窗口。

- [x] **步骤 6：阶段检查**

汇报原生函数签名和句柄生命周期测试。不得操作正在运行的 Codex。

---

### 任务 5：首帧海报、媒体播放与并发启动

**涉及文件：**

- 新建：`src/glory_boot/__init__.py`
- 新建：`src/glory_boot/main.py`
- 新建：`src/glory_boot/diagnostics.py`
- 新建：`src/glory_boot/services/__init__.py`
- 新建：`src/glory_boot/services/codex_launcher.py`
- 新建：`src/glory_boot/services/media.py`
- 新建：`src/glory_boot/services/session.py`
- 新建：`src/glory_boot/ui/__init__.py`
- 新建：`src/glory_boot/ui/application.py`
- 新建：`src/glory_boot/ui/boot_window.py`
- 新建：`tests/test_launcher.py`
- 新建：`tests/test_ui_smoke.py`
- 新建：`tests/conftest.py`

**接口：**

- 使用配置、模型、窗口适配器、时间线和策略。
- 产出 `CodexLauncher.request_once() -> LaunchResult`。
- 产出 `MediaController.open(path)`、`pause_at(seconds)`、`resume()`、`stop()`。
- 产出 `BootWindow.show_poster_first(path)` 和 `StageTimer.mark(name)`。
- `main.main(argv: list[str] | None = None) -> int` 是进程入口。

- [x] **步骤 1：先写启动并发失败用例**

使用伪造进程后端并发调用，断言只发出一次 Codex 激活请求；已有窗口时不启动；启动异常返回结构化失败；调用不会阻塞界面线程。

- [x] **步骤 2：先写界面冒烟失败用例**

设置 `QT_QPA_PLATFORM=offscreen`，断言海报在播放器加载前可见；`Esc` 只触发一次交接；海报缺失时仍打开黑色恢复窗口而不是崩溃。

- [x] **步骤 3：运行测试并确认失败**

运行：`.\.venv\Scripts\python.exe -m pytest tests\test_launcher.py tests\test_ui_smoke.py -v`

预期：失败，因为服务和界面模块不存在。

- [x] **步骤 4：实现进程入口和阶段计时**

创建 Qt 应用，加载配置，启用命名互斥量单实例保护，显示窗口并记录单调时钟。捕获顶层异常，显示简短恢复提示。

- [x] **步骤 5：实现海报优先窗口**

创建无边框、黑色、置顶窗口；把海报作为首帧内容；首次显示后才创建 `QVideoWidget` 和 `QMediaPlayer`，连接 `mediaStatusChanged` 与 `errorOccurred`。

- [x] **步骤 6：实现并发启动**

在 `window_visible` 后从工作线程调用 `CodexLauncher.request_once()`。使用线程安全的一次性状态，并通过 Qt 信号把结果送回界面线程。

- [x] **步骤 7：运行测试和启动基准**

运行：`powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\test.ps1`

运行：`.\.venv\Scripts\python.exe -m glory_boot --benchmark`

预期：测试通过；基准输出 `window_visible_ms`、`media_requested_ms`、`codex_launch_requested_ms`，且首帧不是空白界面。

- [x] **步骤 8：阶段检查**

记录源码模式启动时间和 PySide6 导入时间。尚不进行真实 Codex 冷启动验收。

---

### 任务 6：自适应停留、DWM 交接与恢复

**涉及文件：**

- 修改：`src/glory_boot/services/session.py`
- 修改：`src/glory_boot/services/media.py`
- 修改：`src/glory_boot/ui/boot_window.py`
- 修改：`src/glory_boot/adapters/dwm.py`
- 新建：`tests/test_session.py`
- 修改：`tests/test_timeline.py`
- 修改：`tests/test_policy.py`

**接口：**

- 产出 `SessionController.start()` 和可重复调用的 `SessionController.handoff(reason)`。
- 发出 `hold_started`、`hold_finished`、`handoff_started` 和 `handoff_completed` 信号。

- [x] **步骤 1：先写会话失败用例**

使用伪造媒体、窗口探测器和 DWM 对象，断言 6.3 秒停留、就绪后恢复、交接不重复、DWM 失败时选择透明度回退、超时退出等待、媒体失败仍请求启动 Codex。

- [x] **步骤 2：运行测试并确认失败**

运行：`.\.venv\Scripts\python.exe -m pytest tests\test_session.py -v`

预期：失败，因为 `SessionController` 尚未完成。

- [x] **步骤 3：实现会话状态机**

使用间隔 250 毫秒的 `QTimer` 探测窗口，不阻塞界面线程。播放到 `HoldAt` 时暂停并显示 `Codex正在启动… Esc跳过`，检测到 `codex_stable` 后恢复。

- [x] **步骤 4：实现 DWM 过渡**

用 `destination_at` 映射规范化关键帧；在过渡开始和结束之间逐帧更新透明度；窗口关闭前释放缩略图。注册失败时改为启动器窗口自身淡出。

- [x] **步骤 5：覆盖全部交接原因**

`Esc`、播放完成、超时、媒体失败、DWM 失败和激活失败统一经过 `HandoffPolicy`。

- [x] **步骤 6：运行测试**

运行：`powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\test.ps1`

预期：会话和所有失败路径测试通过。

- [x] **步骤 7：阶段检查**

记录完整失败矩阵。真实 Codex 冷启动测试前必须取得同意。

---

### 任务 7：可恢复入口与打包

**涉及文件：**

- 新建：`src/glory_boot/adapters/shell.py`
- 新建：`scripts/install.ps1`
- 新建：`scripts/restore.ps1`
- 新建：`scripts/build.ps1`
- 新建：`scripts/package.ps1`
- 新建：`packaging/glory_boot.spec`
- 新建：`tests/test_shell.py`
- 修改：`README.md`

**接口：**

- 产出专用 `Codex 荣耀启动` 快捷方式。
- 产出可选、需显式启用的官方入口替换。
- 产出包含目标、参数、图标和 SHA-256 的备份记录与恢复操作。
- 产出 `build/GloryCodexBoot/` 和 `dist/GloryCodexBoot-win-x64.zip`。

- [x] **步骤 1：先写快捷方式失败用例**

在临时目录断言安装可重复执行、中文路径正常、备份与恢复信息准确、拒绝覆盖无关快捷方式，而且不修改真实桌面。

- [x] **步骤 2：运行测试并确认失败**

运行：`.\.venv\Scripts\python.exe -m pytest tests\test_shell.py -v`

预期：失败，因为快捷方式适配器不存在。

- [x] **步骤 3：实现专用入口与恢复**

只在安装脚本中使用 PowerShell 的组件对象模型接口创建快捷方式；目标和备份数据必须先校验。官方入口替换保持显式选择。

- [x] **步骤 4：实现 PyInstaller `onedir`**

使用 `--windowed --onedir`，包含 `media/`、配置模板、Qt 多媒体插件和 PySide6 平台插件。禁止使用 UPX 压缩。

- [x] **步骤 5：构建并检查发布包**

运行：`powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build.ps1`

运行：`powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\package.ps1`

预期：程序可启动；`dist` 包含 Qt 多媒体插件和媒体文件；不包含 `.venv`、`.reference`、缓存、日志或本地素材。

- [x] **步骤 6：运行打包版启动基准**

运行：`powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\package.ps1 -Benchmark`

预期：首帧 `<= 800 ms`，否则必须记录瓶颈分析。

- [x] **步骤 7：阶段检查**

汇报压缩包体积、SHA-256、源码与打包版基准以及恢复步骤。没有明确同意不修改真实快捷方式。

---

### 任务 8：荣耀媒体、端到端验收与展示说明

**涉及文件：**

- 新建：`tools/render_video.py`
- 新建：`assets/local/.gitkeep`
- 新建：`media/startup.mp4`
- 新建：`media/poster.png`
- 新建：`scripts/smoke_test.py`
- 修改：`config/launcher.example.json`
- 修改：`README.md`
- 修改：`docs/superpowers/plans/2026-11-04-codex-glory-boot.md`

**接口：**

- 使用此前全部模块和已批准视觉素材。
- 产出 H.264 视频、匹配海报、校准后的屏幕关键帧、最终发布包、启动指标和完整执行记录。

- [x] **步骤 1：制作程序化视觉素材和渲染工具**

按设计说明绘制无人物黑金墨绿荣耀开场界面，不使用原作角色、现成游戏截图或官方 Logo；用 Pillow/NumPy 生成确定性帧，再由 imageio-ffmpeg 编码。渲染器不得依赖 `assets/local/`。

- [x] **步骤 2：校验媒体元数据**

运行：`.\.venv\Scripts\python.exe scripts\smoke_test.py --assets-only`

预期：通过；时长为 `8.0 ± 0.1 s`，尺寸 `1920×1080`，帧率 60，海报存在，Qt 可解码 H.264。

- [x] **步骤 3：校准过渡关键帧**

预览视频并设置规范化 `ScreenFrames`，保证最终矩形精确覆盖播放器，中间帧跟随画面开口。

- [x] **步骤 4：运行全部自动测试**

运行：`powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\test.ps1`

预期：配置、几何、时间线、策略、启动、会话、快捷方式、界面冒烟和打包检查全部通过。

- [ ] **步骤 5：请求真实冷启动验收**

请秋月大人完全退出 Codex 后，从专用入口启动，并记录：

- 首个可见画面时间；
- 媒体首帧和 Codex 启动请求时间；
- Codex 主窗口就绪时间；
- 晚启动时是否停在等待画面；
- DWM 交接和 `Esc` 行为；
- 快捷入口恢复结果。

没有明确同意，不得结束或重启 Codex。

- [x] **步骤 6：更新执行记录和展示说明**

追加命令、输出、测量值、剩余风险，以及一段适合面试讲解的架构摘要。只有真实验收通过后才能标记完成。

- [x] **步骤 7：最终检查**

已汇报第一阶段自动验证和剩余人工验收项；替换官方快捷方式与开始兴欣界面皮肤阶段仍需分别取得授权。

### 任务 9：过期媒体契约与验证状态同步

**涉及文件：**

- 修改：`AGENTS.md`
- 修改：`README.md`
- 修改：`tests/test_render_video.py`
- 修改：`tests/test_timeline.py`
- 修改：`docs/superpowers/specs/2026-11-04-codex-glory-launch-design.md`
- 修改：`docs/superpowers/plans/2026-11-04-codex-glory-boot.md`

**接口：**

- 项目长期规则只保留启动器工程不变量，不再固化当前成片的时长、默认时间点和阶段路线图。
- 正式媒体的分辨率、帧率、时长和时间点由设计说明、配置和当前渲染产物共同定义。
- 渲染测试必须验证当前程序化视觉，不得继续要求已废弃的本地 Logo 素材。
- README 的验证结果必须标明日期，并且不得把旧构建的性能、体积和哈希描述为当前状态。

- [x] **步骤 1：复现过期测试**

运行：`.\.venv\Scripts\python.exe -m pytest tests\test_render_video.py::test_renderer_uses_exact_local_logo_asset -q`

预期：失败，因为正式渲染器已经使用程序化徽记，不再读取本地 Logo。

- [x] **步骤 2：替换为当前渲染契约测试**

验证程序化徽记在停留时间点可见，并在没有 `assets/local/` 的临时工作目录中仍可渲染；使用 10 秒配置验证时间线不会写死 8 秒。

- [x] **步骤 3：同步长期规则与当前文档**

从 `AGENTS.md` 移除固定 8 秒、默认时间点、阶段路线图、机器专属参考路径和易漂移的依赖枚举；更新设计说明、README 和计划中的当前事实。

- [x] **步骤 4：运行目标测试**

运行：`.\.venv\Scripts\python.exe -m pytest tests\test_render_video.py tests\test_timeline.py -q`

结果：18 通过。

- [x] **步骤 5：运行全量验证**

运行：`powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\test.ps1`

结果：125 通过、0 失败；`compileall` 通过。
