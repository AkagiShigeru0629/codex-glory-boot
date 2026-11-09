# 第二阶段 B Codex 内部壁纸实施计划

> **执行代理须知：** 必须使用 `superpowers:subagent-driven-development` 或 `superpowers:executing-plans`，按任务顺序执行本计划，并用复选框记录进度。本计划会在皮肤模式中启动真实 Codex；所有真实启动、关闭和冷启动验收都必须先取得秋月大人的明确同意，不得主动结束或覆盖正在运行的 Codex。

**目标：** 为 Codex 提供默认关闭、可检测、可关闭、可恢复的应用内兴欣壁纸，壁纸位于原生内容下方且不改变正常操作。

**架构：** 使用 Python 的 `ApplicationActivationManager` 激活接口在本次启动时传入仅绑定回环地址的动态调试端口；Python 通过 Qt WebSocket 执行固定样式注入，样式只修改页面根容器、背景主题变量和必要的可读性表面。注入前校验版本、能力、端口与进程归属，注入后验证视觉标记；失败或关闭时恢复原有根属性和 CSS 变量，不修改 Codex 安装目录。

**技术栈：** CPython 3.14、PySide6 6.12（含 `QtNetwork`、`QtWebSockets`）、Python `ctypes`、标准库 `json`／`socket`／`urllib`、pytest、PyInstaller onedir。

**设计说明：** `docs/superpowers/specs/2026-11-09-phase2-window-and-wallpaper-design.md`

## 全局约束

- 第二阶段 B 首版只做壁纸和必要的背景透明度／可读性调整。
- 首版不重新设计按钮、字体、图标、间距、布局、动画或交互控件。
- 壁纸模块默认关闭；关闭时不添加调试参数、不开放端口、不执行注入。
- 调试地址只能使用 `127.0.0.1`，不得监听或连接局域网地址。
- 不新增 Python 包依赖；已确认当前 `.venv` 可以导入 `PySide6.QtWebSockets`。
- 不引入 Node.js 或 C# 产品代码。
- 不修改 Codex 安装目录、用户配置、聊天、账号、Cookie、Token 或本地存储。
- 页面脚本只执行项目内置的固定检测、安装和恢复表达式，不读取页面文字。
- 未登记兼容性的 Codex 版本默认跳过壁纸，不影响原生启动。
- 不记录壁纸路径、页面目标、窗口标题、页面内容或用户数据；日志只记录阶段、耗时、布尔结果和错误码。
- 每个任务先写失败测试，再写最小实现。
- 最终运行：
  `powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\test.ps1`
- 不自动提交；提交、真实 Codex 启动、冷启动验收和发布需要另行取得明确同意。

## 审查重点

- Codex 已经在运行时没有调试端口，皮肤必须直接跳过并聚焦原窗口，不能尝试重启或替换 Codex。
- 端口被其他本机进程占用或页面目标不属于本次 Codex 进程时，必须拒绝注入。
- Codex 更新导致页面节点或主题令牌变化时，必须停止注入并保留官方外观，不能只显示“半透明半正常”的破损界面。
- 壁纸注入后不得遮挡点击、输入、滚动、粘贴、拖放或对话框，也不能降低代码和菜单的可读性。
- 页面重新加载或 Codex 退出后不得遗留样式、临时资源、监听器、后台进程或活动注入连接。

## 文件结构

- 修改 `src/glory_boot/domain/models.py`：增加不可变 `SkinConfig` 和 `AppConfig.skin`。
- 新增 `src/glory_boot/domain/skin.py`：兼容配置、包版本提取和状态枚举等纯逻辑。
- 修改 `src/glory_boot/config.py`：解析可选 `skin` 配置并保留旧配置兼容。
- 新增 `src/glory_boot/adapters/app_activation.py`：通过 `ApplicationActivationManager` 启动并返回进程号。
- 新增 `src/glory_boot/adapters/devtools.py`：调试目标发现和本地地址校验。
- 新增 `src/glory_boot/adapters/network_ports.py`：分配仅绑定回环地址的临时端口。
- 修改 `src/glory_boot/adapters/win32.py`：查询监听端口所属进程。
- 新增 `src/glory_boot/services/cdp.py`：基于 Qt WebSocket 的异步 CDP 请求客户端。
- 新增 `src/glory_boot/services/skin_payload.py`：读取壁纸、验证格式并构建固定注入表达式。
- 新增 `src/glory_boot/services/skin.py`：编排等待、检测、注入、跳过、恢复和日志。
- 新增 `src/glory_boot/resources/skin.css`：只覆盖背景和必要表面。
- 新增 `src/glory_boot/resources/skin.js`：安装、检测、恢复和固定快捷键的页面脚本模板。
- 新增 `src/glory_boot/resources/skin_profiles.json`：已验证 Codex 版本和所需能力。
- 修改 `src/glory_boot/services/codex_launcher.py`：允许后端携带激活参数和返回进程号。
- 修改 `src/glory_boot/ui/application.py`、`src/glory_boot/main.py`：接入皮肤模式与 `--disable-skin`。
- 修改 `packaging/glory_boot.spec`、`pyproject.toml`：打包新增资源文件和 Qt WebSocket 隐式模块。
- 新增 `tests/test_skin_config.py`、`tests/test_skin_domain.py`、`tests/test_app_activation.py`、`tests/test_devtools.py`、`tests/test_network_ports.py`、`tests/test_cdp.py`、`tests/test_skin_payload.py`、`tests/test_skin.py`。
- 修改 `tests/test_config.py`、`tests/test_launcher.py`、`tests/test_repository_contract.py`。
- 修改 `README.md` 和 `THIRD_PARTY_NOTICES.md`：实现和人工验收完成后同步事实与来源说明。

---

### 任务 1：增加默认关闭的皮肤配置

**文件：**

- 修改：`src/glory_boot/domain/models.py`
- 修改：`src/glory_boot/config.py`
- 修改：`config/launcher.example.json`
- 新增：`tests/test_skin_config.py`
- 修改：`tests/test_config.py`

**接口：**

- `@dataclass(frozen=True, slots=True) class SkinConfig`
- `SkinConfig(enabled: bool = False, wallpaper_path: str | None = None)`
- `AppConfig.skin: SkinConfig = field(default_factory=SkinConfig)`
- `load_config(root: Path) -> AppConfig` 在缺少 `skin` 时使用默认值。

**消费：** 现有 `AppConfig` 和 JSON 配置加载流程。

**产出：** 旧配置无需修改即可运行，皮肤默认关闭。

- [x] **步骤 1：写失败测试**

在 `tests/test_skin_config.py` 写入：

```python
from pathlib import Path

import pytest

from glory_boot.config import load_config


def test_missing_skin_section_defaults_to_disabled(config_root: Path) -> None:
    config = load_config(config_root)

    assert config.skin.enabled is False
    assert config.skin.wallpaper_path is None


def test_enabled_skin_keeps_missing_wallpaper_for_runtime_fallback(
    config_root: Path,
) -> None:
    _write_skin(config_root, enabled=True, wallpaper_path="missing.png")

    config = load_config(config_root)

    assert config.skin.enabled is True
    assert config.skin.wallpaper_path == str(
        (config_root / "missing.png").resolve()
    )


def test_disabled_skin_does_not_require_wallpaper(config_root: Path) -> None:
    _write_skin(config_root, enabled=False, wallpaper_path=None)

    assert load_config(config_root).skin.enabled is False
```

- [x] **步骤 2：运行测试并确认失败**

运行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_skin_config.py -v
```

预期：`SkinConfig` 或 `skin` 字段不存在。

- [x] **步骤 3：实现可选配置和路径解析**

严格校验 `enabled` 是布尔值和路径是字符串。启用时把路径解析为绝对路径，但文件缺失或格式错误只留给皮肤控制器在运行时跳过，不能阻断 Codex 启动。禁用时忽略空路径。不打印壁纸内容。

- [x] **步骤 4：运行配置回归**

运行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_skin_config.py tests\test_config.py -v
```

预期：全部通过，旧配置夹具无需新增必填字段。

---

### 任务 2：增加兼容配置、版本提取和临时端口

**文件：**

- 新增：`src/glory_boot/domain/skin.py`
- 新增：`src/glory_boot/adapters/network_ports.py`
- 新增：`tests/test_skin_domain.py`
- 新增：`tests/test_network_ports.py`

**接口：**

- `package_version_from_path(process_path: str) -> str | None`
- `@dataclass(frozen=True, slots=True) class SkinProfile`
- `select_skin_profile(profiles: tuple[SkinProfile, ...], version: str | None) -> SkinProfile | None`
- `allocate_loopback_port() -> int`

**消费：** 现有 `WindowInfo.process_path`。

**产出：** 用于版本守卫的包版本、已登记兼容配置和本次皮肤模式的本地端口。

- [x] **步骤 1：写失败测试**

在 `tests/test_skin_domain.py` 写入：

```python
def test_package_version_is_read_from_store_path() -> None:
    path = r"C:\Program Files\WindowsApps\OpenAI.Codex_26.924.22138.0_x64__x\ChatGPT.exe"

    assert package_version_from_path(path) == "26.924.22138.0"


def test_unknown_version_is_not_selected() -> None:
    profile = SkinProfile("26.924.22138.0", ("#root",), ("--color-surface",))

    assert select_skin_profile((profile,), "27.0.0.0") is None
```

在 `tests/test_network_ports.py` 写入：

```python
def test_allocated_port_is_available_on_loopback() -> None:
    port = allocate_loopback_port()

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", port))
```

- [x] **步骤 2：运行测试并确认失败**

运行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_skin_domain.py tests\test_network_ports.py -v
```

预期：新增模块不存在。

- [x] **步骤 3：实现纯逻辑和端口分配**

版本提取只匹配 `OpenAI.Codex_<版本>_<架构>__...`，找不到时返回 `None`。兼容选择要求版本完全匹配。端口通过标准库 socket 绑定 `127.0.0.1`、端口 `0` 后再关闭取得；调用方必须立即把端口传给 Codex，发现冲突时整体跳过皮肤。

- [x] **步骤 4：运行目标测试**

运行同一命令，预期全部通过。

---

### 任务 3：使用应用激活接口携带调试参数

**文件：**

- 新增：`src/glory_boot/adapters/app_activation.py`
- 修改：`src/glory_boot/services/codex_launcher.py`
- 新增：`tests/test_app_activation.py`
- 修改：`tests/test_launcher.py`

**接口：**

- `ProcessBackend.launch(app_id: str, arguments: str = "") -> int | None`
- `LaunchResult.launched_pid: int | None = None`
- `ApplicationActivationBackend.launch(app_id: str, arguments: str = "") -> int | None`
- `CodexLauncher.__init__(..., launch_arguments: str = "")`

**消费：** 现有 `CodexLauncher` 调用和 `LaunchResult`。

**产出：** 皮肤模式可以携带
`--remote-debugging-address=127.0.0.1 --remote-debugging-port=<port>`，
并取得本次激活进程号；普通模式继续使用现有 `explorer.exe` 后端。

- [x] **步骤 1：写失败测试**

在 `tests/test_launcher.py` 增加：

```python
def test_launcher_passes_arguments_and_returns_process_id() -> None:
    backend = RecordingBackend(process_id=9876)
    launcher = CodexLauncher(
        _config(),
        process_backend=backend,
        launch_arguments="--remote-debugging-port=50123",
        window_finder=lambda _config: None,
    )

    result = launcher.request_once()

    assert backend.calls == [
        ("OpenAI.Codex_2p2nqsd0c76g0!App", "--remote-debugging-port=50123")
    ]
    assert result.launched_pid == 9876
```

在 `tests/test_app_activation.py` 使用注入的假激活器断言空应用标识和超长参数被拒绝；不执行真实 COM 激活。

- [x] **步骤 2：运行测试并确认失败**

运行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_launcher.py tests\test_app_activation.py -v
```

预期：`launch_arguments`、`launched_pid` 或新后端不存在。

- [x] **步骤 3：实现应用激活后端**

在 `adapters/win32.py` 暴露 `process_path_for_pid(pid: int) -> str | None`，供皮肤控制器从本次激活进程取得 Codex 包路径和版本。

通过 `ctypes` 调用 `CoInitializeEx`、`CoCreateInstance` 和
`IApplicationActivationManager.ActivateApplication`，返回激活进程号，并在正常与异常路径调用 `CoUninitialize`。原生调用放到 `adapters/`，启动线程与资源释放规则沿用现有后端。

普通 `QProcessBackend` 在收到非空参数时抛出 `ValueError`；皮肤模式必须显式选择应用激活后端。

- [x] **步骤 4：运行目标测试**

运行同一命令，预期全部通过。

---

### 任务 4：发现并校验本地调试页面

**文件：**

- 新增：`src/glory_boot/adapters/devtools.py`
- 修改：`src/glory_boot/adapters/win32.py`
- 新增：`tests/test_devtools.py`

**接口：**

- `@dataclass(frozen=True, slots=True) class DevToolsPage`
- 字段：`target_id: str`、`url: str`、`websocket_url: str`
- `parse_targets(payload: object, port: int) -> tuple[DevToolsPage, ...]`
- `find_pages(port: int, timeout_ms: int = 1000) -> tuple[DevToolsPage, ...]`
- `validate_websocket_url(value: str, port: int) -> str`
- `is_codex_page(page: DevToolsPage) -> bool`
- `listener_owner_pid(port: int) -> int | None`

**消费：** 任务 2 分配的端口和任务 3 返回的进程号。

**产出：** 只属于本次 Codex、只使用回环地址的目标页面。

- [x] **步骤 1：写失败测试**

在 `tests/test_devtools.py` 写入：

```python
import pytest


def test_rejects_non_loopback_socket() -> None:
    with pytest.raises(ValueError):
        validate_websocket_url(
            "ws://192.168.1.10:50123/devtools/page/1",
            50123,
        )


def test_rejects_wrong_port_and_credentials() -> None:
    with pytest.raises(ValueError):
        validate_websocket_url("ws://127.0.0.1:50000/devtools/page/1", 50123)
    with pytest.raises(ValueError):
        validate_websocket_url("ws://user:pass@127.0.0.1:50123/devtools/page/1", 50123)


def test_accepts_main_codex_page() -> None:
    page = DevToolsPage(
        "1",
        "app://-/index.html?initialRoute=%2F",
        "ws://127.0.0.1:50123/devtools/page/1",
    )

    assert is_codex_page(page)
```

- [x] **步骤 2：运行测试并确认失败**

运行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_devtools.py -v
```

预期：模块不存在。

- [x] **步骤 3：实现目标发现和端口归属**

使用 `urlsplit` 严格解析并拒绝用户名、密码、非 `ws` 协议、非 `127.0.0.1` 和端口不一致。页面选择只接受 `app://-/index.html` 主页面，排除头像、迷你窗、弹窗和通知路由。`find_pages` 使用标准库向本地 `/json/list` 发出限时请求，只能由后台工作线程调用。`listener_owner_pid` 使用 `GetExtendedTcpTable` 查询 TCP 监听表，不对端口做文本日志。

- [x] **步骤 4：运行目标测试**

运行同一命令，预期全部通过。

---

### 任务 5：构建固定壁纸注入与恢复载荷

**文件：**

- 新增：`src/glory_boot/resources/skin.css`
- 新增：`src/glory_boot/resources/skin.js`
- 新增：`src/glory_boot/services/skin_payload.py`
- 新增：`tests/test_skin_payload.py`

**接口：**

- `load_wallpaper(path: str) -> bytes`
- `@dataclass(frozen=True, slots=True) class SkinPayload`
- 字段：`install_expression: str`、`detect_expression: str`、`restore_expression: str`
- `build_skin_payload(root: Path, wallpaper_path: str) -> SkinPayload`

**消费：** 任务 1 校验过的本地壁纸路径和任务 2 选择的兼容配置。

**产出：** 只做背景与必要可读性修改、可以完整撤销的固定脚本。

- [x] **步骤 1：写失败测试**

在 `tests/test_skin_payload.py` 写入：

```python
import pytest


def test_only_supported_wallpaper_formats_are_accepted(tmp_path: Path) -> None:
    path = tmp_path / "wallpaper.gif"
    path.write_bytes(b"GIF89a")

    with pytest.raises(ValueError):
        load_wallpaper(str(path))


def test_payload_has_one_marker_and_fixed_restore(tmp_path: Path) -> None:
    payload = build_skin_payload(ROOT, str(_png_wallpaper(tmp_path)))

    assert payload.install_expression.count("glory-boot-skin-style") == 1
    assert "__gloryBootSkin" in payload.install_expression
    assert "dispose" in payload.restore_expression
    for forbidden in ("innerText", "localStorage", "document.cookie"):
        assert forbidden not in payload.install_expression
```

- [x] **步骤 2：运行测试并确认失败**

运行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_skin_payload.py -v
```

预期：模块不存在。

- [x] **步骤 3：实现静态载荷**

只接受签名有效的 PNG、JPEG、WebP，限制文件大小为 `20 MiB`。在页面内使用 Blob URL，安装固定样式节点并记录原始根属性、CSS 变量值和优先级；恢复时逐项还原并释放 URL。

CSS 只处理页面和内容背景、必要的文字对比度与菜单／输入框可读表面。不得改变按钮形状、字体、图标、布局或控件尺寸。JS 仅增加精确匹配
`Ctrl+Alt+Shift+R` 的恢复快捷键。

- [x] **步骤 4：运行目标测试**

运行同一命令，预期全部通过。

---

### 任务 6：实现异步 Chrome 调试协议客户端

**文件：**

- 新增：`src/glory_boot/services/cdp.py`
- 新增：`tests/test_cdp.py`

**接口：**

- `class CdpClient(QObject)`
- 信号：`connected: Signal()`、`evaluation_finished: Signal(int, object)`、`failed: Signal(str)`
- `connect_to(websocket_url: str, timeout_ms: int = 5000) -> None`
- `evaluate(expression: str, request_id: int, timeout_ms: int = 5000) -> None`
- `close() -> None`

**消费：** 任务 4 验证过的 WebSocket 地址。

**产出：** 非阻塞执行 `Runtime.evaluate`，超时和断线均产生结构化失败。

- [x] **步骤 1：写失败测试**

使用本机 `QWebSocketServer` 或注入的假套接字客户端测试：

```python
def test_connect_timeout_emits_failure(qapp) -> None:
    client = CdpClient(socket_factory=lambda _url: NeverOpeningSocket())
    failures: list[str] = []
    client.failed.connect(failures.append)

    client.connect_to("ws://127.0.0.1:50123/devtools/page/1", 20)
    _wait(qapp, 50)

    assert failures == ["connect_timeout"]


def test_response_is_matched_by_request_id(qapp) -> None:
    client, socket = _connected_fake_client(qapp)
    results: list[tuple[int, object]] = []
    client.evaluation_finished.connect(lambda i, value: results.append((i, value)))

    client.evaluate("true", request_id=17, timeout_ms=20)
    socket.receive_json({"id": 17, "result": {"result": {"value": True}}})

    assert results == [(17, {"result": {"value": True}})]
```

- [x] **步骤 2：运行测试并确认失败**

运行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_cdp.py -v
```

预期：模块或客户端不存在。

- [x] **步骤 3：实现最小 CDP 客户端**

每次调用分配稳定请求号，使用单层已发送消息映射处理响应，不把页面返回值写入日志。连接、评估和关闭均设置超时与幂等清理。不得同步等待套接字。

- [x] **步骤 4：运行目标测试**

运行同一命令，预期全部通过。

---

### 任务 7：编排等待、检测、注入和恢复

**文件：**

- 新增：`src/glory_boot/services/skin.py`
- 新增：`tests/test_skin.py`

**接口：**

- `class SkinState(StrEnum)`
- 值至少包括：`disabled`、`waiting`、`skipped`、`installed`、`failed`、`restored`
- `class SkinController(QObject)`
- `SkinController.start(launched_pid: int | None) -> None`
- `SkinController.restore() -> None`
- `SkinController.close() -> None`
- 状态改变通过 `state_changed: Signal(str)` 报告。

**消费：** 任务 2、3、4、5、6 的接口。

**产出：** 默认关闭、失败安全、可恢复的壁纸生命周期。

- [x] **步骤 1：写失败测试**

在 `tests/test_skin.py` 写入：

```python
def test_disabled_controller_never_connects() -> None:
    controller, cdp = _skin_controller(enabled=False)

    controller.start(launched_pid=None)

    assert cdp.connect_calls == []
    assert controller.state is SkinState.DISABLED


def test_existing_codex_without_launch_pid_is_skipped() -> None:
    controller, cdp = _skin_controller(launched_pid=None)

    controller.start(launched_pid=None)

    assert controller.state is SkinState.SKIPPED
    assert cdp.connect_calls == []


def test_listener_pid_mismatch_is_rejected() -> None:
    controller, cdp = _skin_controller(launched_pid=10, listener_pid=11)

    controller.start(launched_pid=10)

    assert controller.state is SkinState.SKIPPED
    assert cdp.connect_calls == []


def test_incompatible_version_is_skipped() -> None:
    controller, cdp = _skin_controller(version="99.0.0.0")

    controller.start(launched_pid=10)

    assert controller.state is SkinState.SKIPPED
    assert cdp.connect_calls == []
```

- [x] **步骤 2：运行测试并确认失败**

运行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_skin.py -v
```

预期：模块不存在。

- [x] **步骤 3：实现控制器状态机**

启动参数是会话收到的本次激活进程号；复用已有窗口或没有进程号时直接跳过。目标发现通过独立工作线程执行，结果回到 Qt 主线程。只在版本、能力、端口和进程号全部通过时连接。安装后执行检测表达式，失败立即恢复。每个终态都停止定时器、工作线程和套接字；重复调用 `close()` 必须幂等。日志使用固定阶段名和错误码，不包含页面地址或壁纸路径。

- [x] **步骤 4：运行目标测试**

运行同一命令，预期全部通过。

---

### 任务 8：接入应用、禁用参数和页面恢复快捷键

**文件：**

- 修改：`src/glory_boot/ui/application.py`
- 修改：`src/glory_boot/main.py`
- 修改：`src/glory_boot/services/session.py`
- 修改：`tests/test_ui_smoke.py`
- 修改：`tests/test_session.py`

**接口：**

- `LauncherApplication.__init__(..., skin_disabled_by_cli: bool = False)`
- 命令行新增：`--disable-skin`
- 皮肤被启用且本次冷启动获得进程号时，选择 `ApplicationActivationBackend` 和共享端口参数。
- 皮肤关闭、复用已有 Codex 或版本不兼容时，继续使用第一阶段 `QProcessBackend` 路径。
- `SessionController.launch_result_ready: Signal(object)` 在首次启动结果完成时发出 `LaunchResult`。

**消费：** 任务 1、3、7 的配置、启动后端和控制器。

**产出：** 普通启动默认不开放调试端口；显式启用皮肤时才走增强路径。

- [x] **步骤 1：写失败测试**

增加应用装配测试：

```python
def test_cli_disable_skin_overrides_enabled_config() -> None:
    options = _create_application(
        enabled=True,
        skin_disabled_by_cli=True,
    )

    assert options.skin_enabled is False
    assert options.launch_arguments == ""


def test_enabled_skin_allocates_one_loopback_port() -> None:
    options = _create_application(enabled=True, skin_disabled_by_cli=False)

    assert options.launch_arguments == (
        f"--remote-debugging-address=127.0.0.1 "
        f"--remote-debugging-port={options.skin_port}"
    )
```

- [x] **步骤 2：运行测试并确认失败**

运行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_ui_smoke.py -v
```

预期：命令行或装配接口不存在。

- [x] **步骤 3：接入默认关闭的皮肤模式**

在分配端口和连接控制器之前先检查配置与 CLI 覆盖。应用连接 `launch_result_ready`，把 `launched_pid` 交给皮肤控制器；已有窗口没有进程号时皮肤只记录跳过。控制器跟随 Qt 应用生命周期创建和关闭；交接完成退出启动器前调用 `skin.close()`，但已经注入的页面样式继续存在，直到用户恢复、页面重载或 Codex 退出。调试 WebSocket 在安装和检测完成后立即关闭。

- [x] **步骤 4：运行 UI 和皮肤目标测试**

运行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_ui_smoke.py tests\test_skin.py tests\test_launcher.py -v
```

预期：全部通过。

---

### 任务 9：打包资源、登记兼容版本并完成人工验收

**文件：**

- 修改：`packaging/glory_boot.spec`
- 修改：`pyproject.toml`
- 修改：`src/glory_boot/resources/skin_profiles.json`
- 修改：`README.md`
- 修改：`THIRD_PARTY_NOTICES.md`
- 修改：`docs/superpowers/plans/2026-11-09-phase2b-wallpaper.md`

**接口：**

- 打包包含 `skin.css`、`skin.js`、`skin_profiles.json` 和 `PySide6.QtWebSockets`。
- 只把经过真实 Codex 页面检查的版本加入兼容配置。

**消费：** 前八个任务的实现。

**产出：** 可回退的本地增强包和可核查的兼容性、许可与验收记录。

- [x] **步骤 1：运行全量自动测试**

运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\test.ps1
```

预期：全部通过，未新增外部依赖和敏感日志。

- [x] **步骤 2：更新资源与打包合同**

在 setuptools 包数据和 PyInstaller `datas` 中包含三个资源文件，加入
`hiddenimports=["PySide6.QtWebSockets"]`。增加仓库合同测试，断言资源文件存在、没有 Node 启动脚本、包配置包含 WebSocket 资源。

- [x] **步骤 3：请求真实 Codex 注入验证**

先向秋月大人报告将要启动和关闭 Codex，取得明确同意后执行一次：

- 全程关闭皮肤时启动，确认没有调试参数；
- 显式启用皮肤时启动，确认壁纸位于内容下方；
- 检查侧栏、聊天区、输入框、代码块、菜单和对话框；
- 使用 `Ctrl+Alt+Shift+R` 恢复；
- 页面重载和完全重启后确认无残留；
- 记录当前 Codex 包版本和对应能力。

不得读取聊天内容，不得截图，不得自行结束正在运行的 Codex。

- [x] **步骤 4：只登记通过验证的版本**

把本次版本、所需选择器和主题令牌加入兼容配置；验证失败的版本不登记。若当前版本验证失败，保留空兼容列表并报告失败原因，不把实验失败描述成完成。

- [x] **步骤 5：构建并检查发布包**

运行现有构建和打包命令，检查资源、Qt WebSocket 插件、配置、第三方声明和压缩包；确认壁纸私有素材没有进入公开包，除非已经明确允许。

- [x] **步骤 6：同步 README、来源说明和执行记录**

记录已验证版本、开关、恢复快捷键、测试命令、人工验收结果、已知限制和剩余风险。参考项目只记录设计思路和来源，不复制无明确许可的实现代码。

- [x] **步骤 7：检查工作区**

运行：

```powershell
git status --short
```

确认没有 `.venv/`、`.reference/`、日志、构建产物、调试端口记录、用户壁纸或页面数据进入待提交范围。停止并汇报；提交、默认启用和发布需要新的明确同意。

## 执行记录

| 日期 | 项目 | 结果 |
| --- | --- | --- |
| 2026-11-09 | 自动测试 | `271` 通过、`0` 失败 |
| 2026-11-09 | 资源加载 | 已登记并启用 Codex `26.1103.4239.0`；其他版本继续安全跳过 |
| 2026-11-09 | 运行态版本 | 安装脚本和 `sync-codex-runtime.ps1` 只在找到现存 Store 可执行文件时写入版本记录 |
| 2026-11-09 | onedir 与压缩包 | `skin.css`、`skin.js`、`skin_profiles.json`、`Qt6WebSockets.dll`、`QtWebSockets.pyd` 均存在 |
| 2026-11-09 | 发布包烟雾检查 | 媒体、QtMultimedia、资源和压缩包日志隔离检查通过 |
| 2026-11-09 | 打包基准 | 首个可见窗口 `297.7 ms`、媒体首帧 `489.3 ms`、Codex 启动请求 `300.3 ms` |
| 2026-11-09 | 压缩包 SHA-256 | `9a1bfe35d06788cd884e53d8a87dce059579d51b68f081d773f1d77241b57670` |
| 2026-11-09 | 最终审查修复 | 调试激活失败时无参数回退到原生 Shell，避免壁纸路径阻断 Codex；健康检查成功后重置连续重连预算，并补充回退与重连上限测试 |
| 2026-11-09 | 最终复验 | `275` 通过、`0` 失败；烟雾检查确认媒体、QtMultimedia、WebSocket 资源和日志隔离正常；最终打包基准首个可见窗口 `302.7 ms`、媒体首帧 `523.8 ms`、Codex 启动请求 `307.8 ms` |
| 2026-11-09 | 最终压缩包 | `dist/GloryCodexBoot-win-x64.zip`，SHA-256 `fb8b60bd0232e4f817a20340e6cd02fa5869b7ca35353aa160e7eb87276d2511` |

2026-11-09 补充验收：Codex `26.1103.4239.0` 已完成实际启动、壁纸注入、主内容透明、输入框深色半透明、文字对比度检查，并通过页面内 `dispose()` 恢复后重新注入。页面重载后的重新注入由自动测试覆盖；恢复快捷键仍需最终人工按键确认。
