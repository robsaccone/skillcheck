"""Skill version detail view — metadata and full prompt content."""

import streamlit as st

from components import downshift_headings, strip_front_matter
from config import SKILLS_DIR


def render_skill_detail(skill_id: str, version: str, text: str, meta: dict):
    """Full-page detail view for a single skill version."""

    if st.button("\u2190 Back to skills", type="tertiary"):
        del st.session_state.selected_skill_version
        st.rerun()

    st.markdown(f"## {version}")

    # Version metadata from skill.json
    vmeta = meta.get("versions", {}).get(version, {})

    if vmeta:
        cols = st.columns([2, 1])
        with cols[0]:
            if vmeta.get("source"):
                st.markdown(f"**Source:** {vmeta['source']}")
            if vmeta.get("description"):
                st.markdown(f"**Description:** {vmeta['description']}")
            if vmeta.get("authors"):
                st.markdown(f"**Authors:** {vmeta['authors']}")
            if vmeta.get("license"):
                st.markdown(f"**License:** {vmeta['license']}")
        with cols[1]:
            if vmeta.get("url"):
                st.link_button("View source", vmeta["url"], icon=":material/open_in_new:")

    # File info
    lines = text.count("\n") + 1
    st.caption(f"`{version}.skill.md` — {lines} lines")

    st.divider()

    # Render as markdown
    shifted = downshift_headings(strip_front_matter(text))
    st.markdown(
        f'<div class="doc-preview">\n\n{shifted}\n\n</div>',
        unsafe_allow_html=True,
    )
