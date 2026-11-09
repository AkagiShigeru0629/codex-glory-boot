from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget


class MediaController(QObject):
    first_frame = Signal()
    position_changed = Signal(int)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.player.setAudioOutput(self.audio)
        self._first_frame_emitted = False
        self.player.mediaStatusChanged.connect(self._on_media_status)
        self.player.errorOccurred.connect(self._on_error)
        self.player.mediaStatusChanged.connect(self._on_finished)
        self.player.positionChanged.connect(self.position_changed.emit)

    def set_video_output(self, output: QVideoWidget) -> None:
        self.player.setVideoOutput(output)

    def set_volume(self, volume: float) -> None:
        self.audio.setVolume(volume)

    def open(self, path: str) -> None:
        self._first_frame_emitted = False
        self.player.setSource(QUrl.fromLocalFile(path))

    def play(self) -> None:
        self.player.play()

    def pause_at(self, seconds: float) -> None:
        self.player.setPosition(max(0, round(seconds * 1000)))
        self.player.pause()

    def pause(self) -> None:
        self.player.pause()

    def resume(self) -> None:
        self.player.play()

    def stop(self) -> None:
        self.player.stop()

    @property
    def position_seconds(self) -> float:
        return self.player.position() / 1000

    def _on_media_status(self, status: QMediaPlayer.MediaStatus) -> None:
        if (
            not self._first_frame_emitted
            and status
            in {
                QMediaPlayer.MediaStatus.LoadedMedia,
                QMediaPlayer.MediaStatus.BufferedMedia,
            }
        ):
            self._first_frame_emitted = True
            self.first_frame.emit()

    def _on_error(
        self,
        _error: QMediaPlayer.Error,
        error_string: str,
    ) -> None:
        self.failed.emit(error_string or "媒体播放失败")

    def _on_finished(self, status: QMediaPlayer.MediaStatus) -> None:
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self.finished.emit()
