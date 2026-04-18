from pathlib import Path

from PyQt6.QtCore import QObject, QThread, pyqtSignal

from . import db, paste
from .config import UserConfig
from .hotkey import HotkeyListener
from .recorder import Recorder
from .refine import get_refine
from .stt import get_stt


class TranscribeWorker(QThread):
    finished_ok = pyqtSignal(object)  # db.Recording
    failed = pyqtSignal(str)

    def __init__(
        self,
        audio_path: Path,
        duration: float,
        cfg: UserConfig,
    ) -> None:
        super().__init__()
        self.audio_path = audio_path
        self.duration = duration
        self.cfg = cfg

    def run(self) -> None:
        try:
            stt = get_stt(self.cfg.stt_model)
            raw = stt.transcribe(self.audio_path, self.cfg.language_hint)

            refined = raw
            refine_name = ""
            if self.cfg.refine_enabled and raw.strip():
                refiner = get_refine(self.cfg.refine_model)
                refined = refiner.refine(raw)
                refine_name = refiner.name

            saved = db.estimate_saved_seconds(refined, self.duration, self.cfg.typing_wpm)
            rec = db.Recording(
                audio_path=str(self.audio_path),
                duration_seconds=self.duration,
                raw_text=raw,
                refined_text=refined,
                stt_model=self.cfg.stt_model,
                refine_model=refine_name,
                typing_wpm=self.cfg.typing_wpm,
                saved_seconds=saved,
            )
            db.insert(rec)
            self.finished_ok.emit(rec)
        except Exception as e:
            self.failed.emit(f"{type(e).__name__}: {e}")


class App(QObject):
    state_changed = pyqtSignal(str)        # "idle" | "recording" | "transcribing"
    transcription_done = pyqtSignal(object)  # db.Recording
    error = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        self.cfg = UserConfig.load()
        self.recorder = Recorder()
        self.hotkey = HotkeyListener(self.cfg.hotkey, self._on_toggle_threadsafe)
        self._worker: TranscribeWorker | None = None
        # pynput fires from a non-Qt thread — use a queued signal to marshal onto main.
        self._toggle_bridge = _ToggleBridge()
        self._toggle_bridge.toggled.connect(self._on_toggle)

    def start(self) -> None:
        self.hotkey.start()
        self.state_changed.emit("idle")

    def stop(self) -> None:
        self.hotkey.stop()
        if self.recorder.is_running:
            try:
                self.recorder.stop()
            except Exception:
                pass

    def apply_config(self, cfg: UserConfig) -> None:
        self.cfg = cfg
        cfg.save()
        self.hotkey.update(cfg.hotkey)

    def _on_toggle_threadsafe(self, active: bool) -> None:
        self._toggle_bridge.toggled.emit(active)

    def _on_toggle(self, active: bool) -> None:
        if active:
            self._start_recording()
        else:
            self._stop_recording()

    def _start_recording(self) -> None:
        try:
            self.recorder.start()
            self.state_changed.emit("recording")
        except Exception as e:
            self.error.emit(f"录音启动失败: {e}")

    def _stop_recording(self) -> None:
        if not self.recorder.is_running:
            return
        try:
            audio_path, duration = self.recorder.stop()
        except Exception as e:
            self.error.emit(f"录音结束失败: {e}")
            self.state_changed.emit("idle")
            return

        self.state_changed.emit("transcribing")
        self._worker = TranscribeWorker(audio_path, duration, self.cfg)
        self._worker.finished_ok.connect(self._on_transcription)
        self._worker.failed.connect(self._on_transcription_failed)
        self._worker.start()

    def _on_transcription(self, rec) -> None:
        if rec.refined_text:
            paste.deliver(rec.refined_text, self.cfg.auto_paste)
        self.transcription_done.emit(rec)
        self.state_changed.emit("idle")

    def _on_transcription_failed(self, msg: str) -> None:
        self.error.emit(f"转写失败: {msg}")
        self.state_changed.emit("idle")


class _ToggleBridge(QObject):
    toggled = pyqtSignal(bool)
