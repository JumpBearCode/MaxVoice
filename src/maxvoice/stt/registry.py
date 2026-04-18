from .azure_openai import GPT4oMiniTranscribe, GPT4oTranscribe
from .base import STTProvider

AVAILABLE_STT: list[type[STTProvider]] = [
    GPT4oMiniTranscribe,
    GPT4oTranscribe,
]

_BY_NAME = {cls.name: cls for cls in AVAILABLE_STT}


def get_stt(name: str) -> STTProvider:
    cls = _BY_NAME.get(name, GPT4oMiniTranscribe)
    return cls()
