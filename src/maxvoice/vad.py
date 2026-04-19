"""Voice activity detection → active speech seconds.

Why this exists: wall-clock recording length over-counts the "cost" of voice
dictation. A user who presses the hotkey, thinks for 3 seconds, then speaks
isn't paying that 3 seconds to voice — they'd spend it thinking either way.
For a defensible time-saved metric we want "how many seconds your mouth was
actually moving", not "how long the mic was hot".

Algorithm:
 1. silero-vad returns raw speech segments [(start, end), ...].
 2. Segments separated by a gap < max_natural_pause are merged — normal
    sentence breaks and within-speech breathing should NOT be excluded;
    only real thinking/distraction pauses should.
 3. Sum merged segment durations.

Falls back to `None` on any VAD failure so callers can substitute wall-clock.
"""
from __future__ import annotations

import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np

SAMPLE_RATE = 16000

_MODEL = None


def _model():
    global _MODEL
    if _MODEL is None:
        from silero_vad import load_silero_vad
        _MODEL = load_silero_vad(onnx=True)
    return _MODEL


@dataclass
class VADParams:
    max_natural_pause_ms: int = 2500
    speech_threshold: float = 0.5
    min_speech_duration_ms: int = 250


def active_speech_seconds_from_array(
    audio_int16: np.ndarray,
    params: VADParams,
) -> float | None:
    """Compute active speech from an int16 mono 16kHz array. None on failure."""
    if audio_int16.size == 0:
        return 0.0
    try:
        from silero_vad import get_speech_timestamps

        if audio_int16.ndim > 1:
            audio_int16 = audio_int16[:, 0]
        audio_f = audio_int16.astype(np.float32) / 32768.0
        segments = get_speech_timestamps(
            audio_f,
            _model(),
            return_seconds=True,
            threshold=params.speech_threshold,
            min_speech_duration_ms=params.min_speech_duration_ms,
            sampling_rate=SAMPLE_RATE,
        )
    except Exception as e:
        print(f"[vad] failed, falling back to wall-clock: {e}")
        return None

    if not segments:
        return 0.0

    pause_s = params.max_natural_pause_ms / 1000.0
    merged: list[tuple[float, float]] = [(segments[0]["start"], segments[0]["end"])]
    for seg in segments[1:]:
        last_start, last_end = merged[-1]
        if seg["start"] - last_end < pause_s:
            merged[-1] = (last_start, seg["end"])
        else:
            merged.append((seg["start"], seg["end"]))

    return float(sum(end - start for start, end in merged))


def active_speech_seconds_from_wav(wav_path: Path, params: VADParams) -> float | None:
    try:
        with wave.open(str(wav_path), "rb") as w:
            if w.getframerate() != SAMPLE_RATE or w.getnchannels() != 1:
                return None
            raw = w.readframes(w.getnframes())
            audio = np.frombuffer(raw, dtype=np.int16)
    except Exception:
        return None
    return active_speech_seconds_from_array(audio, params)
