from abc import ABC, abstractmethod
from collections.abc import Sequence
from pathlib import Path

from ..config import DictionaryEntry


class STTProvider(ABC):
    """Speech-to-text provider. All providers take a WAV file path and return plain text."""

    name: str = ""
    label: str = ""

    @abstractmethod
    def transcribe(
        self,
        audio_path: Path,
        language_hint: str = "",
        dictionary: Sequence[DictionaryEntry] = (),
    ) -> str:
        ...
