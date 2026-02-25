"""Chat page — data-aware conversation with tool calling via aisuite."""

import json

import aisuite as ai
import streamlit as st

from chat_tools import TOOLS, build_system_prompt
from models import MODEL_CONFIGS, get_available_models

available = get_available_models()

if not available:
    st.warning("No models available. Add API keys to your .env file.")
    st.stop()


# ---------------------------------------------------------------------------
# Model selector
# ---------------------------------------------------------------------------

# Providers confirmed working with aisuite tool calling.
# Google needs vertexai SDK (we use google-genai); Together models mostly
# don't support function calling.  Both can be added when support improves.
PROVIDER_MAP = {
    "anthropic": "anthropic",
    "openai": "openai",
}

model_keys = [
    k for k, cfg in available.items()
    if cfg["provider"] in PROVIDER_MAP
]

if not model_keys:
    st.warning("No models with supported providers available.")
    st.stop()

selected_model = st.sidebar.selectbox(
    "Chat Model",
    options=model_keys,
    format_func=lambda k: MODEL_CONFIGS[k]["display_name"],
    key="chat_model",
)

if st.sidebar.button("New Chat", use_container_width=True):
    st.session_state.chat_messages = []
    st.rerun()

cfg = MODEL_CONFIGS[selected_model]
provider_key = PROVIDER_MAP[cfg["provider"]]
aisuite_model = f"{provider_key}:{cfg['model_id']}"
model_name = cfg["display_name"]

st.markdown(f"## Ask {model_name}")


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
        # Replay tool activity
        for activity in msg.get("tool_activity", []):
            with st.expander(f"Tool: {activity['name']}", expanded=False):
                if activity.get("input"):
                    st.code(json.dumps(activity["input"], indent=2), language="json")
                if activity.get("result"):
                    st.code(activity["result"][:3000])
        if msg.get("content"):
            st.markdown(msg["content"])


# ---------------------------------------------------------------------------
# Chat input
# ---------------------------------------------------------------------------

if prompt := st.chat_input("Ask about your evaluation data"):
    st.session_state.chat_messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        # Build aisuite messages: system + history
        system_prompt = build_system_prompt()
        api_messages = [{"role": "system", "content": system_prompt}]
        for m in st.session_state.chat_messages:
            api_messages.append({"role": m["role"], "content": m["content"]})

        with st.spinner("Thinking..."):
            client = ai.Client()
            # OpenAI newer models require max_completion_tokens
            token_kwarg = (
                {"max_completion_tokens": 4096}
                if provider_key == "openai"
                else {"max_tokens": 4096}
            )
            try:
                response = client.chat.completions.create(
                    model=aisuite_model,
                    messages=api_messages,
                    tools=TOOLS,
                    max_turns=5,
                    **token_kwarg,
                )
            except Exception as e:
                st.error(f"Error: {e}")
                st.stop()

        # Extract tool activity from intermediate messages.
        # aisuite interleaves: assistant (with tool_calls) → tool (result) → ...
        # We pair each tool_call with the next matching tool result.
        tool_activity: list[dict] = []
        pending: dict[str, dict] = {}  # tool_call_id → activity dict
        intermediate = getattr(
            response.choices[0], "intermediate_messages", []
        )
        for im in intermediate:
            # Assistant messages contain tool_calls
            tool_calls = getattr(im, "tool_calls", None)
            if tool_calls:
                for tc in tool_calls:
                    fn = getattr(tc, "function", tc)
                    name = getattr(fn, "name", "unknown")
                    tc_id = getattr(tc, "id", name)
                    args_str = getattr(fn, "arguments", "{}")
                    try:
                        args = json.loads(args_str) if isinstance(args_str, str) else args_str
                    except (json.JSONDecodeError, TypeError):
                        args = {}
                    entry = {"name": name, "input": args, "result": ""}
                    tool_activity.append(entry)
                    pending[tc_id] = entry
                continue

            # Tool result messages
            role = getattr(im, "role", None) or (im.get("role") if isinstance(im, dict) else None)
            if role == "tool":
                tc_id = getattr(im, "tool_call_id", None) or (im.get("tool_call_id") if isinstance(im, dict) else None)
                raw = getattr(im, "content", None) or (im.get("content", "") if isinstance(im, dict) else "")
                # aisuite wraps tool results with json.dumps(), so unwrap
                content = raw
                if isinstance(raw, str):
                    try:
                        decoded = json.loads(raw)
                        if isinstance(decoded, str):
                            content = decoded
                    except (json.JSONDecodeError, TypeError):
                        pass
                content = str(content)
                if tc_id and tc_id in pending:
                    pending[tc_id]["result"] = content
                elif tool_activity:
                    # Fallback: match to the last entry without a result
                    for entry in reversed(tool_activity):
                        if not entry["result"]:
                            entry["result"] = content
                            break

        # Display tool activity
        for activity in tool_activity:
            with st.expander(f"Tool: {activity['name']}", expanded=False):
                if activity.get("input"):
                    st.code(json.dumps(activity["input"], indent=2), language="json")
                if activity.get("result"):
                    st.code(activity["result"][:3000])

        # Display final text
        final_text = response.choices[0].message.content or ""
        st.markdown(final_text)

        # Token usage + cost
        usage = getattr(response, "usage", None)
        if usage:
            in_tok = getattr(usage, "prompt_tokens", 0) or getattr(usage, "input_tokens", 0) or 0
            out_tok = getattr(usage, "completion_tokens", 0) or getattr(usage, "output_tokens", 0) or 0
            cost_in = cfg.get("cost_in", 0)
            cost_out = cfg.get("cost_out", 0)
            cost = in_tok * cost_in / 1_000_000 + out_tok * cost_out / 1_000_000
            st.caption(f"{in_tok:,} in / {out_tok:,} out — ${cost:.4f}")

    # Save to session state
    st.session_state.chat_messages.append({
        "role": "assistant",
        "content": final_text,
        "tool_activity": tool_activity,
    })
