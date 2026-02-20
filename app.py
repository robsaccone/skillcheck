"""Skillcheck — Streamlit Dashboard.

Entrypoint: page config, shared CSS, navigation, and sidebar.
Pages live in pages/ and are loaded via st.Page file paths.
"""

import streamlit as st
from datetime import datetime
from pathlib import Path

from config import RESULTS_DIR

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
# Sidebar — recent eval runs
# ---------------------------------------------------------------------------

if pg.title != "Chat" and RESULTS_DIR.exists():
    # Group result files into runs by (skill_id, doc_name), track most recent mtime
    run_map: dict[tuple[str, str], float] = {}
    for rf in RESULTS_DIR.rglob("*.json"):
        parts = rf.stem.split("__", 1)
        if len(parts) != 2 or rf.parent.parent.parent != RESULTS_DIR:
            continue
        doc_name = parts[1]
        skill_id = rf.parent.parent.name
        key = (skill_id, doc_name)
        mtime = rf.stat().st_mtime
        if key not in run_map or mtime > run_map[key]:
            run_map[key] = mtime

    if run_map:
        recent_runs = sorted(run_map.items(), key=lambda x: x[1], reverse=True)[:8]
        st.sidebar.divider()
        st.sidebar.caption("Recent Runs")
        for (skill_id, doc_name), mtime in recent_runs:
            dt = datetime.fromtimestamp(mtime)
            time_str = f"{dt.month}/{dt.day} {dt.strftime('%I:%M %p').lower()}"
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
