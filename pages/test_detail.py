"""Test document detail view — answer key summary and full document."""

import streamlit as st

from components import SEVERITY_EMOJI, SEVERITY_LABEL, downshift_headings


def render_test_detail(skill_id: str, doc_name: str, doc_text: str | None, ak_data: dict | None):
    """Full-page detail view for a test document and its answer key."""

    if st.button("\u2190 Back to skills", type="tertiary"):
        del st.session_state.selected_skill_test
        st.rerun()

    st.markdown(f"## {doc_name}")

    # --- Header metrics ---
    if ak_data:
        title = ak_data.get("doc_title", "")
        if title:
            st.caption(title)

        col1, col2, col3 = st.columns(3)
        col1.metric("Risk", ak_data.get("overall_risk", "—"))
        col2.metric("Recommendation", ak_data.get("expected_recommendation", "—"))
        col3.metric("Issues", len(ak_data.get("issues", [])))

        rationale = ak_data.get("overall_risk_rationale", "")
        if rationale:
            st.caption(rationale)

        scoring_notes = ak_data.get("scoring_notes", "")
        if scoring_notes:
            st.info(scoring_notes, icon=":material/target:")

    # --- Tabs ---
    tab_labels = []
    if doc_text:
        tab_labels.append("Document")
    if ak_data:
        tab_labels.append("Issues")
    if ak_data and ak_data.get("business_context"):
        tab_labels.append("Business Context")

    if not tab_labels:
        st.warning("No answer key or document found for this test.")
        return

    tabs = st.tabs(tab_labels)
    tab_idx = 0

    # Document tab
    if doc_text:
        with tabs[tab_idx]:
            shifted = downshift_headings(doc_text)
            st.markdown(
                f'<div class="doc-preview">\n\n{shifted}\n\n</div>',
                unsafe_allow_html=True,
            )
        tab_idx += 1

    # Issues tab
    if ak_data:
        with tabs[tab_idx]:
            for issue in ak_data.get("issues", []):
                sev = issue.get("severity", "M")
                section = issue.get("section", "")
                emoji = SEVERITY_EMOJI.get(sev, "")
                with st.expander(
                    f"{emoji} {issue['title']}  "
                    f"({SEVERITY_LABEL.get(sev, '1x')}, §{section})"
                ):
                    st.markdown(issue.get("description", ""))
                    rubric = issue.get("rubric", "")
                    if rubric:
                        st.caption(f"**Rubric:** {rubric}")

            # False positive traps
            traps = ak_data.get("false_positive_traps", [])
            if traps:
                st.divider()
                st.markdown("#### False Positive Traps")
                for trap in traps:
                    with st.expander(trap.get("provision", "")):
                        st.caption(trap.get("why_its_standard", ""))
        tab_idx += 1

    # Business Context tab
    if ak_data and ak_data.get("business_context"):
        with tabs[tab_idx]:
            st.markdown(ak_data["business_context"])
