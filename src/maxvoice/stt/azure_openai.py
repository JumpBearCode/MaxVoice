from pathlib import Path

from openai import AzureOpenAI

from ..config import AZURE
from .base import STTProvider


def _client() -> AzureOpenAI:
    return AzureOpenAI(
        azure_endpoint=AZURE.endpoint,
        api_key=AZURE.api_key,
        api_version=AZURE.api_version,
    )


class _AzureTranscribe(STTProvider):
    deployment_env: str = ""
    deployment_default: str = ""

    def transcribe(self, audio_path: Path, language_hint: str = "") -> str:
        client = _client()
        deployment = AZURE.deployment(self.deployment_env, self.deployment_default)
        kwargs: dict = {"model": deployment}
        if language_hint:
            kwargs["language"] = language_hint
        with audio_path.open("rb") as f:
            resp = client.audio.transcriptions.create(file=f, **kwargs)
        return resp.text.strip()


class Whisper(_AzureTranscribe):
    name = "whisper"
    label = "Whisper (Azure OpenAI)"
    deployment_env = "AZURE_STT_WHISPER_DEPLOYMENT"
    deployment_default = "whisper"


class GPT4oTranscribe(_AzureTranscribe):
    name = "gpt-4o-transcribe"
    label = "GPT-4o Transcribe (accurate)"
    deployment_env = "AZURE_STT_GPT4O_TRANSCRIBE_DEPLOYMENT"
    deployment_default = "gpt-4o-transcribe"


class GPT4oMiniTranscribe(_AzureTranscribe):
    name = "gpt-4o-mini-transcribe"
    label = "GPT-4o Mini Transcribe (fast & cheap)"
    deployment_env = "AZURE_STT_GPT4O_MINI_TRANSCRIBE_DEPLOYMENT"
    deployment_default = "gpt-4o-mini-transcribe"
