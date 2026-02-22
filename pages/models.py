"""Models overview page — shows configured models and API key status."""

import streamlit as st

from models import MODEL_CONFIGS, get_available_models

st.markdown("## Models")

st.caption(
    "These are the available models for testing skills and judging results."
)


available = get_available_models()

table_data = []
for key, cfg in MODEL_CONFIGS.items():
    has_key = key in available
    icon = "\u2705" if has_key else "\u26aa"
    # Build defaults summary (temperature, max_tokens, reasoning_effort)
    defaults = []
    if cfg.get("temperature") is not None:
        defaults.append(f"temp {cfg['temperature']}")
    if cfg.get("max_tokens"):
        defaults.append(f"max {cfg['max_tokens']}")
    if cfg.get("reasoning_effort"):
        defaults.append(f"reasoning: {cfg['reasoning_effort']}")
    table_data.append({
        "Provider": cfg["provider"].capitalize(),
        "Model": f"{icon} {cfg['display_name']}",
        "Context": f"{cfg['context_k']}K",
        "Cost ($/1M tok)": f"${cfg['cost_in']:.2f} in / ${cfg['cost_out']:.2f} out",
        "Defaults": " · ".join(defaults) if defaults else "—",
    })

st.dataframe(table_data, width="stretch", hide_index=True)

if not available:
    st.warning("No API keys configured. Add keys to your .env file to enable models.")
