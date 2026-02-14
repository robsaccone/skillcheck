"""Chat page — simple streaming conversation with any configured model."""

import streamlit as st

from models import MODEL_CONFIGS, get_available_models

available = get_available_models()

if not available:
    st.warning("No models available. Add API keys to your .env file.")
    st.stop()

model_keys = list(available.keys())

selected_model = st.sidebar.selectbox(
    "Chat Model",
    options=model_keys,
    format_func=lambda k: MODEL_CONFIGS[k]["display_name"],
    key="chat_model",
)

model_name = MODEL_CONFIGS[selected_model]["display_name"]
st.markdown(f"## Chat with {model_name}")

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = []

# Clear history when model changes
if st.session_state.get("chat_last_model") != selected_model:
    st.session_state.chat_messages = []
    st.session_state.chat_last_model = selected_model

# Display chat history
for msg in st.session_state.chat_messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])


# ---------------------------------------------------------------------------
# Streaming helpers (one per provider)
# ---------------------------------------------------------------------------

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
    import os
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
    import os
    import google.generativeai as genai
    genai.configure(api_key=os.environ["GOOGLE_API_KEY"])
    model = genai.GenerativeModel(model_name=model_id)
    # Convert to Gemini format: alternating user/model turns
    history = []
    for msg in messages[:-1]:
        role = "user" if msg["role"] == "user" else "model"
        history.append({"role": role, "parts": [msg["content"]]})
    chat = model.start_chat(history=history)
    response = chat.send_message(messages[-1]["content"], stream=True)
    for chunk in response:
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


# ---------------------------------------------------------------------------
# Chat input
# ---------------------------------------------------------------------------

if prompt := st.chat_input("Send a message"):
    st.session_state.chat_messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        api_messages = [
            {"role": m["role"], "content": m["content"]}
            for m in st.session_state.chat_messages
        ]
        response = st.write_stream(stream_response(selected_model, api_messages))

    st.session_state.chat_messages.append({"role": "assistant", "content": response})
