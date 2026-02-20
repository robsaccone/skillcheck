"""Chat page — simple streaming conversation with any configured model."""

import streamlit as st

from models import MODEL_CONFIGS, get_available_models
from streaming import stream_response

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
