import json
import os

from dotenv import load_dotenv
from pydantic import BaseModel, Field

from .paths import config_path
from .typing_speed import TypingSpeed
from .vad import VADParams

load_dotenv()


class VADConfig(BaseModel):
    """Tunable params for the time-saved metric's silence handling.

    Defaults lean toward *under*-estimating saved time: a conservative
    number is more defensible when shown to others than an optimistic one.
    """
    max_natural_pause_ms: int = 2500
    min_active_speech_seconds: float = 0.5
    speech_threshold: float = 0.5
    min_speech_duration_ms: int = 250

    def to_params(self) -> VADParams:
        return VADParams(
            max_natural_pause_ms=self.max_natural_pause_ms,
            speech_threshold=self.speech_threshold,
            min_speech_duration_ms=self.min_speech_duration_ms,
        )


class AzureCreds(BaseModel):
    endpoint: str = Field(default_factory=lambda: os.getenv("AZURE_OPENAI_ENDPOINT", ""))
    api_key: str = Field(default_factory=lambda: os.getenv("AZURE_OPENAI_API_KEY", ""))
    api_version: str = Field(
        default_factory=lambda: os.getenv("AZURE_OPENAI_API_VERSION", "2025-04-01-preview")
    )

    def deployment(self, env_var: str, fallback: str) -> str:
        return os.getenv(env_var, fallback)


class UserConfig(BaseModel):
    hotkey: str = "<alt>+q"
    stt_model: str = "gpt-4o-mini-transcribe"
    refine_model: str = "gpt-5.4-nano"
    refine_enabled: bool = True
    typing_speed: TypingSpeed = Field(default_factory=TypingSpeed)
    vad: VADConfig = Field(default_factory=VADConfig)
    retention_days: int = 30
    max_audio_gb: float = 1.0
    auto_paste: bool = True
    language_hint: str = ""

    @classmethod
    def load(cls) -> "UserConfig":
        p = config_path()
        if p.exists():
            try:
                return cls.model_validate_json(p.read_text())
            except Exception:
                pass
        cfg = cls()
        cfg.save()
        return cfg

    def save(self) -> None:
        config_path().write_text(json.dumps(self.model_dump(), indent=2))


AZURE = AzureCreds()
