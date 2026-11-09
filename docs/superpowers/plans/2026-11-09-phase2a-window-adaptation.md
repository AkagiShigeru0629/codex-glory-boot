# 第二阶段 A 启动器窗口适配实施计划

> **执行代理须知：** 必须使用 `superpowers:subagent-driven-development` 或 `superpowers:executing-plans`，按任务顺序执行本计划，并用复选框记录进度。本计划不包含提交、推送、真实 Codex 冷启动或替换官方入口；这些操作需要另行取得秋月大人的明确同意。

**目标：** 让独立启动器按照 Codex 主窗口客户区显示和完成 DWM 交接，而不是始终全屏。

**架构：** 启动器仍先显示海报并并行启动 Codex。应用在启动前读取上次有效的 Codex 客户区，首次运行时使用安全默认矩形；Codex 主窗口稳定后，通过 Win32 读取客户区屏幕坐标，将启动器校准一次，并让动画视口与 DWM 目标共用该矩形。校准失败时继续使用当前有效矩形，不阻断第一阶段流程。

**技术栈：** CPython 3.14、PySide6 6.12、QtMultimedia、Python `ctypes`、pytest、PyInstaller onedir。

**设计说明：** `docs/superpowers/specs/2026-11-09-phase2-window-and-wallpaper-design.md`

## 全局约束

- 第一阶段首帧目标、并行启动、完整播放、等待、超时和 DWM 回退保持不变。
- 首帧显示不得等待 Codex 主窗口或窗口几何探测。
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

- 首次运行没有历史几何时，必须立即显示安全默认尺寸，不能为了探测 Codex 而出现空白等待。
- 目标窗口位于负坐标显示器或不同 DPI 显示器时，启动器、媒体视口和 DWM 目标必须保持一致。
- 校准期间媒体不能重新打开、重新起播或露出白屏、黑屏。
- Codex 窗口在校准前后消失、最小化或移动时，启动器仍必须能够超时回退到可操作的 Codex 或明确错误。
- 移除 `showFullScreen()` 后，首帧窗口、媒体首帧和 Codex 启动请求的并行时序不得退化。

## 文件结构

- 新增 `src/glory_boot/domain/placement.py`：默认矩形和可见性判断等纯函数。
- 新增 `src/glory_boot/adapters/window_state.py`：上次有效客户区 JSON 的原子读写。
- 修改 `src/glory_boot/adapters/win32.py`：客户区屏幕坐标和物理矩形定位。
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

第二阶段 A 打包基准使用无外部启动副作用的后端：首个可见窗口 `322.4 ms`、媒体首帧 `517.6 ms`、Codex 启动请求 `326.3 ms`，均未超过首帧 `800 ms` 目标。基准没有启动真实 Codex，因此不能证明实际窗口校准成功。
