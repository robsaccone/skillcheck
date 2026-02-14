"""Result detail view — summary, issue breakdown, and full response."""

import streamlit as st

from engine import get_scores, load_answer_key
from models import MODEL_CONFIGS
from components import TIER_LABEL, detection_chip


# ---------------------------------------------------------------------------
# Rubric dimension labels
# ---------------------------------------------------------------------------

ISSUE_DIMS = ["identified", "correctly_characterized", "severity_appropriate", "actionable"]
META_DIMS = ["identified", "synthesized", "strategic"]


def _dim_label(dim: str) -> str:
    """Human-readable label for a rubric dimension key."""
    return dim.replace("_", " ").capitalize()


def _est_cost(result: dict, model_key: str) -> float:
    """Estimate API cost in dollars from token counts and model pricing."""
    cfg = MODEL_CONFIGS.get(model_key, {})
    cost_in = cfg.get("cost_in", 0)
    cost_out = cfg.get("cost_out", 0)
    in_tok = result.get("input_tokens", 0)
    out_tok = result.get("output_tokens", 0)
    return (in_tok * cost_in + out_tok * cost_out) / 1_000_000


# ---------------------------------------------------------------------------
# Main render function
# ---------------------------------------------------------------------------

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
        # Parse ISO timestamp to readable format
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(timestamp)
            run_time = dt.strftime("%b %d, %Y at %I:%M %p")
        except (ValueError, TypeError):
            run_time = timestamp
    else:
        run_time = "Unknown"

    st.caption(f"{skill_id} · {doc_name} · Run {run_time}")

    quick = get_scores(result)
    judge = result.get("judge_scores")
    answer_key = load_answer_key(skill_id, doc_name)

    tab_summary, tab_issues, tab_response = st.tabs(["Summary", "Issues", "Response"])

    # ------------------------------------------------------------------
    # Summary tab — high-level metrics and plain-language explanation
    # ------------------------------------------------------------------
    with tab_summary:
        # Primary score — judge if available, else quick
        if judge:
            score_pct = judge.get("composite_score", 0) * 100
            score_label = "Judge Score"
        else:
            score_pct = quick.get("weighted_pct", 0)
            score_label = "Quick Score"

        found = quick.get("total_found", 0)
        possible = quick.get("total_possible", 0)
        secs = result.get("elapsed_seconds", 0)
        cost = _est_cost(result, model_key)

        in_tok = result.get("input_tokens", 0)
        out_tok = result.get("output_tokens", 0)
        total_tok = in_tok + out_tok

        mc1, mc2, mc3, mc4, mc5 = st.columns(5)
        mc1.metric(score_label, f"{score_pct:.0f}%")
        mc2.metric("Issues Found", f"{found}/{possible}")
        mc3.metric("Time", f"{secs:.0f}s")
        mc4.metric("Tokens", f"{total_tok:,}")
        mc5.metric("Est. Cost", f"${cost:.2f}")

        # Tier breakdown
        if quick:
            must = quick.get("must_catch", {})
            should = quick.get("should_catch", {})
            nice = quick.get("nice_to_catch", {})
            st.markdown(
                f"**Must-catch** {must.get('found', 0)}/{must.get('total', 0)} · "
                f"**Should-catch** {should.get('found', 0)}/{should.get('total', 0)} · "
                f"**Nice-to-catch** {nice.get('found', 0)}/{nice.get('total', 0)}"
            )

        # Judge quality dimensions (compact, inline)
        if judge:
            comp = judge.get("component_scores", {})
            st.markdown(
                f"**Completeness** {comp.get('completeness', 0) * 100:.0f}% · "
                f"**Precision** {comp.get('precision', 0) * 100:.0f}% · "
                f"**Quality** {comp.get('professional_quality', 0) * 10:.1f}/10 · "
                f"**Classification** {comp.get('classification_accuracy', 0) * 100:.0f}%"
            )

    # ------------------------------------------------------------------
    # Issues tab — per-issue rubric breakdown
    # ------------------------------------------------------------------
    with tab_issues:
        if not answer_key:
            st.info("No answer key available for this document.")
            return

        judge_issues = judge.get("issues", {}) if judge else {}
        judge_metas = judge.get("meta_issues", {}) if judge else {}
        issues_detected = quick.get("issues_detected", {})
        meta_detected = quick.get("meta_issues_detected", {})

        # Build tier map
        guidance = answer_key.get("scoring_guidance", {})
        tier_map = {}
        for tier in ["must_catch", "should_catch", "nice_to_catch"]:
            for iid in guidance.get(tier, []):
                tier_map[iid] = tier

        for issue in answer_key.get("issues", []):
            iid = issue["id"]
            tier = tier_map.get(iid, "")
            weight_tag = TIER_LABEL.get(tier, "")
            ji = judge_issues.get(iid)

            if ji:
                score = sum(ji.get(d, 0) for d in ISSUE_DIMS)
                max_score = len(ISSUE_DIMS)
                with st.expander(f"{score}/{max_score} — {iid}: {issue['title']} ({weight_tag})"):
                    rubric = issue.get("rubric", {})
                    for d in ISSUE_DIMS:
                        val = ji.get(d, 0)
                        icon = "\u2713" if val else "\u2717"
                        label = rubric.get(d, _dim_label(d))
                        st.markdown(f"{icon} **{_dim_label(d)}** — {label}")
                    notes = ji.get("judge_notes")
                    if notes:
                        st.caption(notes)
            else:
                detected = issues_detected.get(iid, False)
                st.markdown(
                    detection_chip(f"{iid}: {issue['title']} ({weight_tag})", detected),
                    unsafe_allow_html=True,
                )

        # Meta-issues
        metas = answer_key.get("meta_issues", [])
        if metas:
            st.markdown("**Meta-Issues**")
            for meta in metas:
                mid = meta["id"]
                jm = judge_metas.get(mid)

                if jm:
                    score = sum(jm.get(d, 0) for d in META_DIMS)
                    max_score = len(META_DIMS)
                    with st.expander(f"{score}/{max_score} — {mid}: {meta['title']}"):
                        rubric = meta.get("rubric", {})
                        for d in META_DIMS:
                            val = jm.get(d, 0)
                            icon = "\u2713" if val else "\u2717"
                            label = rubric.get(d, _dim_label(d))
                            st.markdown(f"{icon} **{_dim_label(d)}** — {label}")
                        notes = jm.get("judge_notes")
                        if notes:
                            st.caption(notes)
                else:
                    detected = meta_detected.get(mid, False)
                    st.markdown(
                        detection_chip(f"{mid}: {meta['title']}", detected),
                        unsafe_allow_html=True,
                    )

    # ------------------------------------------------------------------
    # Response tab — full model output
    # ------------------------------------------------------------------
    with tab_response:
        st.markdown(result.get("response_text", ""))
