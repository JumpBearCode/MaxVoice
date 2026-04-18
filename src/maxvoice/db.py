from datetime import datetime
from zoneinfo import ZoneInfo

from sqlmodel import Field, Session, SQLModel, create_engine, select

from .paths import db_path
from .typing_speed import TypingSpeed, saved_seconds as _calc_saved

EASTERN = ZoneInfo("America/New_York")


class Recording(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(EASTERN))
    audio_path: str
    duration_seconds: float
    raw_text: str = ""
    refined_text: str = ""
    stt_model: str = ""
    refine_model: str = ""
    saved_seconds: float = 0.0


_engine = None


def engine():
    global _engine
    if _engine is None:
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


def recompute_saved_seconds(speed: TypingSpeed) -> int:
    with Session(engine()) as s:
        recs = list(s.exec(select(Recording)))
        for r in recs:
            text = r.refined_text or r.raw_text
            r.saved_seconds = _calc_saved(text, r.duration_seconds, speed)
            s.add(r)
        s.commit()
    return len(recs)
