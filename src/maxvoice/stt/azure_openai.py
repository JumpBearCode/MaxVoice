from pathlib import Path

from openai import AzureOpenAI

from ..config import AZURE
from .base import STTProvider

# Style-match prompt: models mimic the prompt's style rather than follow instructions.
# Keeping English tech terms inline teaches the model not to translate them.
_PROMPT = (
    "以下是中英混合的技术讨论。保留英文术语原文，不要翻译成中文。"
    "示例：这个 garbage collection 的 pipeline 需要 refactor 一下，"
    "我去 GitHub 上开个 pull request，然后 commit 到这个 folder。"
    "Azure AI Foundry 的 model，input token 和 output token 的 cost "
    "你帮我查一下，再做成一个 column。benchmark、embedding、deployment、"
    "API、CICD、template、on-premises、Cloud Code、OpenAI、token 都保留英文。"
)


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
        kwargs: dict = {"model": deployment, "prompt": _PROMPT}
        if language_hint:
            kwargs["language"] = language_hint
        with audio_path.open("rb") as f:
            resp = client.audio.transcriptions.create(file=f, **kwargs)
        return resp.text.strip()


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
