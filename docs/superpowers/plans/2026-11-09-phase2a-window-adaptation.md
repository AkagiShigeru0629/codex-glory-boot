# 第二阶段 A 启动器窗口适配实施计划

> **执行代理须知：** 必须使用 `superpowers:subagent-driven-development` 或 `superpowers:executing-plans`，按任务顺序执行本计划，并用复选框记录进度。本计划不包含提交、推送、真实 Codex 冷启动或替换官方入口；这些操作需要另行取得秋月大人的明确同意。

**目标：** 等待 Codex 主窗口稳定后，让独立启动器按照其整窗可见外框开始播放，并完成同矩形 DWM 交接。

**架构：** 冷启动时启动器窗口保持隐藏，Codex 在后台启动。目标主窗口连续稳定后，通过 DWM 扩展外框读取整窗可见矩形，设置启动器物理几何，再显示海报、附加媒体并开始播放。动画视口和 DWM 目标共用该矩形；达到配置等待上限仍未取得稳定窗口时显示失败状态。

**技术栈：** CPython 3.14、PySide6 6.12、QtMultimedia、Python `ctypes`、pytest、PyInstaller onedir。

**设计说明：** `docs/superpowers/specs/2026-11-09-phase2-window-and-wallpaper-design.md`

## 全局约束

- 2026-11-12 起，正常冷启动必须等待 Codex 主窗口稳定后再显示和播放；旧的“立即首帧”约束仅作为第一阶段历史记录。
- 启动器隐藏等待必须受 `MaxWaitSeconds` 限制，不能永久无反馈。
- 窗口适配只执行一次，不持续跟随 Codex 窗口移动或缩放。
- 所有坐标和持久化尺寸使用物理像素。
- 支持负坐标、多显示器、125%／150% DPI、普通窗口和最大化窗口。
- `domain/` 只包含纯 Python 逻辑，不导入 PySide6、`ctypes` 或文件系统。
- 产品业务逻辑、测试和 Windows 适配继续使用 Python，不新增依赖。
- 不记录窗口标题、截图、聊天内容或用户数据。
- 每个任务先写失败测试，再写最小实现。
- 每个任务结束运行目标测试；最终运行：
  `powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\test.ps1`
- 不自动提交；执行 `git status --short` 和差异检查后等待秋月大人决定。
- 不自行启动、结束、重启或覆盖正在运行的 Codex。

## 审查重点

- Codex 主窗口稳定前不得显示会随后跳大的小窗口；稳定后才允许首次可见。
- 目标窗口位于负坐标显示器或不同 DPI 显示器时，启动器、媒体视口和 DWM 目标必须保持一致。
- 校准完成前媒体不能开始播放，首次播放只能请求一次。
- Codex 窗口在校准前后消失、最小化或移动时，启动器仍必须能够超时回退到可操作的 Codex 或明确错误。
- 用户可见区域必须覆盖 Codex 整窗外框，不能只覆盖客户区而露出标题栏或边框。

## 文件结构

- 新增 `src/glory_boot/domain/placement.py`：默认矩形和可见性判断等纯函数。
- 新增 `src/glory_boot/adapters/window_state.py`：上次有效整窗外框 JSON 的原子读写。
- 修改 `src/glory_boot/adapters/win32.py`：DWM 整窗可见外框和物理矩形定位。
- 新增 `src/glory_boot/services/window_placement.py`：选择初始视口、执行一次校准和记录成功几何。
- 修改 `src/glory_boot/services/session.py`：在 Codex 窗口稳定时通知应用执行一次校准。
- 修改 `src/glory_boot/ui/application.py`：接入初始几何、校准回调、视口提供者和成功记录。
- 修改 `tests/test_session.py`、`tests/test_win32.py`；新增 `tests/test_placement.py`、`tests/test_window_state.py`、`tests/test_window_placement.py`。
- 修改 `README.md`：实现与验证完成后同步第二阶段 A 的当前事实。

---

### 任务 1：定义安全默认矩形和显示器可见性

**文件：**

- 新增：`src/glory_boot/domain/placement.py`
- 新增：`tests/test_placement.py`

**接口：**

- `default_launcher_rect(work_area: Rect, *, coverage: float = 0.7, aspect_width: int = 1920, aspect_height: int = 1080) -> Rect`
- `is_rect_visible(rect: Rect, monitors: tuple[Rect, ...], *, minimum_width: int = 64, minimum_height: int = 64) -> bool`

**消费：** 现有 `Rect`。

**产出：** 应用初始化使用的安全矩形，以及历史几何的有效性判断。

- [x] **步骤 1：写失败测试**

在 `tests/test_placement.py` 写入：

```python
import pytest

from glory_boot.domain.models import Rect
from glory_boot.domain.placement import default_launcher_rect, is_rect_visible


def test_default_launcher_rect_fits_sixteen_by_nine_inside_coverage() -> None:
    result = default_launcher_rect(Rect(0, 0, 1920, 1040))

    assert result.x == pytest.approx(312.8888888889)
    assert result.y == 156
    assert result.width == pytest.approx(1294.2222222222)
    assert result.height == 728


def test_default_launcher_rect_supports_negative_work_area() -> None:
    result = default_launcher_rect(Rect(-2560, 0, 2560, 1440))

    assert result == Rect(-2176, 216, 1792, 1008)


def test_is_rect_visible_requires_minimum_intersection() -> None:
    monitors = (Rect(-1920, 0, 1920, 1080), Rect(0, 0, 2560, 1440))

    assert is_rect_visible(Rect(-100, 100, 800, 600), monitors)
    assert not is_rect_visible(Rect(-1900, 100, 50, 50), monitors)
```

- [x] **步骤 2：运行测试并确认失败**

运行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_placement.py -v
```

预期：`ModuleNotFoundError` 或无法导入新增函数。

- [x] **步骤 3：实现纯函数**

`default_launcher_rect` 先在 `work_area` 内缩进得到可用区域，再调用现有 `centered` 保持 16:9。`is_rect_visible` 检查矩形与任一显示器交集的宽高是否同时达到最小值；所有输入不是有限正尺寸时返回安全结果或抛出 `ValueError`。

- [x] **步骤 4：运行目标测试**

运行同一命令，预期全部通过。

---

### 任务 2：持久化上一次有效的客户区

**文件：**

- 新增：`src/glory_boot/adapters/window_state.py`
- 新增：`tests/test_window_state.py`

**接口：**

- `WindowStateStore(path: Path)`
- `WindowStateStore.load() -> Rect | None`
- `WindowStateStore.save(rect: Rect) -> None`

**消费：** 现有 `Rect`。

**产出：** 应用启动前可读取的历史客户区，以及交接成功后可写入的物理矩形。

- [x] **步骤 1：写失败测试**

在 `tests/test_window_state.py` 写入：

```python
import json
from pathlib import Path

from glory_boot.adapters.window_state import WindowStateStore
from glory_boot.domain.models import Rect


def test_window_state_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "window-state.json"
    store = WindowStateStore(path)

    store.save(Rect(-1200, 80, 1400, 820))

    assert store.load() == Rect(-1200, 80, 1400, 820)


def test_corrupt_or_invalid_state_is_ignored(tmp_path: Path) -> None:
    path = tmp_path / "window-state.json"
    path.write_text('{"x": true, "y": 0, "width": 10, "height": 10}')

    assert WindowStateStore(path).load() is None
    assert list(tmp_path.glob("*.tmp")) == []
```

- [x] **步骤 2：运行测试并确认失败**

运行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_window_state.py -v
```

预期：模块不存在。

- [x] **步骤 3：实现原子 JSON 存储**

使用 `json` 和 `os.replace` 写入同目录临时文件。拒绝布尔值、非有限值、宽高不是正数、宽高小于 Codex 最小客户区 `450×280` 的记录。读取任何格式错误都返回 `None`，不向界面抛出异常。

- [x] **步骤 4：运行目标测试**

运行同一命令，预期全部通过，且临时文件无残留。

---

### 任务 3：读取客户区屏幕坐标并移动启动器窗口

**文件：**

- 修改：`src/glory_boot/adapters/win32.py`
- 修改：`tests/test_win32.py`

**接口：**

- `client_screen_rect(hwnd: int) -> Rect`
- `set_window_rect(hwnd: int, rect: Rect) -> None`

**消费：** `Rect`、现有 `Win32Error` 和 Win32 DLL 声明。

**产出：** 物理屏幕坐标下的 Codex 客户区，以及无边框启动器的物理矩形定位。

- [x] **步骤 1：写失败测试**

在 `tests/test_win32.py` 增加输入校验测试：

```python
from glory_boot.adapters.win32 import client_screen_rect, set_window_rect
from glory_boot.domain.models import Rect


def test_client_screen_rect_rejects_invalid_handle() -> None:
    with pytest.raises(Win32Error):
        client_screen_rect(0)


def test_set_window_rect_rejects_invalid_rectangle() -> None:
    with pytest.raises(ValueError):
        set_window_rect(123, Rect(0, 0, 0, 100))
```

- [x] **步骤 2：运行测试并确认失败**

运行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_win32.py -v
```

预期：无法导入新增函数。

- [x] **步骤 3：实现 Win32 几何调用**

为 `ClientToScreen` 和 `SetWindowPos` 设置准确的 `argtypes`、`restype`。`client_screen_rect` 调用 `GetClientRect` 后把客户区原点转换为屏幕坐标；`set_window_rect` 使用 `SWP_NOACTIVATE | SWP_SHOWWINDOW` 和 `HWND_TOPMOST`，不得改变启动器的无边框、置顶或透明度状态。

- [x] **步骤 4：运行目标测试**

运行同一命令，预期新增测试及既有窗口筛选测试全部通过。

---

### 任务 4：编排初始视口和一次窗口校准

**文件：**

- 新增：`src/glory_boot/services/window_placement.py`
- 新增：`tests/test_window_placement.py`

**接口：**

- `class WindowPlacementController`
- 构造参数：`window_hwnd: Callable[[], int]`、`state_store: WindowStateStore`、`monitors: Callable[[], tuple[Rect, ...]]`、`default_rect: Callable[[], Rect]`、`client_rect: Callable[[int], Rect]`、`place_window: Callable[[int, Rect], None]`
- `initial_viewport() -> Rect`
- `align(window: WindowInfo) -> bool`
- `viewport() -> Rect`
- `remember_success() -> bool`

**消费：** 任务 1 的纯函数、任务 2 的存储、任务 3 的 Win32 适配和现有 `WindowInfo`。

**产出：** 应用和 `SessionController` 共用的当前视口，以及不抛异常的校准结果。

- [x] **步骤 1：写失败测试**

在 `tests/test_window_placement.py` 写入以下核心断言：

```python
def test_initial_viewport_uses_valid_saved_rect() -> None:
    controller = _controller(saved=Rect(-1200, 40, 1400, 820))

    assert controller.initial_viewport() == Rect(-1200, 40, 1400, 820)


def test_initial_viewport_rejects_offscreen_saved_rect() -> None:
    controller = _controller(saved=Rect(5000, 5000, 800, 600))

    assert controller.initial_viewport() == Rect(100, 100, 1280, 720)


def test_align_moves_window_once_and_updates_viewport() -> None:
    controller = _controller()
    controller.initial_viewport()

    assert controller.align(_codex_window(hwnd=4321)) is True
    assert controller.align(_codex_window(hwnd=4321)) is True
    assert controller.placed == [(900, Rect(-1920, 40, 1400, 820))]
    assert controller.viewport() == Rect(-1920, 40, 1400, 820)


def test_align_failure_keeps_previous_viewport() -> None:
    controller = _controller(client_rect_error=OSError("denied"))
    initial = controller.initial_viewport()

    assert controller.align(_codex_window(hwnd=4321)) is False
    assert controller.viewport() == initial
```

测试辅助对象只使用内存状态，不创建真实窗口。

- [x] **步骤 2：运行测试并确认失败**

运行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_window_placement.py -v
```

预期：模块和服务不存在。

- [x] **步骤 3：实现布局控制器**

控制器持有当前视口和是否已经校准的状态。`align` 只对同一 `hwnd` 成功校准一次；失败时返回 `False` 并保留原视口。`remember_success` 只在已经成功校准时写入存储，写入失败返回 `False`。

- [x] **步骤 4：运行目标测试**

运行同一命令，预期全部通过。

---

### 任务 5：在 Codex 窗口稳定时通知一次校准

**文件：**

- 修改：`src/glory_boot/services/session.py`
- 修改：`tests/test_session.py`

**接口：**

- `SessionController.__init__(..., target_stable_callback: Callable[[WindowInfo], None] | None = None)`
- 回调在同一个 `hwnd` 连续第二次满足窗口筛选时调用，每个 `hwnd` 最多一次。

**消费：** 现有窗口探测状态和 `WindowInfo`。

**产出：** 应用能在不修改领域时间线的情况下执行一次几何校准。

- [x] **步骤 1：写失败测试**

在 `tests/test_session.py` 增加：

```python
def test_target_stable_callback_fires_once_per_window() -> None:
    aligned: list[int] = []
    controller, _media, _launcher, _window, _now = _session(
        window_finder=lambda _config: _existing_window(),
        target_stable_callback=lambda found: aligned.append(found.hwnd),
    )

    controller.tick()
    controller.tick()
    controller.tick()

    assert aligned == [4321]
```

- [x] **步骤 2：运行测试并确认失败**

运行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_session.py::test_target_stable_callback_fires_once_per_window -v
```

预期：构造参数不接受 `target_stable_callback`。

- [x] **步骤 3：实现稳定回调**

在 `_apply_codex_state` 确认同一窗口稳定后调用一次回调。回调异常不得改变 Codex 就绪判断、启动重试或交接策略；会话记录布尔失败结果，但不得记录窗口标题或内容。

- [x] **步骤 4：运行目标测试与会话回归**

运行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_session.py -v
```

预期：新增测试和既有会话测试全部通过。

---

### 任务 6：接入应用启动、初始尺寸和 DWM 视口

**文件：**

- 修改：`src/glory_boot/ui/application.py`
- 修改：`tests/test_ui_smoke.py`

**接口：**

- `LauncherApplication` 使用 `WindowPlacementController`。
- `SessionController(viewport_provider=placement.viewport)`。
- 在 `SessionController.handoff_completed` 后调用 `placement.remember_success()`。
- 启动器不再调用 `showFullScreen()`。

**消费：** 任务 3、4、5 的接口。

**产出：** 使用历史或默认矩形显示首帧，稳定后校准一次，并以校准矩形供 DWM 使用。

- [x] **步骤 1：写失败测试**

在 `tests/test_ui_smoke.py` 增加窗口生命周期测试：

```python
def test_launcher_window_can_present_at_non_fullscreen_rect(
    qapp,
    tmp_path,
) -> None:
    window = BootWindow()
    window.show_poster_first(str(_poster_path(tmp_path)))

    window.show()
    qapp.processEvents()

    assert window.isVisible()
    assert window.windowState() & Qt.WindowState.WindowFullScreen == 0
    window.close()
```

- [x] **步骤 2：运行测试并确认失败**

运行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_ui_smoke.py::test_launcher_window_can_present_at_non_fullscreen_rect -v
```

预期：如果测试辅助函数或当前行为尚未满足，测试失败。

- [x] **步骤 3：接入控制器并替换全屏路径**

使用 `%LOCALAPPDATA%\GloryBoot\window-state.json` 作为持久化路径；使用当前光标所在显示器工作区生成默认矩形。先创建原生窗口句柄并设置物理矩形，再显示窗口和记录 `window_visible`。把同一视口传给会话，并在成功交接后记录最终 Codex 客户区。

校准回调和 DWM 更新继续运行在 Qt 主线程；不得在后台线程直接设置窗口几何。

- [x] **步骤 4：运行界面和会话测试**

运行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_ui_smoke.py tests\test_session.py tests\test_placement.py tests\test_window_state.py tests\test_window_placement.py -v
```

预期：全部通过。

---

### 任务 7：全量验证、基准和文档同步

**文件：**

- 修改：`README.md`
- 修改：`docs/superpowers/plans/2026-11-09-phase2a-window-adaptation.md`

**接口：**

- 记录实际运行命令、测试结果、打包基准和仍需人工验收的多显示器／DPI 场景。

**消费：** 前六个任务的实现和测试。

**产出：** 可审阅的第二阶段 A 交付记录和明确风险。

- [x] **步骤 1：运行全量自动测试**

运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\test.ps1
```

预期：全部测试通过，无新增警告或残留进程。

- [x] **步骤 2：运行打包启动基准**

按项目现有打包与基准命令重建 onedir 包，记录首个可见窗口、媒体首帧、Codex 启动请求和是否发生尾帧停留。预期首帧目标仍为 `<= 800 ms`；若超限，记录瓶颈，不得直接声称完成。

- [ ] **步骤 3：执行人工几何验收**

在秋月大人确认后，分别检查：

- 1080p 普通窗口；
- 负坐标副屏；
- 125% 与 150% DPI；
- Codex 最大化窗口；
- 无历史记录的首次运行；
- 校准期间 `Esc` 跳过。

预期：启动器与 Codex 客户区一致，DWM 最终覆盖同一矩形，失败时仍进入可操作 Codex。

- [x] **步骤 4：同步 README 和执行记录**

只写已经验证的事实，更新第二阶段 A 当前状态、配置位置、测试命令、基准值和剩余人工风险。

- [x] **步骤 5：检查工作区**

运行：

```powershell
git status --short
```

确认没有 `.venv/`、`.reference/`、日志、构建产物、壁纸私有素材或真实窗口截图进入待提交范围。停止并汇报；提交和最终发布需要新的明确同意。

### 任务 8：改为 Codex 窗口稳定后再播放

**文件：**

- 修改：`src/glory_boot/ui/application.py`
- 修改：`src/glory_boot/ui/boot_window.py`
- 修改：`src/glory_boot/services/session.py`
- 修改：`src/glory_boot/services/window_placement.py`
- 修改：`src/glory_boot/adapters/win32.py`
- 修改：`src/glory_boot/adapters/dwm.py`
- 修改：`src/glory_boot/adapters/window_state.py`
- 修改：`tests/test_ui_smoke.py`
- 修改：`tests/test_session.py`
- 修改：`tests/test_win32.py`
- 修改：`tests/test_window_placement.py`

**接口：**

- 冷启动不再创建 12 秒强制显示定时器。
- `DwmGetWindowAttribute(DWMWA_EXTENDED_FRAME_BOUNDS)` 提供整窗可见外框，失败时回退 `GetWindowRect`。
- 用户跳过、媒体失败或窗口等待超时发生在首次显示前时，先显示海报但不启动媒体，再执行现有交接策略。

- [x] **步骤 1：写失败测试**

覆盖以下行为：启动路径不再设置定时回退；首次显示前可进入无媒体的错误交接；隐藏等待超过 `MaxWaitSeconds` 会超时；DWM 返回整窗外框；DWM 失败时回退 `GetWindowRect`；视频与海报覆盖视口；DWM 缩略图使用整窗内容。

- [x] **步骤 2：运行目标测试并确认失败**

新增测试分别失败于 `_reveal_for_handoff` 不存在、隐藏等待不超时、仍启动 12 秒定时器，以及客户区/保留比例行为不符合预期。

- [x] **步骤 3：实现窗口稳定后播放**

移除 `REVEAL_FALLBACK_MS` 和 `_reveal_timer`。Codex 稳定回调完成整窗对齐、显示和媒体启动；会话在媒体尚未启动时按 `MaxWaitSeconds` 超时；首次显示前的交接只显示海报。

- [x] **步骤 4：覆盖整窗外框**

启动器使用 DWM 可见外框替代客户区矩形，视频和海报使用覆盖式缩放。DWM 缩略图切换为整窗内容，避免交接尾声跳回客户区尺寸。

- [x] **步骤 5：运行全量与发布验证**

全量测试 `283` 通过、`0` 失败；重建 onedir 后基准第一个可见窗口 `301.1 ms`、媒体首帧 `490.9 ms`、Codex 启动请求 `303.7 ms`；资源与压缩包烟雾检查通过。基准模式不读取真实 Codex，会直接显示并启动媒体，因此不代表正常冷启动的等待时点。

## 执行记录

| 日期 | 提交 | 改动 | 自动验证 | 基准与风险 |
| --- | --- | --- | --- | --- |
| 2026-11-09 | `25ec2dc` | 建立第二阶段基线；保留秋月大人允许提交的本地媒体 | 153 通过 | 基线仓库此前没有提交 |
| 2026-11-09 | `4d2fe09` | 增加安全默认矩形、显示器可见性和仓库私有目录忽略修正 | 161 通过 | 浮点覆盖比例采用近似断言 |
| 2026-11-09 | `a808aeb` | 增加窗口几何原子持久化和损坏回退 | 164 通过 | 只保存坐标尺寸，不保存窗口内容 |
| 2026-11-09 | `72d9fad` | 增加客户区屏幕坐标、物理窗口定位和显示器工作区 | 167 通过 | 原生调用通过假 Win32 边界测试 |
| 2026-11-09 | `d736439` | 编排历史视口、一次校准和成功记录 | 172 通过 | 校准失败保持原视口 |
| 2026-11-09 | `14b905a` | 在 Codex 窗口稳定时触发一次校准 | 173 通过 | 回调异常不改变就绪和交接策略 |
| 2026-11-09 | `111d5a0` | 应用接入初始几何、DWM 共用视口和成功持久化 | 176 通过 | 原生显示器几何增加 Win32 工作区枚举 |
| 2026-11-09 | `0cbf4b3` | 已有 Codex 显示动画前直接聚焦退出；短暂窗口漏检不再重置稳定窗口或触发重复启动 | 261 通过 | 非沙箱实机验证：复用 `91 ms`，整次退出约 `754 ms`，未显示动画 |
| 2026-11-09 | 本任务文档提交 | 同步 README、计划和当前验证事实 | 261 通过 | 真实冷启动下的多显示器、DPI 和最大化验收仍待执行 |
| 2026-11-12 | 本任务 | 改为 Codex 主窗口稳定后显示并播放；按 DWM 整窗可见外框覆盖，视频和海报裁切填满，移除 12 秒强制回退 | `283` 通过；打包基准窗口 `301.1 ms`、媒体首帧 `490.9 ms`、启动请求 `303.7 ms`；压缩包 SHA-256 `740445c160b48c810244a954b5fce10e8565bcbc1eafa86e253541695667cb90`；当前最大化 Codex 只读实测整窗矩形为 `1920×1032` | 需要在完全退出 Codex 后人工确认普通窗口、最大化和多显示器 |
| 2026-11-12 | 首帧闪烁修复 | 首个合格主窗口被发现时重新读取当前句柄，以透明状态显示并锁定矩形后恢复不透明；禁止可见后的二次定位 | `296` 通过；打包基准窗口 `298.7 ms` | 真实冷启动仍需确认首帧无默认尺寸闪帧 |
| 2026-11-16 | 末帧黑场修复 | 时间线返回 `HOLD` 时真正暂停在 `HoldAt`，并显示等待状态；渲染器就绪标记在窗口枚举短暂歧义时仍可放行；兜底从首个有效窗口出现时计时，避免句柄替换后额外等待 8 秒 | `300` 通过；真实日志确认旧路径在末帧黑场额外停留约 `7.35 s` | 仍需完整冷启动确认新包不再出现黑场停留 |
| 2026-11-16 | 回归包 | 重建 onedir 与压缩包；烟雾检查确认媒体、Qt 多媒体、WebSocket 资源和日志隔离正常 | 基准窗口 `263.6 ms`、媒体首帧 `454.8 ms`、启动请求 `266.9 ms`；SHA-256 `b75d506fd4b218ad6dbb80151125fd5917798210abf551ca2dc1dbfa8d6acaae` | 基准不启动真实 Codex |
| 2026-11-16 | 全屏误显定位 | 真实日志在激活受理后先找到同包旧窗口，几何读取失败后旧代码仍用历史 `1920×1032` 矩形显示；现等启动身份确定后才探测，按激活进程号过滤窗口，校准失败保持隐藏并由稳定回调重试，几何回调不得再次查询其他进程 | `305` 通过；新增启动身份等待、旧进程拒绝、失败不显示和回调不重查测试 | 需下次真实冷启动确认动画与当前 Codex 外框一致 |
| 2026-11-16 | 动画关闭硬边界 | 壁纸准备状态仍可间接延长动画等待；现 Codex 内容就绪后壁纸最多再阻塞 5 秒，超过后记录 `codex_ready_skin_timeout` 并继续 CRT 收束与交接 | `307` 通过；新增就绪门控不得无限阻塞测试 | 保证动画关闭，不保证超时后壁纸仍成功 |
| 2026-11-16 | 动画尺寸大于窗口 | 录屏逐帧测得动画约 `1392×824`、最终 Codex 窗口约 `1279×822`；旧实现首次发现窗口即锁定几何，命中了 Codex 缩放过程中的中间尺寸 | 首次发现只等待，不显示；同一窗口连续稳定后重新读取并锁定整窗外框；`312` 通过 | 需重新录屏确认动画与最终窗口等宽 |
| 2026-11-16 | 录屏帧率证据 | 21.64 秒录屏仅 `20.05 fps`，而动画源为 `60 fps`；录屏天然丢弃约三分之二动画帧 | 该录屏不能作为实时卡顿的独立证据；几何修复后需用不低于 60 fps 的录制复核 | 不据低帧率录屏做性能结论 |
| 2026-11-16 | 稳定窗口修复包 | 构建稳定窗口校准后的 onedir 与压缩包；按秋月大人要求不运行可见基准 | `312` 通过；烟雾检查通过；SHA-256 `66a49a32d3185b7fa1791d49ab2e191aa2813c384f57f9976f564088c81d55ef` | 待重新录屏确认动画与 Codex 窗口同尺寸 |
| 2026-11-16 | 完整画面与白屏修复 | 视频和海报从 `KeepAspectRatioByExpanding` 改为完整铺满目标矩形，不再裁切左右内容；Codex 壳窗口首次出现后使用 Win32 分层透明隐藏，启动器首帧显示后才恢复 | 新增窗口透明隐藏/恢复和完整画面测试；`315` 通过 | 需新包实机确认无白屏且画面不裁切 |
| 2026-11-16 | 完整画面修复包 | 构建包含完整视频铺满、窗口透明遮盖和实色正文/卡片表面的 onedir 与压缩包；不运行可见基准 | `316` 通过；烟雾检查通过；SHA-256 `65f5f2ae24c4ca87879c30be0a82c023a06505dbe8a01e8af654b1f95493e68e` | 待秋月大人实机确认 |
| 2026-11-16 | 最终回归包 | 重建包含启动身份等待、窗口 PID 过滤、几何失败重试、壁纸门控硬边界、DWM 直接关闭和参考项目浅色透明皮肤修复的 onedir 与压缩包 | 基准窗口 `262.4 ms`、媒体首帧 `472.8 ms`、启动请求 `270.3 ms`；SHA-256 `e23d574ff300538e46431341ef39f38e9872693c7706347beda5e09d9710f9aa` | 真实冷启动仍需人工确认 |
| 2026-11-16 | 连续播放修复包 | 窗口框架稳定并开始媒体播放后即视为交接就绪；移除 `HoldAt` 暂停、内容日志门控和壁纸等待门控；重建 onedir 与压缩包 | `300` 通过；烟雾检查通过；SHA-256 `4607e048972ff5092a57506809f9f78f188b2aab68507e3ed6ee518549722ff2` | 未运行可见基准；真实冷启动仍需人工确认 |
| 2026-11-16 | 双关闭视觉定位 | Qt 实机实验确认暂停在 `6400 ms` 后恢复位置为 `6449 ms`，媒体没有重播；DWM 已把 Codex 显示到启动器窗口后，旧流程又淡出整个承载窗口，形成第二次视觉收束 | DWM 完整交接后直接关闭承载窗口；只有 DWM 失败或提前跳过才使用窗口淡出；`309` 通过 | 需冷启动确认只出现一次 CRT 收束 |

第二阶段 A 打包基准使用无外部启动副作用的后端：首个可见窗口 `322.4 ms`、媒体首帧 `517.6 ms`、Codex 启动请求 `326.3 ms`，均未超过首帧 `800 ms` 目标。基准没有启动真实 Codex，因此不能证明实际窗口校准成功。
