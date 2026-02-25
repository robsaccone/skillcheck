"""Skillcheck — Streamlit Dashboard.

Entrypoint: page config, shared CSS, navigation, and sidebar.
Pages live in pages/ and are loaded via st.Page file paths.
"""

import streamlit as st
from datetime import datetime
from pathlib import Path

import db
from config import DB_PATH, RESULTS_DIR

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

pg = st.navigation({
    "": [
        st.Page("pages/home.py", title="About", icon=":material/home:", default=True),
    ],
    " ": [
        st.Page("pages/skills.py", title="Skills", icon=":material/description:"),
        st.Page("pages/models.py", title="Models", icon=":material/smart_toy:"),
        st.Page("pages/judges.py", title="Judges", icon=":material/gavel:"),
        st.Page("pages/evaluate.py", title="Evaluate", icon=":material/play_circle:"),
        st.Page("pages/chat.py", title="Chat", icon=":material/chat:"),
    ],
})

# ---------------------------------------------------------------------------
# Migration — import legacy JSON results into DuckDB on first run
# ---------------------------------------------------------------------------

if not DB_PATH.exists() and RESULTS_DIR.exists():
    count = db.migrate_json_results(RESULTS_DIR)
    if count:
        st.toast(f"Migrated {count} results from JSON to DuckDB.")

# ---------------------------------------------------------------------------
# Sidebar — recent eval runs
# ---------------------------------------------------------------------------

if pg.title != "Chat":
    recent_runs = db.get_recent_runs(limit=8)
    if recent_runs:
        st.sidebar.divider()
        st.sidebar.caption("Recent Runs")
        for run in recent_runs:
            skill_id = run["skill_id"]
            doc_name = run["doc_name"]
            ts = run["timestamp"]
            if hasattr(ts, "strftime"):
                dt = ts
            else:
                try:
                    dt = datetime.fromisoformat(str(ts))
                except (ValueError, TypeError):
                    dt = None
            time_str = f"{dt.month}/{dt.day} {dt.strftime('%I:%M %p').lower()}" if dt else ""
            label = f":material/history: {skill_id} / {doc_name}  \n{time_str}"
            if st.sidebar.button(
                label,
                key=f"run_{skill_id}_{doc_name}",
                use_container_width=True,
                type="tertiary",
            ):
                st.session_state.viewer_skill = skill_id
                st.session_state.viewer_doc = doc_name
                st.session_state.viewer_mode = True
                st.session_state.pop("selected_result", None)
                st.session_state.pop("selected_result_ctx", None)
                st.switch_page("pages/evaluate.py")

pg.run()
