from pathlib import Path
from collections.abc import Callable

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QKeyEvent,
    QKeySequence,
    QPixmap,
    QResizeEvent,
    QShortcut,
)
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QGridLayout,
    QLabel,
    QWidget,
)

from glory_boot.services.media import MediaController


class BootWindow(QWidget):
    skip_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Codex 荣耀启动")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setStyleSheet("background-color: #000000;")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._background = QColor("#000000")
        self.poster = QLabel()
        self.poster.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.poster.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.poster.setStyleSheet("background-color: #000000;")
        self.poster.hide()

        self.waiting = QLabel()
        self.waiting.setAlignment(
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom
        )
        self.waiting.setContentsMargins(0, 0, 0, 64)
        self.waiting.setStyleSheet(
            "color: #D8ECFF; background: transparent;"
            "font-size: 24px; font-weight: 600;"
        )
        self.waiting.hide()

        self.video = QVideoWidget()
        self.video.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.video.hide()
        self.player: QMediaPlayer | None = None

        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.video, 0, 0)
        layout.addWidget(self.poster, 0, 0)
        layout.addWidget(self.waiting, 0, 0)
        self._skip_emitted = False
        self._fade_animation: QPropertyAnimation | None = None
        self.skip_shortcut = QShortcut(
            QKeySequence(Qt.Key.Key_Escape),
            self,
        )
        self.skip_shortcut.setContext(
            Qt.ShortcutContext.ApplicationShortcut
        )
        self.skip_shortcut.activated.connect(self._request_skip)
        self._poster_source: QPixmap | None = None

    @property
    def poster_is_visible(self) -> bool:
        return (
            self.poster.isVisible()
            and self.poster.pixmap() is not None
            and not self.poster.pixmap().isNull()
        )

    @property
    def background_name(self) -> str:
        return self._background.name()

    def show_poster_first(self, path: str) -> None:
        pixmap = QPixmap(path)
        if not Path(path).is_file() or pixmap.isNull():
            self._poster_source = None
            self.poster.clear()
            self.poster.hide()
            self.setStyleSheet("background-color: #000000;")
            return

        self._poster_source = pixmap
        self.poster.setPixmap(
            pixmap.scaled(
                max(1, self.width()),
                max(1, self.height()),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        self.poster.show()
        self.poster.raise_()

    def fade_out(
        self,
        duration_ms: int,
        completed: Callable[[], None],
    ) -> None:
        if duration_ms <= 0 or not self.isVisible() or self.windowOpacity() <= 0:
            completed()
            return

        animation = QPropertyAnimation(self, b"windowOpacity", self)
        animation.setDuration(duration_ms)
        animation.setStartValue(self.windowOpacity())
        animation.setEndValue(0.0)
        animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        animation.finished.connect(completed)
        self._fade_animation = animation
        animation.start()

    def attach_media(self, media: MediaController) -> None:
        media.set_video_output(self.video)
        self.player = media.player
        self.video.show()
        self.video.raise_()
        self.poster.hide()

    def initialize_player(self) -> QMediaPlayer:
        if self.player is not None:
            return self.player
        self.player = QMediaPlayer(self)
        self.video.show()
        self.poster.hide()
        return self.player

    def show_waiting(self, visible: bool) -> None:
        self.waiting.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop
        )
        self.waiting.setText("Codex 正在启动…\nEsc 跳过")
        self.waiting.setStyleSheet(
            "color: #D8ECFF; background: transparent;"
            "font-size: 24px; font-weight: 600;"
        )
        self.waiting.setContentsMargins(0, 40, 48, 0)
        self.waiting.setVisible(visible)
        if visible:
            self.waiting.raise_()

    def show_error(self, message: str) -> None:
        self.waiting.setText(message)
        self.waiting.setStyleSheet(
            "color: #FFD3A6; background: transparent;"
            "font-size: 22px; font-weight: 600;"
        )
        self.waiting.setContentsMargins(0, 0, 0, 64)
        self.waiting.show()
        self.waiting.raise_()
        self.show()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        if self._poster_source is not None:
            self.poster.setPixmap(
                self._poster_source.scaled(
                    max(1, self.width()),
                    max(1, self.height()),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self._request_skip()
            event.accept()
            return
        super().keyPressEvent(event)

    def _request_skip(self) -> None:
        if not self._skip_emitted:
            self._skip_emitted = True
            self.skip_requested.emit()
