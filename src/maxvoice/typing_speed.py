"""Per-language typing speed → estimated typing time.

Each supported language has:
- a default WPM (international average, see DEFAULTS below)
- a chars-per-"word" convention used to convert WPM ↔ CPM.

CPM is the internal unit because "WPM" is ill-defined across scripts (CJK has
no whitespace), so we classify each character by its Unicode block, sum chars
per language bucket, and divide by that language's CPM.

WPM conventions per language (matches each language's standard typing test):
  english:  1 word = 5 chars (international standard; "the" and "encyclopedia"
            both count proportionally to their length)
  chinese:  1 "word" = 1 字 — Chinese typing tests measure 字/分, not WPM
  hindi:    1 word = 6 chars (Devanagari avg word length, incl. matras)
  telugu:   1 word = 6 chars
  tamil:    1 word = 7 chars (agglutinative, words tend longer)

International-average defaults:
  english 40 WPM, chinese 50 字/min, hindi 25 WPM, telugu 20 WPM, tamil 25 WPM
"""

from pydantic import BaseModel

CHARS_PER_WORD: dict[str, int] = {
    "english": 5,
    "chinese": 1,
    "hindi": 6,
    "telugu": 6,
    "tamil": 7,
}

# Unicode block ranges per language bucket. Anything outside these falls back
# to "english" (covers Latin, digits, common punctuation, Cyrillic, etc.).
# Hiragana/Katakana/Hangul share the "chinese" rate as a CJK-family fallback —
# not linguistically precise but adequate for a typing-time estimate.
SCRIPT_RANGES: dict[str, list[tuple[int, int]]] = {
    "chinese": [
        (0x4E00, 0x9FFF),   # CJK Unified Ideographs
        (0x3400, 0x4DBF),   # CJK Extension A
        (0x3040, 0x309F),   # Hiragana
        (0x30A0, 0x30FF),   # Katakana
        (0xAC00, 0xD7AF),   # Hangul Syllables
    ],
    "hindi": [(0x0900, 0x097F)],   # Devanagari
    "telugu": [(0x0C00, 0x0C7F)],
    "tamil": [(0x0B80, 0x0BFF)],
}


class TypingSpeed(BaseModel):
    """Per-language typing speed, in each language's native WPM convention."""

    english: int = 40   # WPM (5 chars/word)
    chinese: int = 50   # 字/min (1 char = 1 unit)
    hindi: int = 25     # WPM (6 chars/word)
    telugu: int = 20    # WPM (6 chars/word)
    tamil: int = 25     # WPM (7 chars/word)

    def cpm(self, lang: str) -> float:
        wpm = getattr(self, lang, self.english)
        return wpm * CHARS_PER_WORD.get(lang, 5)


def classify(ch: str) -> str:
    code = ord(ch)
    for lang, ranges in SCRIPT_RANGES.items():
        if any(lo <= code <= hi for lo, hi in ranges):
            return lang
    return "english"


def estimate_typing_seconds(text: str, speed: TypingSpeed) -> float:
    counts: dict[str, int] = {}
    for ch in text:
        if ch.isspace():
            continue
        lang = classify(ch)
        counts[lang] = counts.get(lang, 0) + 1
    total = 0.0
    for lang, n in counts.items():
        cpm = speed.cpm(lang)
        if cpm > 0:
            total += n / cpm * 60.0
    return total


def saved_seconds(
    text: str,
    active_speech_seconds: float,
    speed: TypingSpeed,
    min_active_seconds: float = 0.5,
) -> float:
    """Typing-time estimate minus actual speech time.

    `active_speech_seconds` should be VAD-derived (time the user's mouth was
    moving) rather than wall-clock — silence and thinking pauses aren't a
    voice-tool cost. If VAD finds less than `min_active_seconds` of speech
    we report 0 to avoid inflated savings from mostly-silent clips or STT
    hallucinations.
    """
    if active_speech_seconds < min_active_seconds:
        return 0.0
    return max(estimate_typing_seconds(text, speed) - active_speech_seconds, 0.0)
