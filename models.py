"""Model configurations and API dispatch for Skillcheck."""

import os
import time

# ---------------------------------------------------------------------------
# Model Configs
# ---------------------------------------------------------------------------

MODEL_CONFIGS = {
    # Anthropic
    "claude-opus-4-6": {
        "provider": "anthropic",
        "model_id": "claude-opus-4-6",
        "display_name": "Claude Opus 4.6",
        "env_key": "ANTHROPIC_API_KEY",
        "cost_in": 5.00,
        "cost_out": 25.00,
        "context_k": 200,
    },
    "claude-haiku-4-5": {
        "provider": "anthropic",
        "model_id": "claude-haiku-4-5",
        "display_name": "Claude Haiku 4.5",
        "env_key": "ANTHROPIC_API_KEY",
        "cost_in": 1.00,
        "cost_out": 5.00,
        "context_k": 200,
    },
    # OpenAI
    "gpt-5.2": {
        "provider": "openai",
        "model_id": "gpt-5.2",
        "display_name": "GPT-5.2",
        "env_key": "OPENAI_API_KEY",
        "cost_in": 1.75,
        "cost_out": 14.00,
        "context_k": 400,
    },
    "gpt-5-nano": {
        "provider": "openai",
        "model_id": "gpt-5-nano",
        "display_name": "GPT-5 Nano",
        "env_key": "OPENAI_API_KEY",
        "cost_in": 0.05,
        "cost_out": 0.40,
        "context_k": 400,
        "reasoning_effort": "low",
    },
    # Google
    "gemini-3-pro": {
        "provider": "google",
        "model_id": "gemini-3-pro-preview",
        "display_name": "Gemini 3 Pro",
        "env_key": "GOOGLE_API_KEY",
        "cost_in": 2.00,
        "cost_out": 12.00,
        "context_k": 1000,
    },
    "gemini-3.1-pro": {
        "provider": "google",
        "model_id": "gemini-3.1-pro-preview",
        "display_name": "Gemini 3.1 Pro",
        "env_key": "GOOGLE_API_KEY",
        "cost_in": 2.00,
        "cost_out": 12.00,
        "context_k": 1000,
    },
    "gemini-3-flash": {
        "provider": "google",
        "model_id": "gemini-3-flash-preview",
        "display_name": "Gemini 3 Flash",
        "env_key": "GOOGLE_API_KEY",
        "cost_in": 0.50,
        "cost_out": 3.00,
        "context_k": 1000,
    },
    # Together (dark horses)
    "deepseek-r1": {
        "provider": "together",
        "model_id": "deepseek-ai/DeepSeek-R1",
        "display_name": "DeepSeek R1",
        "env_key": "TOGETHER_API_KEY",
        "cost_in": 3.00,
        "cost_out": 7.00,
        "context_k": 164,
    },
    "qwen3-235b": {
        "provider": "together",
        "model_id": "Qwen/Qwen3-235B-A22B-Thinking-2507",
        "display_name": "Qwen3 235B",
        "env_key": "TOGETHER_API_KEY",
        "cost_in": 0.65,
        "cost_out": 3.00,
        "context_k": 262,
    },
}


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
    **kwargs,
) -> dict:
    """Call an LLM and return response data.

    Returns dict with keys: text, input_tokens, output_tokens, elapsed_seconds.
    Retries automatically on transient errors (429/503/529) with exponential backoff.
    """
    import sys

    dispatch = {
        "anthropic": lambda: _call_anthropic(model_id, system, user, max_tokens),
        "openai": lambda: _call_openai(model_id, system, user, max_tokens, **kwargs),
        "google": lambda: _call_google(model_id, system, user, max_tokens),
        "together": lambda: _call_together(model_id, system, user, max_tokens),
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


def _call_anthropic(model_id: str, system: str, user: str, max_tokens: int) -> dict:
    import anthropic

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=model_id,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return {
        "text": response.content[0].text,
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
    }


def _call_openai(model_id: str, system: str, user: str, max_tokens: int, **kwargs) -> dict:
    import openai

    client = openai.OpenAI()
    params = {
        "model": model_id,
        "max_completion_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
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


def _call_google(model_id: str, system: str, user: str, max_tokens: int) -> dict:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
    response = client.models.generate_content(
        model=model_id,
        contents=user,
        config=types.GenerateContentConfig(
            system_instruction=system,
            max_output_tokens=max_tokens,
        ),
    )
    usage = response.usage_metadata
    return {
        "text": response.text,
        "input_tokens": getattr(usage, "prompt_token_count", 0),
        "output_tokens": getattr(usage, "candidates_token_count", 0),
    }


def _call_together(model_id: str, system: str, user: str, max_tokens: int) -> dict:
    import openai

    client = openai.OpenAI(
        api_key=os.environ["TOGETHER_API_KEY"],
        base_url="https://api.together.xyz/v1",
    )
    response = client.chat.completions.create(
        model=model_id,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    choice = response.choices[0]
    text = choice.message.content or getattr(choice.message, "reasoning_content", None) or ""
    usage = response.usage
    return {
        "text": text,
        "input_tokens": getattr(usage, "prompt_tokens", 0),
        "output_tokens": getattr(usage, "completion_tokens", 0),
    }
