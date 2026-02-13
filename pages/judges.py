"""Judges page — select up to two LLM judges for evaluation grading."""

import streamlit as st

from models import MODEL_CONFIGS, get_available_models

st.markdown("## Judges")

available = get_available_models()

if not available:
    st.warning("No models available. Add API keys to your .env file.")
    st.stop()

model_keys = list(available.keys())

st.caption(
    "Select one or two models to act as 'judges' that will evaluate results based on provided answer keys. \n\n"
    "When two are selected, results are compared for agreement or divergence."
)

col1, col2 = st.columns(2)

with col1:
    st.markdown("**Judge 1**")
    judge1 = st.selectbox(
        "Judge 1",
        options=model_keys,
        format_func=lambda k: MODEL_CONFIGS[k]["display_name"],
        label_visibility="collapsed",
        key="judge1_select",
    )

with col2:
    st.markdown("**Judge 2** (optional)")
    judge2_options = [None] + [k for k in model_keys if k != judge1]
    judge2 = st.selectbox(
        "Judge 2",
        options=judge2_options,
        format_func=lambda k: MODEL_CONFIGS[k]["display_name"] if k else "— None —",
        label_visibility="collapsed",
        key="judge2_select",
    )

# Persist selections in session_state for other pages
st.session_state.judge1 = judge1
st.session_state.judge2 = judge2

st.divider()

st.markdown("**Judge Instructions**")
judge_prompt = st.text_area(
    "Judge System Prompt",
    placeholder="Enter the system prompt that will be sent to the judge model(s)...",
    height=300,
    label_visibility="collapsed",
    key="judge_system_prompt",
)
