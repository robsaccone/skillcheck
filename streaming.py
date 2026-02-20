"""Shared streaming helpers for chat-based features.

Extracted from pages/chat.py so they can be reused without triggering
Streamlit page-level side effects.
"""

import os

from models import MODEL_CONFIGS


def _stream_anthropic(model_id: str, messages: list):
    import anthropic
    client = anthropic.Anthropic()
    with client.messages.stream(
        model=model_id,
        max_tokens=4096,
        messages=messages,
    ) as stream:
        for text in stream.text_stream:
            yield text


def _stream_openai(model_id: str, messages: list, base_url: str | None = None, api_key_env: str = "OPENAI_API_KEY"):
    import openai
    kwargs = {}
    if base_url:
        kwargs["base_url"] = base_url
        kwargs["api_key"] = os.environ[api_key_env]
    client = openai.OpenAI(**kwargs)
    stream = client.chat.completions.create(
        model=model_id,
        messages=[{"role": "system", "content": "You are a helpful assistant."}, *messages],
        stream=True,
    )
    for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        if delta.content:
            yield delta.content


def _stream_google(model_id: str, messages: list):
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
    # Build contents: alternating user/model turns
    contents = []
    for msg in messages:
        role = "user" if msg["role"] == "user" else "model"
        contents.append(types.Content(role=role, parts=[types.Part(text=msg["content"])]))
    for chunk in client.models.generate_content_stream(
        model=model_id,
        contents=contents,
    ):
        if chunk.text:
            yield chunk.text


def stream_response(model_key: str, messages: list):
    """Route to the correct streaming provider."""
    cfg = MODEL_CONFIGS[model_key]
    provider = cfg["provider"]
    model_id = cfg["model_id"]

    if provider == "anthropic":
        yield from _stream_anthropic(model_id, messages)
    elif provider == "openai":
        yield from _stream_openai(model_id, messages)
    elif provider == "google":
        yield from _stream_google(model_id, messages)
    elif provider == "together":
        yield from _stream_openai(
            model_id, messages,
            base_url="https://api.together.xyz/v1",
            api_key_env="TOGETHER_API_KEY",
        )
