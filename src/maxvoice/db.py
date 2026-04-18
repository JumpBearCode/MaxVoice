from datetime import datetime, timezone

from sqlmodel import Field, Session, SQLModel, create_engine, select

from .paths import db_path


class Recording(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    audio_path: str
    duration_seconds: float
    raw_text: str = ""
    refined_text: str = ""
    stt_model: str = ""
    refine_model: str = ""
    typing_wpm: int = 40
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


def estimate_saved_seconds(text: str, duration_s: float, wpm: int) -> float:
    # Rough char→word conversion: CJK 1 char ≈ 1 word; latin words split by whitespace.
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    latin_words = len([w for w in text.split() if any(c.isalpha() for c in w)])
    words = max(cjk + latin_words, 1)
    typing_s = words / max(wpm, 1) * 60.0
    return max(typing_s - duration_s, 0.0)
