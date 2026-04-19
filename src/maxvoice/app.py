import traceback
from pathlib import Path

import numpy as np
from PyQt6.QtCore import QObject, QThread, pyqtSignal

from . import db, paste, storage, typing_speed, vad
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
        audio: np.ndarray,
        cfg: UserConfig,
        mode: str = "refine",
    ) -> None:
        super().__init__()
        self.audio_path = audio_path
        self.duration = duration
        self.audio = audio
        self.cfg = cfg
        self.mode = mode

    def run(self) -> None:
        try:
            active = vad.active_speech_seconds_from_array(
                self.audio, self.cfg.vad.to_params()
            )
            if active is None:
                active = self.duration

            stt = get_stt(self.cfg.stt_model)
            raw = stt.transcribe(
                self.audio_path, self.cfg.language_hint, self.cfg.dictionary
            )

            refined = raw
            refine_name = ""
            # Translate mode always runs the LLM (refine_enabled only gates the
            # normal-mode cleanup pass — translation is the whole point here).
            needs_llm = raw.strip() and (
                self.mode == "translate" or self.cfg.refine_enabled
            )
            if needs_llm:
                provider = get_refine(self.cfg.refine_model)
                if self.mode == "translate":
                    refined = provider.translate(raw, self.cfg.dictionary)
                else:
                    refined = provider.refine(raw, self.cfg.dictionary)
                refine_name = provider.name

            saved = typing_speed.saved_seconds(
                refined, active, self.cfg.typing_speed,
                self.cfg.vad.min_active_speech_seconds,
            )
            rec = db.Recording(
                audio_path=str(self.audio_path),
                duration_seconds=self.duration,
                active_speech_seconds=active,
                raw_text=raw,
                refined_text=refined,
                stt_model=self.cfg.stt_model,
                refine_model=refine_name,
                saved_seconds=saved,
            )
            db.insert(rec)
            self.finished_ok.emit(rec)
        except Exception as e:
            # Print full traceback to stderr so failures are visible in the
            # terminal even when the tray notification is dismissed/suppressed.
            traceback.print_exc()
            self.failed.emit(f"{type(e).__name__}: {e}")


class App(QObject):
    state_changed = pyqtSignal(str)        # "idle" | "recording" | "transcribing"
    transcription_done = pyqtSignal(object)  # db.Recording
    error = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        self.cfg = UserConfig.load()
        self.recorder = Recorder()
        self.hotkey = HotkeyListener(
            self._hotkey_map(self.cfg), self._on_toggle_threadsafe
        )
        self._worker: TranscribeWorker | None = None
        self._active_mode: str = "refine"  # set on each recording start
        # NSEvent monitors fire on the Qt main thread, so this queued signal
        # is no longer strictly required for thread marshalling. Kept as a
        # defensive boundary — if the listener backend ever changes again,
        # callbacks still arrive via a Qt signal rather than reentrantly.
        self._toggle_bridge = _ToggleBridge()
        self._toggle_bridge.toggled.connect(self._on_toggle)

    @staticmethod
    def _hotkey_map(cfg: UserConfig) -> dict[str, str]:
        return {cfg.hotkey: "refine", cfg.translate_hotkey: "translate"}

    def start(self) -> None:
        self.hotkey.start()
        n = db.backfill_active_speech(self.cfg.vad.to_params())
        if n:
            print(f"[app] backfilled active_speech for {n} records")
            db.recompute_saved_seconds(
                self.cfg.typing_speed, self.cfg.vad.min_active_speech_seconds
            )
        self._run_cleanup()
        self.state_changed.emit("idle")

    def _run_cleanup(self) -> None:
        deleted = storage.cleanup_audio(
            self.cfg.retention_days, self.cfg.max_audio_gb
        )
        if deleted:
            print(
                f"[app] retention: deleted {deleted} old WAV(s) "
                f"(>{self.cfg.retention_days} days, over {self.cfg.max_audio_gb} GB)"
            )

    def stop(self) -> None:
        self.hotkey.stop()
        if self.recorder.is_running:
            try:
                self.recorder.stop()
            except Exception:
                pass

    def apply_config(self, cfg: UserConfig) -> None:
        recompute = (
            cfg.typing_speed != self.cfg.typing_speed
            or cfg.vad != self.cfg.vad
        )
        vad_params_changed = cfg.vad.to_params() != self.cfg.vad.to_params()
        retention_changed = (
            cfg.retention_days != self.cfg.retention_days
            or cfg.max_audio_gb != self.cfg.max_audio_gb
        )
        self.cfg = cfg
        cfg.save()
        self.hotkey.update(self._hotkey_map(cfg))
        if vad_params_changed:
            # VAD params changed → stale active_speech values. Rerun VAD on
            # anything we still have audio for, then recompute saved.
            db.backfill_active_speech(cfg.vad.to_params(), force=True)
        if recompute:
            db.recompute_saved_seconds(cfg.typing_speed, cfg.vad.min_active_speech_seconds)
        if retention_changed:
            self._run_cleanup()

    def _on_toggle_threadsafe(self, mode: str, active: bool) -> None:
        self._toggle_bridge.toggled.emit(mode, active)

    def _on_toggle(self, mode: str, active: bool) -> None:
        if active:
            self._active_mode = mode
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
            audio_path, duration, audio = self.recorder.stop()
        except Exception as e:
            self.error.emit(f"录音结束失败: {e}")
            self.state_changed.emit("idle")
            return

        self.state_changed.emit("transcribing")
        self._worker = TranscribeWorker(
            audio_path, duration, audio, self.cfg, self._active_mode
        )
        self._worker.finished_ok.connect(self._on_transcription)
        self._worker.failed.connect(self._on_transcription_failed)
        self._worker.start()

    def _on_transcription(self, rec) -> None:
        if rec.refined_text:
            paste.deliver(rec.refined_text, self.cfg.auto_paste)
        self._run_cleanup()
        self.transcription_done.emit(rec)
        self.state_changed.emit("idle")

    def _on_transcription_failed(self, msg: str) -> None:
        self.error.emit(f"转写失败: {msg}")
        self.state_changed.emit("idle")


class _ToggleBridge(QObject):
    toggled = pyqtSignal(str, bool)
