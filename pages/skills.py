"""Skills Library page — browse skills, versions, and tests."""

import streamlit as st

from config import SKILLS_DIR
from engine import (
    discover_skills,
    list_skill_versions,
    load_skill_version,
    load_skill_meta,
    list_test_docs,
    load_test_doc,
    load_answer_key,
)
from components import severity_prefix
from pages.skill_detail import render_skill_detail
from pages.test_detail import render_test_detail

# ---------------------------------------------------------------------------
# Detail views (selected version or test)
# ---------------------------------------------------------------------------

sel = st.session_state.get("selected_skill_version")
if sel:
    ctx = st.session_state.get("selected_skill_ctx", {})
    skill_id = ctx.get("skill_id", "")
    version = ctx.get("version", "")
    meta = load_skill_meta(skill_id) or {}
    text = load_skill_version(skill_id, version)
    if text is not None:
        render_skill_detail(skill_id, version, text, meta)
        st.stop()
    else:
        del st.session_state.selected_skill_version
        st.rerun()

sel_test = st.session_state.get("selected_skill_test")
if sel_test:
    ctx = st.session_state.get("selected_skill_test_ctx", {})
    skill_id = ctx.get("skill_id", "")
    doc_name = ctx.get("doc_name", "")
    doc_text = load_test_doc(skill_id, doc_name)
    ak_data = load_answer_key(skill_id, doc_name)
    if doc_text is not None or ak_data is not None:
        render_test_detail(skill_id, doc_name, doc_text, ak_data)
        st.stop()
    else:
        del st.session_state.selected_skill_test
        st.rerun()

# ---------------------------------------------------------------------------
# Main listing
# ---------------------------------------------------------------------------

st.markdown("## Skills Library")

skills = discover_skills()
if not skills:
    st.info("No skills found. Add skill directories with `skill.json` to the `skills/` folder.")
    st.stop()

for skill in skills:
    skill_id = skill["skill_id"]
    meta = load_skill_meta(skill_id) or {}
    version_meta = meta.get("versions", {})
    versions = list_skill_versions(skill_id)
    docs = list_test_docs(skill_id)

    with st.expander(
        f"**{skill['display_name']}** — {skill.get('description', '')}  "
        f"({len(versions)} versions, {len(docs)} tests)",
        expanded=True,
    ):
        col_ver, col_tests = st.columns(2, gap="large")

        # --- Versions ---
        with col_ver:
            st.markdown("#### Versions")
            if versions:
                for v in versions:
                    vmeta = version_meta.get(v, {})
                    source = vmeta.get("source", "")
                    desc = vmeta.get("description", "")

                    label = vmeta.get("display_name", v)
                    detail = source or desc or ""
                    c_btn, c_info = st.columns([1, 3], vertical_alignment="center")
                    with c_btn:
                        if st.button(
                            f":material/description: {label}",
                            key=f"skill_ver_{skill_id}_{v}",
                            type="tertiary",
                        ):
                            st.session_state.selected_skill_version = True
                            st.session_state.selected_skill_ctx = {
                                "skill_id": skill_id,
                                "version": v,
                            }
                            st.rerun()
                    with c_info:
                        if detail:
                            st.caption(detail)
            else:
                st.caption("No versions found.")

        # --- Tests ---
        with col_tests:
            st.markdown("#### Tests")
            if docs:
                for doc_name in docs:
                    ak_data = load_answer_key(skill_id, doc_name)
                    risk = ak_data.get("overall_risk", "") if ak_data else ""
                    rec = ak_data.get("expected_recommendation", "") if ak_data else ""
                    issue_count = len(ak_data.get("issues", [])) if ak_data else 0

                    c_btn, c_info = st.columns([2, 3], vertical_alignment="center")
                    with c_btn:
                        if st.button(
                            f":material/quiz: {doc_name}",
                            key=f"skill_test_{skill_id}_{doc_name}",
                            type="tertiary",
                        ):
                            st.session_state.selected_skill_test = True
                            st.session_state.selected_skill_test_ctx = {
                                "skill_id": skill_id,
                                "doc_name": doc_name,
                            }
                            st.rerun()
                    with c_info:
                        if ak_data:
                            st.caption(f"{risk} · {rec} · {issue_count} issues")
                        else:
                            st.caption("No answer key")
            else:
                st.caption("No tests found.")
