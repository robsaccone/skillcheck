"""Result detail view — summary, issue checklist, and full response."""

import streamlit as st

from engine import load_answer_key
from judge import detect_self_enhancement_risk
from models import MODEL_CONFIGS
from components import SEVERITY_LABEL, downshift_headings, est_cost, fmt_time


def render_result_page(result: dict, version: str, model_key: str, skill_id: str, doc_name: str):
    """Full-page detail view for a single evaluation result."""
    model_name = MODEL_CONFIGS.get(model_key, {}).get("display_name", model_key)

    if st.button("\u2190 Back to results", type="tertiary"):
        del st.session_state.selected_result
        st.rerun()

    st.markdown(f"## {version} x {model_name}")

    # Run metadata
    timestamp = result.get("timestamp", "")
    if timestamp:
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(timestamp)
            run_time = dt.strftime("%b %d, %Y at %I:%M %p")
        except (ValueError, TypeError):
            run_time = timestamp
    else:
        run_time = "Unknown"

    st.caption(f"{skill_id} \u00b7 {doc_name} \u00b7 Run {run_time}")

    judge = result.get("judge_scores")
    answer_key = load_answer_key(skill_id, doc_name)

    # Self-enhancement bias warning
    if judge:
        judge_model = judge.get("judge_model", "")
        # Handle panel format (joined with +)
        judge_models = judge_model.split("+") if "+" in judge_model else [judge_model]
        for jm in judge_models:
            warning = detect_self_enhancement_risk(jm, model_key)
            if warning:
                st.warning(warning)

    tab_summary, tab_issues, tab_response = st.tabs(["Summary", "Issues", "Response"])

    # ------------------------------------------------------------------
    # Summary tab
    # ------------------------------------------------------------------
    with tab_summary:
        secs = result.get("elapsed_seconds", 0)
        cost = est_cost(result, model_key)
        in_tok = result.get("input_tokens", 0)
        out_tok = result.get("output_tokens", 0)
        total_tok = in_tok + out_tok

        if judge:
            score_pct = judge.get("composite_score", 0) * 100
            issues_found = judge.get("issues_found", 0)
            issues_total = judge.get("issues_total", 0)
            rec_match = judge.get("recommendation_match", False)
            fp_count = judge.get("false_positive_count", 0)

            mc1, mc2, mc3, mc4 = st.columns(4)
            mc1.metric("Score", f"{score_pct:.0f}%")
            mc2.metric("Recommendation", "\u2713 Correct" if rec_match else "\u2717 Wrong")
            mc3.metric("Issues Found", f"{issues_found}/{issues_total}")
            mc4.metric("False Positives", str(fp_count))

            mc5, mc6, mc7, mc8 = st.columns(4)
            mc5.metric("Time", fmt_time(secs))
            mc6.metric("Tokens", f"{total_tok:,}")
            mc7.metric("Est. Cost", f"${cost:.2f}")
            hit_rate = judge.get("weighted_hit_rate", 0)
            mc8.metric("Weighted Hit Rate", f"{hit_rate:.0f}%")

            # Panel details
            panel_size = judge.get("panel_size", 1)
            if panel_size > 1:
                panel_judges = judge.get("panel_judges", [])
                panel_scores = judge.get("panel_scores", [])
                panel_names = [
                    MODEL_CONFIGS.get(k, {}).get("display_name", k)
                    for k in panel_judges
                ]
                st.caption(
                    f"Panel of {panel_size} judges: {', '.join(panel_names)} "
                    "(scores aggregated via majority vote)"
                )
                if panel_scores:
                    score_parts = []
                    for ps in panel_scores:
                        jn = MODEL_CONFIGS.get(ps["judge_model"], {}).get("display_name", ps["judge_model"])
                        sc = ps["composite_score"] * 100
                        score_parts.append(f"{jn}: {sc:.0f}%")
                    st.caption("Individual scores: " + " | ".join(score_parts))
        else:
            mc1, mc2, mc3, mc4 = st.columns(4)
            mc1.metric("Score", "Not judged")
            mc2.metric("Time", fmt_time(secs))
            mc3.metric("Tokens", f"{total_tok:,}")
            mc4.metric("Est. Cost", f"${cost:.2f}")

    # ------------------------------------------------------------------
    # Issues tab — checklist with reasoning
    # ------------------------------------------------------------------
    with tab_issues:
        if not answer_key:
            st.info("No answer key available for this document.")
            return

        judge_issues = judge.get("issues", {}) if judge else {}
        reasoning = judge.get("reasoning", {}) if judge else {}

        # Recommendation match at top
        if judge:
            rec = judge.get("recommendation", {})
            model_said = rec.get("model_said", "?")
            correct = rec.get("correct", "?")
            match = rec.get("match", False)
            icon = "\u2713" if match else "\u2717"
            st.markdown(
                f"**{icon} Recommendation:** Model said **{model_said}**, "
                f"correct was **{correct}** (+{10 if match else 0} pts)"
            )
            # Show recommendation reasoning if available
            rec_reasoning = reasoning.get("recommendation")
            if rec_reasoning:
                st.caption(f"*{rec_reasoning}*")
            st.divider()

        # Issue checklist with reasoning
        for issue in answer_key.get("issues", []):
            iid = issue["id"]
            severity = issue.get("severity", "M")
            weight_tag = SEVERITY_LABEL.get(severity, "1x")
            hit = judge_issues.get(iid, 0)
            icon = "\u2713" if hit else "\u2717"
            st.markdown(f"{icon} **{iid}**: {issue['title']}  `{weight_tag}`")
            # Show per-issue reasoning if available
            issue_reasoning = reasoning.get(iid)
            if issue_reasoning:
                st.caption(f"*{issue_reasoning}*")

        # False positives
        if judge:
            fp_list = judge.get("false_positives", [])
            fp_count = judge.get("false_positive_count", 0)
            if fp_count > 0 or fp_list:
                st.divider()
                from config import FP_PENALTY_PER
                st.markdown(f"**False Positives ({fp_count})** (-{fp_count * FP_PENALTY_PER} pts)")
                for fp in fp_list:
                    st.markdown(f"- {fp}")

    # ------------------------------------------------------------------
    # Response tab — full model output
    # ------------------------------------------------------------------
    with tab_response:
        response = result.get("response_text", "")
        shifted = downshift_headings(response)
        st.markdown(
            f'<div class="doc-preview">\n\n{shifted}\n\n</div>',
            unsafe_allow_html=True,
        )
