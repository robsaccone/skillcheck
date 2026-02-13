"""Shared UI helpers, constants, and rendering functions for Skillcheck."""

import streamlit as st

from engine import load_answer_key

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SEVERITY_EMOJI = {"CRITICAL": "\U0001f534", "HIGH": "\U0001f7e0", "MODERATE": "\U0001f535", "LOW": "\u26aa"}

TIER_LABEL = {"must_catch": "3\u00d7", "should_catch": "2\u00d7", "nice_to_catch": "1\u00d7"}


# ---------------------------------------------------------------------------
# Badge & chip helpers
# ---------------------------------------------------------------------------

def severity_badge_html(severity: str) -> str:
    s = severity.lower()
    return f'<span class="badge-{s}">{severity}</span>'


def severity_prefix(severity: str) -> str:
    return SEVERITY_EMOJI.get(severity.upper(), "") + " " + severity


def detection_chip(label: str, detected: bool) -> str:
    cls = "chip-hit" if detected else "chip-miss"
    icon = "\u2705" if detected else "\u274c"
    return f'<span class="{cls}">{icon} {label}</span>'


# ---------------------------------------------------------------------------
# Result detail panel
# ---------------------------------------------------------------------------

def render_result_detail(result: dict, skill_id: str, doc_name: str):
    """Render full-width detail panel: stats left, response right."""
    scores = result.get("auto_scores", {})
    pct = scores.get("weighted_pct", 0)

    left, right = st.columns([1, 2])

    with left:
        mc1, mc2 = st.columns(2)
        mc1.metric("Weighted", f"{pct:.1f}%")
        mc2.metric("Issues", f"{scores.get('total_found', 0)}/{scores.get('total_possible', 0)}")

        mc3, mc4 = st.columns(2)
        mc3.metric("Must-Catch", f"{scores.get('must_catch', {}).get('found', 0)}/{scores.get('must_catch', {}).get('total', 0)}")
        mc4.metric("Time", f"{result.get('elapsed_seconds', 0):.1f}s")

        st.caption(
            f"Tokens: {result.get('input_tokens', 0):,} in / "
            f"{result.get('output_tokens', 0):,} out"
        )

        answer_key = load_answer_key(skill_id, doc_name)
        if answer_key and scores.get("issues_detected"):
            st.markdown("**Detection**")
            chips_html = ""
            for issue in answer_key.get("issues", []):
                iid = issue["id"]
                detected = scores["issues_detected"].get(iid, False)
                chips_html += detection_chip(f"{iid}: {issue['title']}", detected) + " "
            for meta in answer_key.get("meta_issues", []):
                mid = meta["id"]
                detected = scores.get("meta_issues_detected", {}).get(mid, False)
                chips_html += detection_chip(f"{mid}: {meta['title']}", detected) + " "
            st.markdown(chips_html, unsafe_allow_html=True)

    with right:
        st.markdown("**Response**")
        st.markdown(result.get("response_text", ""))
