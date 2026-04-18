from abc import ABC, abstractmethod
from pathlib import Path


class STTProvider(ABC):
    """Speech-to-text provider. All providers take a WAV file path and return plain text."""

    name: str = ""
    label: str = ""

    @abstractmethod
    def transcribe(self, audio_path: Path, language_hint: str = "") -> str:
        ...
