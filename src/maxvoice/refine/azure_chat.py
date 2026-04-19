from openai import AzureOpenAI

from ..config import AZURE
from .base import SYSTEM_PROMPT, TRANSLATE_SYSTEM_PROMPT, RefineProvider


def _client() -> AzureOpenAI:
    return AzureOpenAI(
        azure_endpoint=AZURE.endpoint,
        api_key=AZURE.api_key,
        api_version=AZURE.api_version,
    )


class _AzureChatRefine(RefineProvider):
    deployment_env: str = ""
    deployment_default: str = ""

    def _complete(self, system_prompt: str, raw_text: str) -> str:
        client = _client()
        deployment = AZURE.deployment(self.deployment_env, self.deployment_default)
        # GPT-5.x uses max_completion_tokens, not max_tokens. Cap at 4× input chars
        # (rough upper bound for cleanup/translation output) with a floor of 200.
        cap = max(200, len(raw_text) * 4)
        resp = client.chat.completions.create(
            model=deployment,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": raw_text},
            ],
            temperature=0.0,
            max_completion_tokens=cap,
        )
        return (resp.choices[0].message.content or "").strip()

    def refine(self, raw_text: str) -> str:
        stripped = raw_text.strip()
        # Short-input guard: small models hallucinate or truncate on tiny repetitive
        # inputs ("哈喽哈喽哈喽" 6 chars → +/- 哈喽). Skip refinement when the input
        # is short OR has very low character variety.
        if len(stripped) < 8 and len(set(stripped)) < 4:
            return stripped
        return self._complete(SYSTEM_PROMPT, raw_text)

    def translate(self, raw_text: str) -> str:
        stripped = raw_text.strip()
        # Short-input guard also applies to translate — "哈喽" alone is too thin
        # to translate meaningfully and small models tend to hallucinate on it.
        if len(stripped) < 8 and len(set(stripped)) < 4:
            return stripped
        return self._complete(TRANSLATE_SYSTEM_PROMPT, raw_text)


class GPT54Nano(_AzureChatRefine):
    name = "gpt-5.4-nano"
    label = "GPT-5.4 Nano (fastest/cheapest)"
    deployment_env = "AZURE_REFINE_GPT54_NANO_DEPLOYMENT"
    deployment_default = "gpt-5.4-nano"


class GPT54Mini(_AzureChatRefine):
    name = "gpt-5.4-mini"
    label = "GPT-5.4 Mini"
    deployment_env = "AZURE_REFINE_GPT54_MINI_DEPLOYMENT"
    deployment_default = "gpt-5.4-mini"


class ClaudeHaiku45(_AzureChatRefine):
    """Claude Haiku 4.5 via Azure AI Foundry — exposed through the OpenAI-compatible
    chat.completions endpoint on Foundry."""

    name = "claude-haiku-4-5"
    label = "Claude Haiku 4.5"
    deployment_env = "AZURE_REFINE_HAIKU_DEPLOYMENT"
    deployment_default = "claude-haiku-4-5"
