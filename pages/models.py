"""Models overview page — shows configured models and API key status."""

import streamlit as st

from models import MODEL_CONFIGS, get_available_models

st.markdown("## Models")

available = get_available_models()

table_data = []
for key, cfg in MODEL_CONFIGS.items():
    has_key = key in available
    table_data.append({
        "Model": cfg["display_name"],
        "Provider": cfg["provider"].capitalize(),
        "Model ID": cfg["model_id"],
        "API Key Env": cfg["env_key"],
        "Status": "\u2705 Available" if has_key else "\u26aa Unavailable",
    })

st.dataframe(table_data, width="stretch", hide_index=True)

if not available:
    st.warning("No API keys configured. Add keys to your .env file to enable models.")
