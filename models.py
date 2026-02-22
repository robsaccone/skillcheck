"""Model configurations and API dispatch for Skillcheck."""

import json
import os
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Model Configs — loaded from models.json
# ---------------------------------------------------------------------------

MODEL_CONFIGS: dict[str, dict] = json.loads(
    (Path(__file__).parent / "models.json").read_text(encoding="utf-8")
)


def get_available_models():
    """Return model configs whose API keys are present in the environment."""
    available = {}
    for key, cfg in MODEL_CONFIGS.items():
        if os.environ.get(cfg["env_key"]):
            available[key] = cfg
    return available


# ---------------------------------------------------------------------------
# API Dispatch
# ---------------------------------------------------------------------------

_RETRYABLE_STATUS_CODES = {429, 529, 503}  # rate-limit, overloaded, unavailable
_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 5  # seconds


def call_model(
    provider: str,
    model_id: str,
    system: str,
    user: str,
    max_tokens: int = 16384,
    temperature: float | None = None,
    **kwargs,
) -> dict:
    """Call an LLM and return response data.

    Returns dict with keys: text, input_tokens, output_tokens, elapsed_seconds.
    Retries automatically on transient errors (429/503/529) with exponential backoff.
    """
    import sys

    dispatch = {
        "anthropic": lambda: _call_anthropic(model_id, system, user, max_tokens, temperature),
        "openai": lambda: _call_openai(model_id, system, user, max_tokens, temperature, **kwargs),
        "google": lambda: _call_google(model_id, system, user, max_tokens, temperature),
        "together": lambda: _call_together(model_id, system, user, max_tokens, temperature),
    }
    if provider not in dispatch:
        raise ValueError(f"Unknown provider: {provider}")

    start = time.time()
    last_err = None

    for attempt in range(_MAX_RETRIES):
        try:
            result = dispatch[provider]()
            result["elapsed_seconds"] = round(time.time() - start, 2)
            if not result.get("text"):
                raise RuntimeError(f"{provider}/{model_id} returned empty response text")
            return result
        except Exception as e:
            last_err = e
            status = getattr(e, "status_code", None) or getattr(e, "code", None)
            if status in _RETRYABLE_STATUS_CODES and attempt < _MAX_RETRIES - 1:
                # Use retry-after header if the API provides one, else exponential backoff
                headers = getattr(e, "response", None)
                retry_after = getattr(headers, "headers", {}).get("retry-after") if headers else None
                delay = float(retry_after) if retry_after else _RETRY_BASE_DELAY * (2 ** attempt)
                print(f"[retry] {provider}/{model_id}: {status} — retrying in {delay:.0f}s (attempt {attempt + 1}/{_MAX_RETRIES})", file=sys.stderr)
                time.sleep(delay)
            else:
                raise

    raise last_err  # unreachable, but keeps type checkers happy


def _call_anthropic(model_id: str, system: str, user: str, max_tokens: int, temperature: float | None = None) -> dict:
    import anthropic

    client = anthropic.Anthropic()
    params: dict = {
        "model": model_id,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    if temperature is not None:
        params["temperature"] = temperature
    response = client.messages.create(**params)
    return {
        "text": response.content[0].text,
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
    }


def _call_openai(model_id: str, system: str, user: str, max_tokens: int, temperature: float | None = None, **kwargs) -> dict:
    import openai

    client = openai.OpenAI()
    params: dict = {
        "model": model_id,
        "max_completion_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    if temperature is not None:
        params["temperature"] = temperature
    if kwargs.get("reasoning_effort"):
        params["reasoning_effort"] = kwargs["reasoning_effort"]
    response = client.chat.completions.create(**params)
    choice = response.choices[0]
    text = choice.message.content or getattr(choice.message, "reasoning_content", None) or ""
    return {
        "text": text,
        "input_tokens": response.usage.prompt_tokens,
        "output_tokens": response.usage.completion_tokens,
    }


def _call_google(model_id: str, system: str, user: str, max_tokens: int, temperature: float | None = None) -> dict:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
    config_kwargs: dict = {
        "system_instruction": system,
        "max_output_tokens": max_tokens,
    }
    if temperature is not None:
        config_kwargs["temperature"] = temperature
    response = client.models.generate_content(
        model=model_id,
        contents=user,
        config=types.GenerateContentConfig(**config_kwargs),
    )
    usage = response.usage_metadata
    return {
        "text": response.text,
        "input_tokens": getattr(usage, "prompt_token_count", 0),
        "output_tokens": getattr(usage, "candidates_token_count", 0),
    }


def _call_together(model_id: str, system: str, user: str, max_tokens: int, temperature: float | None = None) -> dict:
    import openai

    client = openai.OpenAI(
        api_key=os.environ["TOGETHER_API_KEY"],
        base_url="https://api.together.xyz/v1",
    )
    params: dict = {
        "model": model_id,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    if temperature is not None:
        params["temperature"] = temperature
    response = client.chat.completions.create(**params)
    choice = response.choices[0]
    text = choice.message.content or getattr(choice.message, "reasoning_content", None) or ""
    usage = response.usage
    return {
        "text": text,
        "input_tokens": getattr(usage, "prompt_tokens", 0),
        "output_tokens": getattr(usage, "completion_tokens", 0),
    }
