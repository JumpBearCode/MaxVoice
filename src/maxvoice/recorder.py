import queue
import threading
import wave
from datetime import datetime
from pathlib import Path

import numpy as np
import sounddevice as sd

from .paths import audio_dir

SAMPLE_RATE = 16000
CHANNELS = 1
DTYPE = "int16"


class Recorder:
    """Streaming recorder with no length cap — appends frames to an in-memory queue
    until stop() is called, then writes a single WAV file."""

    def __init__(self) -> None:
        self._queue: queue.Queue[np.ndarray] = queue.Queue()
        self._stream: sd.InputStream | None = None
        self._running = False
        self._lock = threading.Lock()

    def _callback(self, indata, frames, time, status) -> None:  # noqa: ARG002
        if status:
            # Overruns/underruns — log but keep recording.
            print(f"[recorder] {status}")
        self._queue.put(indata.copy())

    def start(self) -> None:
        with self._lock:
            if self._running:
                return
            self._queue = queue.Queue()
            self._stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype=DTYPE,
                callback=self._callback,
            )
            self._stream.start()
            self._running = True

    def stop(self) -> tuple[Path, float]:
        with self._lock:
            if not self._running or self._stream is None:
                raise RuntimeError("recorder is not running")
            self._stream.stop()
            self._stream.close()
            self._stream = None
            self._running = False

        frames = []
        while not self._queue.empty():
            frames.append(self._queue.get_nowait())

        if not frames:
            audio = np.zeros((0, CHANNELS), dtype=np.int16)
        else:
            audio = np.concatenate(frames, axis=0)

        duration = audio.shape[0] / SAMPLE_RATE
        path = audio_dir() / f"{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.wav"
        with wave.open(str(path), "wb") as w:
            w.setnchannels(CHANNELS)
            w.setsampwidth(2)
            w.setframerate(SAMPLE_RATE)
            w.writeframes(audio.astype(np.int16).tobytes())
        return path, duration

    @property
    def is_running(self) -> bool:
        return self._running
