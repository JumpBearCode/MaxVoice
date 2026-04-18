"""Cost estimation for STT + refine usage.

Rates are USD, sourced from public Azure OpenAI / Foundry pricing pages
(checked 2026-04). STT is billed per minute of audio (rounded to the second);
refine is billed per token (input + output).

Token counts aren't stored on Recording rows yet, so we estimate from text
length: ~1 token per CJK char, ~1 token per 4 latin chars. The SDK does return
real usage (`resp.usage` for chat and for gpt-4o-(mini-)transcribe); capturing
those into the DB is the next step if more accuracy is needed.
"""

# STT: USD per minute of audio.
# gpt-4o-transcribe: $0.006/min ; gpt-4o-mini-transcribe: $0.003/min
STT_PER_MIN: dict[str, float] = {
    "gpt-4o-transcribe": 0.006,
    "gpt-4o-mini-transcribe": 0.003,
}

# Refine: (input USD / 1M tokens, output USD / 1M tokens)
#   gpt-5.4-nano       $0.20 / $1.25
#   gpt-5.4-mini       $0.75 / $4.50
#   claude-haiku-4-5   $1.00 / $5.00
REFINE_PER_MTOK: dict[str, tuple[float, float]] = {
    "gpt-5.4-nano": (0.20, 1.25),
    "gpt-5.4-mini": (0.75, 4.50),
    "claude-haiku-4-5": (1.00, 5.00),
}

# Fixed overhead added to every refine call's input — the SYSTEM_PROMPT is
# ~4 KB of mostly English text, dominating token cost on short utterances.
SYSTEM_PROMPT_TOKENS = 1100


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    other = len(text) - cjk
    return cjk + max(other // 4, 1 if other else 0)


def stt_cost(model: str, duration_seconds: float) -> float:
    rate = STT_PER_MIN.get(model)
    if rate is None:
        return 0.0
    return duration_seconds / 60.0 * rate


def refine_cost(model: str, raw_text: str, refined_text: str) -> float:
    rates = REFINE_PER_MTOK.get(model)
    if rates is None:
        return 0.0
    in_rate, out_rate = rates
    in_tok = SYSTEM_PROMPT_TOKENS + estimate_tokens(raw_text)
    out_tok = estimate_tokens(refined_text)
    return (in_tok * in_rate + out_tok * out_rate) / 1_000_000.0


def total_cost(
    stt_model: str,
    refine_model: str,
    duration_seconds: float,
    raw_text: str,
    refined_text: str,
) -> float:
    cost = stt_cost(stt_model, duration_seconds)
    if refine_model:
        cost += refine_cost(refine_model, raw_text, refined_text)
    return cost
