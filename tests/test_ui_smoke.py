from pathlib import Path

from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from glory_boot.domain.models import Rect
from glory_boot.ui.application import present_initial_window
from glory_boot.ui.boot_window import BootWindow


def test_poster_is_visible_before_player_is_created(
    qapp,
    tmp_path: Path,
) -> None:
    poster_path = tmp_path / "poster.png"
    Image.new("RGB", (16, 9), "#112233").save(poster_path)
    window = BootWindow()

    window.show_poster_first(str(poster_path))
    window.show()
    qapp.processEvents()

    assert window.player is None
    assert window.poster_is_visible is True
    window.close()


def test_missing_poster_opens_black_recovery_window(
    qapp,
    tmp_path: Path,
) -> None:
    window = BootWindow()

    window.show_poster_first(str(tmp_path / "missing.png"))
    window.show()
    qapp.processEvents()

    assert window.isVisible() is True
    assert window.background_name == "#000000"
    assert window.poster_is_visible is False
    window.close()


def test_escape_emits_skip_only_once(qapp) -> None:
    window = BootWindow()
    events: list[None] = []
    window.skip_requested.connect(lambda: events.append(None))
    window.show()
    qapp.processEvents()

    QTest.keyClick(window, Qt.Key.Key_Escape)
    QTest.keyClick(window, Qt.Key.Key_Escape)
    qapp.processEvents()

    assert len(events) == 1
    window.close()


def test_waiting_overlay_does_not_shrink_video(qapp) -> None:
    window = BootWindow()
    window.resize(960, 540)
    window.poster.hide()
    window.video.show()
    window.show()
    qapp.processEvents()

    window.show_waiting(True)
    qapp.processEvents()

    assert window.video.geometry() == window.rect()
    assert window.waiting.geometry() == window.rect()
    window.close()


def test_waiting_overlay_uses_top_right_safe_area(qapp) -> None:
    window = BootWindow()
    window.resize(960, 540)
    window.show_waiting(True)
    qapp.processEvents()

    alignment = window.waiting.alignment()
    margins = window.waiting.contentsMargins()

    assert alignment & Qt.AlignmentFlag.AlignRight
    assert alignment & Qt.AlignmentFlag.AlignTop
    assert margins.right() >= 32
    assert margins.top() >= 32
    assert "\n" in window.waiting.text()
    window.close()


def test_application_escape_shortcut_is_connected(qapp) -> None:
    window = BootWindow()
    events: list[None] = []
    window.skip_requested.connect(lambda: events.append(None))

    assert window.skip_shortcut.context() == Qt.ShortcutContext.ApplicationShortcut
    window.skip_shortcut.activated.emit()
    window.skip_shortcut.activated.emit()

    assert len(events) == 1
    window.close()


def test_window_fade_out_is_animated_and_invokes_completion(qapp) -> None:
    window = BootWindow()
    completed: list[None] = []
    window.show()
    qapp.processEvents()

    window.fade_out(40, lambda: completed.append(None))
    QTest.qWait(80)

    assert completed == [None]
    assert window.windowOpacity() <= 0.01
    window.close()


class PresentationWindow:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def winId(self) -> int:
        self.calls.append("winId")
        return 900

    def show(self) -> None:
        self.calls.append("show")


class Placement:
    def initial_viewport(self) -> Rect:
        return Rect(-1200, 40, 1400, 820)


class PresentationApplication:
    def processEvents(self) -> None:
        self.calls.append("processEvents")


class PresentationTimer:
    def mark(self, name: str) -> None:
        self.calls.append(f"mark:{name}")


def test_present_initial_window_places_before_showing(qapp) -> None:
    window = PresentationWindow()
    application = PresentationApplication()
    application.calls = window.calls
    timer = PresentationTimer()
    timer.calls = window.calls
    placed: list[tuple[int, Rect]] = []

    present_initial_window(
        window=window,
        placement=Placement(),
        place_window=lambda hwnd, rect: placed.append((hwnd, rect)),
        qt_app=application,
        timer=timer,
    )

    assert placed == [(900, Rect(-1200, 40, 1400, 820))]
    assert window.calls == [
        "winId",
        "show",
        "processEvents",
        "mark:window_visible",
    ]
