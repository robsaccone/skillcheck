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
    table_data.append({
        "Model": cfg["display_name"],
        "Provider": cfg["provider"].capitalize(),
        "Model ID": f"{icon} {cfg['model_id']}",
        "Context": f"{cfg['context_k']}K",
        "Cost ($/1M tok)": f"${cfg['cost_in']:.2f} in / ${cfg['cost_out']:.2f} out",
    })

st.dataframe(table_data, width="stretch", hide_index=True)

if not available:
    st.warning("No API keys configured. Add keys to your .env file to enable models.")
