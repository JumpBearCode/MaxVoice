"""Audio retention — cap on-disk WAV storage without dropping recent work.

Rule: a WAV is deleted only when BOTH conditions hold simultaneously:
  (a) it is older than `retention_days`
  (b) the total audio folder size exceeds `max_audio_gb`

So the retention window is a hard guarantee (nothing inside it is ever
touched); the budget only kicks in to trim past-retention files when disk
usage grows. Files are removed oldest-first until the budget is met.

Returns the number of files deleted.
"""
from __future__ import annotations

import time

from .paths import audio_dir


def cleanup_audio(retention_days: int, max_audio_gb: float) -> int:
    max_bytes = int(max_audio_gb * 1024 * 1024 * 1024)
    cutoff_mtime = time.time() - retention_days * 86400

    wavs = sorted(audio_dir().glob("*.wav"), key=lambda p: p.stat().st_mtime)
    total = sum(w.stat().st_size for w in wavs)

    deleted = 0
    for wav in wavs:  # oldest first
        if total <= max_bytes:
            break
        try:
            st = wav.stat()
        except FileNotFoundError:
            continue
        if st.st_mtime >= cutoff_mtime:
            # Still inside the retention window — protected even if over budget.
            continue
        try:
            wav.unlink()
            total -= st.st_size
            deleted += 1
        except OSError as e:
            print(f"[storage] failed to delete {wav.name}: {e}")

    return deleted
