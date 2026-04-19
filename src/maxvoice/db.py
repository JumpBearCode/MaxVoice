import sqlite3
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlmodel import Field, Session, SQLModel, create_engine, select

from .paths import db_path
from .typing_speed import TypingSpeed, saved_seconds as _calc_saved
from .vad import VADParams, active_speech_seconds_from_wav

EASTERN = ZoneInfo("America/New_York")


class Recording(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(EASTERN))
    audio_path: str
    duration_seconds: float
    # Wall-clock duration_seconds stays for STT billing + UI. active_speech_seconds
    # is the VAD-derived "mouth actually moving" time used for the saved metric.
    # Nullable so legacy rows can be detected + backfilled.
    active_speech_seconds: float | None = Field(default=None)
    raw_text: str = ""
    refined_text: str = ""
    stt_model: str = ""
    refine_model: str = ""
    saved_seconds: float = 0.0


_engine = None


def _ensure_columns() -> None:
    """SQLModel.metadata.create_all creates missing tables but not missing
    columns. Hand-patch the one schema change we've introduced."""
    p = db_path()
    if not p.exists():
        return
    conn = sqlite3.connect(str(p))
    try:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(recording)").fetchall()}
        if cols and "active_speech_seconds" not in cols:
            conn.execute("ALTER TABLE recording ADD COLUMN active_speech_seconds REAL")
            conn.commit()
    finally:
        conn.close()


def engine():
    global _engine
    if _engine is None:
        _ensure_columns()
        _engine = create_engine(f"sqlite:///{db_path()}")
        SQLModel.metadata.create_all(_engine)
    return _engine


def insert(rec: Recording) -> Recording:
    with Session(engine()) as s:
        s.add(rec)
        s.commit()
        s.refresh(rec)
    return rec


def all_recordings(limit: int = 200) -> list[Recording]:
    with Session(engine()) as s:
        return list(
            s.exec(select(Recording).order_by(Recording.created_at.desc()).limit(limit))
        )


def backfill_active_speech(params: VADParams, force: bool = False) -> int:
    """Fill active_speech_seconds for rows missing it (or all rows if force=True).

    Reads the saved WAV and runs VAD. If the WAV is gone or VAD fails, falls
    back to wall-clock duration — same as the old behavior — so old entries
    just keep their existing saved_seconds value.
    """
    updated = 0
    with Session(engine()) as s:
        if force:
            recs = list(s.exec(select(Recording)))
        else:
            recs = list(s.exec(
                select(Recording).where(Recording.active_speech_seconds == None)  # noqa: E711
            ))
        for r in recs:
            wav = Path(r.audio_path)
            active: float | None = None
            if wav.exists():
                active = active_speech_seconds_from_wav(wav, params)
            if active is None:
                active = r.duration_seconds
            r.active_speech_seconds = active
            s.add(r)
            updated += 1
        s.commit()
    return updated


def recompute_saved_seconds(speed: TypingSpeed, min_active_seconds: float = 0.5) -> int:
    with Session(engine()) as s:
        recs = list(s.exec(select(Recording)))
        for r in recs:
            text = r.refined_text or r.raw_text
            active = (
                r.active_speech_seconds
                if r.active_speech_seconds is not None
                else r.duration_seconds
            )
            r.saved_seconds = _calc_saved(text, active, speed, min_active_seconds)
            s.add(r)
        s.commit()
    return len(recs)
