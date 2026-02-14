"""Skills Library page — browse skills, versions, docs, and answer keys."""

import streamlit as st

from config import SKILLS_DIR
from engine import (
    discover_skills,
    list_skill_versions,
    load_skill_version,
    list_test_docs,
    load_test_doc,
    load_answer_key,
)
from components import severity_badge_html, severity_prefix

st.markdown("## Skills Library")

st.caption(
    "Skills can be added to the `skills/` directory and are organized by task type."
)


skills = discover_skills()
if not skills:
    st.info("No skills found. Add skill directories with skill.json to the skills/ folder.")
    st.stop()

for skill in skills:
    skill_id = skill["skill_id"]
    with st.expander(
        f"**{skill['display_name']}** — {skill.get('description', '')}  "
        f"({skill['version_count']} versions, {skill['doc_count']} docs)",
        expanded=False,
    ):
        col_ver, col_doc, col_ak = st.columns(3, gap="large")

        # Versions
        with col_ver:
            st.markdown("#### Versions")
            versions = list_skill_versions(skill_id)
            if versions:
                for v in versions:
                    path = SKILLS_DIR / skill_id / f"{v}.skill.md"
                    size = path.stat().st_size if path.exists() else 0
                    size_kb = size / 1024

                    text = load_skill_version(skill_id, v)
                    with st.expander(f"`{v}.skill.md` ({size_kb:.1f} KB)", expanded=False):
                        if text:
                            st.code(text, language="markdown", line_numbers=True)
                        else:
                            st.warning("File not found")
            else:
                st.caption("No versions found.")

        # Test Documents
        with col_doc:
            st.markdown("#### Test Documents")
            docs = list_test_docs(skill_id)
            if docs:
                for doc_name in docs:
                    doc_text = load_test_doc(skill_id, doc_name)
                    with st.expander(f"`{doc_name}.md`", expanded=False):
                        if doc_text:
                            st.markdown(doc_text)
                        else:
                            st.warning("File not found")
            else:
                st.caption("No test documents found.")

        # Answer Keys
        with col_ak:
            st.markdown("#### Answer Keys")
            ak_dir = SKILLS_DIR / skill_id / "answer_keys"
            if ak_dir.exists():
                ak_files = sorted(ak_dir.glob("*.json"))
                if ak_files:
                    for ak_path in ak_files:
                        ak_name = ak_path.stem
                        ak_data = load_answer_key(skill_id, ak_name)
                        with st.expander(f"`{ak_name}.json`", expanded=False):
                            if ak_data:
                                st.markdown(
                                    f"**Overall Risk:** {severity_badge_html(ak_data.get('overall_risk', 'N/A'))}",
                                    unsafe_allow_html=True,
                                )
                                st.caption(ak_data.get("overall_risk_rationale", ""))

                                for issue in ak_data.get("issues", []):
                                    sev = issue.get("severity", "MODERATE")
                                    st.markdown(
                                        f"{severity_prefix(sev)} — **{issue['id']}**: {issue['title']}",
                                    )
                            else:
                                st.warning("Could not load answer key")
                else:
                    st.caption("No answer keys found.")
            else:
                st.caption("No answer keys directory.")
