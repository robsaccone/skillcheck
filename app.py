"""Skillcheck — Streamlit Dashboard.

Entrypoint: page config, shared CSS, navigation, and sidebar.
Pages live in pages/ and are loaded via st.Page file paths.
"""

import streamlit as st
from pathlib import Path

# ---------------------------------------------------------------------------
# Page Config (must be first Streamlit call)
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Skillcheck",
    page_icon="\u26a1",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Shared CSS (runs on every rerun, applies to all pages)
# ---------------------------------------------------------------------------

css = (Path(__file__).parent / "app.css").read_text(encoding="utf-8")
st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)

ASSETS = Path(__file__).parent / "assets"
st.logo(
    str(ASSETS / "logo.svg"),
    size="large",
    icon_image=str(ASSETS / "logo_icon.svg"),
)

# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------

pg = st.navigation([
    st.Page("pages/skills.py", title="Skills", icon=":material/description:"),
    st.Page("pages/models.py", title="Models", icon=":material/smart_toy:"),
    st.Page("pages/judges.py", title="Judges", icon=":material/gavel:"),
    st.Page("pages/evaluate.py", title="Evaluate", icon=":material/play_circle:", default=True),
])

# with st.sidebar:
#     st.markdown("---")
#     st.caption("Byu Rob Saccone \u00b7 NexLaw Partners")

pg.run()
