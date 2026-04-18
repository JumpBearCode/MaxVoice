from .azure_chat import GPT54Mini, GPT54Nano
from .base import RefineProvider

# Claude Haiku 4.5 is deployed but Foundry exposes Anthropic models via a separate
# /anthropic endpoint, not the OpenAI-compatible chat.completions path used here.
# Adding it back requires a dedicated AnthropicProvider using the anthropic SDK.
AVAILABLE_REFINE: list[type[RefineProvider]] = [
    GPT54Nano,
    GPT54Mini,
]

_BY_NAME = {cls.name: cls for cls in AVAILABLE_REFINE}


def get_refine(name: str) -> RefineProvider:
    cls = _BY_NAME.get(name, GPT54Nano)
    return cls()
