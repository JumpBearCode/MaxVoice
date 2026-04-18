import json
import os

from dotenv import load_dotenv
from pydantic import BaseModel, Field

from .paths import config_path

load_dotenv()


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
    typing_wpm: int = 40
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
