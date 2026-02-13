"""Model configurations and API dispatch for Skillcheck."""

import os
import time

from dotenv import load_dotenv

load_dotenv(override=True)

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
    },
    "claude-haiku-4-5": {
        "provider": "anthropic",
        "model_id": "claude-haiku-4-5",
        "display_name": "Claude Haiku 4.5",
        "env_key": "ANTHROPIC_API_KEY",
    },
    # OpenAI
    "gpt-5.2": {
        "provider": "openai",
        "model_id": "gpt-5.2",
        "display_name": "GPT-5.2",
        "env_key": "OPENAI_API_KEY",
    },
    "gpt-5-nano": {
        "provider": "openai",
        "model_id": "gpt-5-nano",
        "display_name": "GPT-5 Nano",
        "env_key": "OPENAI_API_KEY",
    },
    # Google
    "gemini-3-pro": {
        "provider": "google",
        "model_id": "gemini-3-pro-preview",
        "display_name": "Gemini 3 Pro",
        "env_key": "GOOGLE_API_KEY",
    },
    "gemini-3-flash": {
        "provider": "google",
        "model_id": "gemini-3-flash-preview",
        "display_name": "Gemini 3 Flash",
        "env_key": "GOOGLE_API_KEY",
    },
    # Together (dark horses)
    "deepseek-r1": {
        "provider": "together",
        "model_id": "deepseek-ai/DeepSeek-R1",
        "display_name": "DeepSeek R1",
        "env_key": "TOGETHER_API_KEY",
    },
    "qwen3-235b": {
        "provider": "together",
        "model_id": "Qwen/Qwen3-235B-A22B-Thinking-2507",
        "display_name": "Qwen3 235B",
        "env_key": "TOGETHER_API_KEY",
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

def call_model(
    provider: str,
    model_id: str,
    system: str,
    user: str,
    max_tokens: int = 8192,
) -> dict:
    """Call an LLM and return response data.

    Returns dict with keys: text, input_tokens, output_tokens, elapsed_seconds.
    """
    start = time.time()

    if provider == "anthropic":
        result = _call_anthropic(model_id, system, user, max_tokens)
    elif provider == "openai":
        result = _call_openai(model_id, system, user, max_tokens)
    elif provider == "google":
        result = _call_google(model_id, system, user, max_tokens)
    elif provider == "together":
        result = _call_together(model_id, system, user, max_tokens)
    else:
        raise ValueError(f"Unknown provider: {provider}")

    result["elapsed_seconds"] = round(time.time() - start, 2)
    return result


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


def _call_openai(model_id: str, system: str, user: str, max_tokens: int) -> dict:
    import openai

    client = openai.OpenAI()
    response = client.chat.completions.create(
        model=model_id,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    choice = response.choices[0]
    return {
        "text": choice.message.content,
        "input_tokens": response.usage.prompt_tokens,
        "output_tokens": response.usage.completion_tokens,
    }


def _call_google(model_id: str, system: str, user: str, max_tokens: int) -> dict:
    import google.generativeai as genai

    genai.configure(api_key=os.environ["GOOGLE_API_KEY"])
    model = genai.GenerativeModel(
        model_name=model_id,
        system_instruction=system,
    )
    response = model.generate_content(
        user,
        generation_config=genai.types.GenerationConfig(
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
    usage = response.usage
    return {
        "text": choice.message.content,
        "input_tokens": getattr(usage, "prompt_tokens", 0),
        "output_tokens": getattr(usage, "completion_tokens", 0),
    }
