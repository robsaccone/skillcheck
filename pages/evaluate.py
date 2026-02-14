"""Evaluate page — run evaluations, display results matrix and detail views."""

import pandas as pd
import streamlit as st
from streamlit_local_storage import LocalStorage

from models import MODEL_CONFIGS, get_available_models
from engine import (
    discover_skills,
    get_scores,
    judge_saved_results,
    list_skill_versions,
    list_test_docs,
    load_answer_key,
    load_results,
    run_evaluation,
)
from components import (
    TIER_LABEL,
    detection_chip,
    est_cost,
)
from pages.result_detail import render_result_page


# ---------------------------------------------------------------------------
# Styling helpers
# ---------------------------------------------------------------------------

def _score_bg(val):
    """Return background-color CSS for a score cell. Extracts % from strings like '94% · 12s · $0.18'."""
    if not isinstance(val, str) or "%" not in val:
        return ""
    try:
        pct = float(val.split("%")[0])
    except ValueError:
        return ""
    if pct >= 90:
        return "background-color: #065f46; color: #6ee7b7"
    elif pct >= 75:
        return "background-color: #92400e; color: #fde68a"
    return "background-color: #7f1d1d; color: #fca5a5"


def _get_cell_pct(result: dict) -> float | None:
    """Extract display percentage — judge composite if available, else quick weighted."""
    judge = result.get("judge_scores")
    if judge and "composite_score" in judge:
        return judge["composite_score"] * 100
    qs = get_scores(result)
    return qs.get("weighted_pct", 0) if qs else None




def render_results_matrix(results_map: dict, versions: list, model_keys: list, skill_id: str, doc_name: str):
    """Render results as a styled dataframe. Cell selection drills into detail view."""

    # Build display-name columns and a lookup from display name back to key
    model_names = []
    name_to_key = {}
    for mk in model_keys:
        name = MODEL_CONFIGS.get(mk, {}).get("display_name", mk)
        model_names.append(name)
        name_to_key[name] = mk

    # Build the dataframe: rows=versions, cols=model display names
    rows = []
    errors = []
    # Track totals across all versions
    all_pcts = []      # flat list of all percentages
    all_secs = []      # flat list of all elapsed times
    all_costs = []     # flat list of all costs

    for v in versions:
        row = {}
        pcts = []
        row_secs = []
        row_costs = []
        for mk, name in zip(model_keys, model_names):
            r = results_map.get((v, mk))
            if r and "error" not in r:
                pct = _get_cell_pct(r)
                if pct is not None:
                    secs = r.get("elapsed_seconds", 0)
                    cost = est_cost(r, mk)
                    row[name] = f"{pct:.0f}%   [{secs:.0f}s · ${cost:.2f}]"
                    pcts.append(pct)
                    row_secs.append(secs)
                    row_costs.append(cost)
                else:
                    row[name] = "\u2014"
            elif r and "error" in r:
                row[name] = "ERR"
                errors.append((v, name, r["error"]))
            else:
                row[name] = "\u2014"

        if pcts:
            avg_pct = sum(pcts) / len(pcts)
            total_secs = sum(row_secs)
            total_cost = sum(row_costs)
            row["Score"] = f"{avg_pct:.0f}%   [{total_secs:.0f}s · ${total_cost:.2f}]"
        else:
            row["Score"] = "\u2014"

        all_pcts.extend(pcts)
        all_secs.extend(row_secs)
        all_costs.extend(row_costs)
        rows.append(row)

    # Totals row
    totals_row = {}
    for name in model_names:
        # Aggregate per-model across all versions
        m_pcts, m_secs, m_costs = [], [], []
        mk = name_to_key[name]
        for v in versions:
            r = results_map.get((v, mk))
            if r and "error" not in r:
                pct = _get_cell_pct(r)
                if pct is not None:
                    m_pcts.append(pct)
                    m_secs.append(r.get("elapsed_seconds", 0))
                    m_costs.append(est_cost(r, mk))
        if m_pcts:
            totals_row[name] = f"{sum(m_pcts)/len(m_pcts):.0f}%   [{sum(m_secs):.0f}s · ${sum(m_costs):.2f}]"
        else:
            totals_row[name] = "\u2014"

    if all_pcts:
        totals_row["Score"] = f"{sum(all_pcts)/len(all_pcts):.0f}%   [{sum(all_secs):.0f}s · ${sum(all_costs):.2f}]"
    else:
        totals_row["Score"] = "\u2014"
    rows.append(totals_row)
    index_labels = versions + ["\u03a3 Total"]

    df = pd.DataFrame(rows, index=index_labels)
    df.index.name = "Version"

    # Apply conditional coloring via Pandas Styler
    summary_style = "font-weight: bold; background-color: rgba(255,255,255,0.05)"

    def _highlight_summaries(val, row_name, col_name):
        """Bold + subtle background for the totals row and Score column."""
        if row_name == "\u03a3 Total":
            return f"{summary_style}; border-top: 2px solid #4a5568"
        if col_name == "Score":
            return f"{summary_style}; border-left: 2px solid #4a5568"
        return ""

    def _summary_style_fn(df_input):
        return pd.DataFrame(
            [[_highlight_summaries(df_input.iloc[r, c], df_input.index[r], df_input.columns[c])
              for c in range(len(df_input.columns))]
             for r in range(len(df_input.index))],
            index=df_input.index,
            columns=df_input.columns,
        )

    styled = df.style.map(_score_bg).apply(_summary_style_fn, axis=None)

    # Render with cell selection enabled
    event = st.dataframe(
        styled,
        width="stretch",
        hide_index=False,
        on_select="rerun",
        selection_mode="single-cell",
        key="results_matrix",
        column_config={
            "Version": st.column_config.TextColumn(label="Skill Version"),
            "Score": st.column_config.TextColumn(width="small"),
        },
    )

    # Handle cell click → drill into detail view
    sel = event.selection if event else None
    if sel:
        cells = sel.get("cells", []) if isinstance(sel, dict) else getattr(sel, "cells", [])
        if cells:
            c = cells[0]
            # Streamlit returns {"row": int, "column": str_or_int}
            if isinstance(c, dict):
                row_idx = c.get("row")
                col_val = c.get("column")
            elif isinstance(c, (list, tuple)) and len(c) >= 2:
                row_idx, col_val = c[0], c[1]
            else:
                row_idx = col_val = None

            if row_idx is not None and col_val is not None and row_idx < len(versions):
                # col_val may be a column name (str) or index (int)
                col_name = col_val if isinstance(col_val, str) else (
                    model_names[col_val] if isinstance(col_val, int) and col_val < len(model_names) else None
                )
                mk = name_to_key.get(col_name) if col_name else None
                if mk:
                    v = versions[row_idx]
                    r = results_map.get((v, mk))
                    if r and "error" not in r:
                        st.session_state.selected_result = (v, mk)
                        st.session_state.selected_result_ctx = {
                            "skill_id": skill_id,
                            "doc": doc_name,
                            "results": results_map,
                        }
                        st.rerun()

    # Show errors below the table
    if errors:
        with st.expander(f":red[**{len(errors)} error(s)**]", expanded=False):
            for v, model, err in errors:
                st.text(f"{v} \u00d7 {model}: {err}")

    # Issue heatmap — shows per-issue detection across all version x model combos
    answer_key = load_answer_key(skill_id, doc_name)
    if not answer_key:
        return

    # Collect all results that have scores
    scored = []
    for v in versions:
        for mk in model_keys:
            r = results_map.get((v, mk))
            if r and "error" not in r and get_scores(r):
                scored.append((v, mk, r))

    if not scored:
        return

    issues = answer_key.get("issues", [])
    meta_issues = answer_key.get("meta_issues", [])
    guidance = answer_key.get("scoring_guidance", {})
    tier_map = {}
    for tier in ["must_catch", "should_catch", "nice_to_catch"]:
        for iid in guidance.get(tier, []):
            tier_map[iid] = tier

    st.divider()
    st.markdown("### Issue Analysis")

    heatmap_models = list(dict.fromkeys(mk for _, mk, _ in scored))
    all_issues = issues + meta_issues

    # Issue rubric dimensions for score fractions
    issue_dims = ["identified", "correctly_characterized", "severity_appropriate", "actionable"]
    meta_dims = ["identified", "synthesized", "strategic"]

    tab_labels = []
    for mk in heatmap_models:
        display = MODEL_CONFIGS.get(mk, {}).get("display_name", mk)
        tab_labels.append(display)

    tabs = st.tabs(tab_labels)

    for tab, mk in zip(tabs, heatmap_models):
        filtered = [(v, mk2, r) for v, mk2, r in scored if mk2 == mk]
        if not filtered:
            continue

        with tab:
            heatmap_rows = []
            issue_labels = []
            ncols = len(filtered)
            for issue in all_issues:
                iid = issue["id"]
                is_meta = iid.startswith("META")
                dims = meta_dims if is_meta else issue_dims
                tier = tier_map.get(iid, "")
                tier_tag = TIER_LABEL.get(tier, "")
                issue_labels.append(f"{iid} {issue['title']}  {tier_tag}")

                row = {}
                total_pts = 0
                total_max = 0
                for v, _, r in filtered:
                    judge = r.get("judge_scores")
                    judge_bucket = "meta_issues" if is_meta else "issues"
                    ji = judge.get(judge_bucket, {}).get(iid) if judge else None

                    if ji:
                        score = sum(ji.get(d, 0) for d in dims)
                        row[v] = f"{score}/{len(dims)}"
                        total_pts += score
                        total_max += len(dims)
                    else:
                        sc = get_scores(r)
                        det = sc.get("issues_detected", {})
                        meta_det = sc.get("meta_issues_detected", {})
                        detected = det.get(iid, False) or meta_det.get(iid, False)
                        row[v] = "\u2705" if detected else "\u274c"
                        total_pts += 1 if detected else 0
                        total_max += 1

                rate = f"{total_pts / total_max * 100:.0f}%" if total_max else "\u2014"
                row["Score"] = rate
                heatmap_rows.append(row)

            if heatmap_rows:
                heatmap_df = pd.DataFrame(heatmap_rows, index=issue_labels)
                heatmap_df.index.name = "Issue"
                st.dataframe(
                    heatmap_df.style.map(
                        _score_bg, subset=["Score"]
                    ),
                    width="stretch",
                    hide_index=False,
                )


# ---------------------------------------------------------------------------
# Page body
# ---------------------------------------------------------------------------

# Full-page detail view when a result is selected
sel = st.session_state.get("selected_result")
if sel:
    # Try cell-click context first, then eval_results, then disk
    results_src = (
        st.session_state.get("selected_result_ctx")
        or st.session_state.get("eval_results")
        or {}
    )
    results_map = results_src.get("results", {})
    if not results_map:
        skill_id = results_src.get("skill_id", "")
        for r in load_results(skill_id):
            v, mk = r.get("version", ""), r.get("model_key", "")
            if v and mk:
                results_map[(v, mk)] = r
    v, mk = sel
    r = results_map.get((v, mk))
    if r and "error" not in r:
        skill_id = results_src.get("skill_id", r.get("skill_id", ""))
        doc_name = results_src.get("doc", r.get("doc_name", ""))
        render_result_page(r, v, mk, skill_id, doc_name)
        st.stop()
    else:
        del st.session_state.selected_result

st.markdown("## Evaluate")
st.caption("Skillcheck will run and evaluate all combinations of the selected models, skills, and documents.")

skills = discover_skills()
available = get_available_models()

if not skills:
    st.info("No skills found.")
    st.stop()

if not available:
    st.warning("No models available. Add API keys to your .env file.")
    st.stop()

running = st.session_state.get("eval_running", False)

# Controls — disabled while running
skill_map = {s["skill_id"]: s["display_name"] for s in skills}
skill_options = list(skill_map.keys())
model_options = list(available.keys())

# --- Persistent storage for sticky selections ---
ls = LocalStorage(key="eval_storage")

# Restore from localStorage on fresh load (browser refresh)
if "eval_models" not in st.session_state:
    saved = ls.getItem("eval_models")
    if saved:
        valid = [m for m in saved.split(",") if m in model_options]
        if valid:
            st.session_state.eval_models = valid
    if "eval_models" not in st.session_state:
        st.session_state.eval_models = model_options[:2] if len(model_options) >= 2 else model_options

if "eval_skill" not in st.session_state:
    saved = ls.getItem("eval_skill")
    if saved and saved in skill_options:
        st.session_state.eval_skill = saved

# Restore judge selections from localStorage
if "judge1" not in st.session_state:
    saved = ls.getItem("judge1")
    if saved and saved in model_options:
        st.session_state.judge1 = saved
    else:
        st.session_state.judge1 = model_options[0] if model_options else None
    st.session_state.judge2 = None
    saved2 = ls.getItem("judge2")
    if saved2 and saved2 in model_options:
        st.session_state.judge2 = saved2

# Doc restoration happens after skill is resolved (options depend on skill)

col1, col2, col3 = st.columns(3)

with col1:
    selected_models = st.multiselect(
        "Select Models",
        options=model_options,
        format_func=lambda k: MODEL_CONFIGS[k]["display_name"],
        disabled=running,
        key="eval_models",
    )

with col2:
    selected_skill = st.selectbox(
        "Select Skill",
        options=skill_options,
        format_func=lambda k: skill_map[k],
        disabled=running,
        key="eval_skill",
    )

with col3:
    docs = list_test_docs(selected_skill)
    if docs:
        # Restore doc from localStorage if not in session_state
        if "eval_doc" not in st.session_state:
            saved = ls.getItem("eval_doc")
            if saved and saved in docs:
                st.session_state.eval_doc = saved

        selected_doc = st.selectbox(
            "Select Test",
            options=docs,
            disabled=running,
            key="eval_doc",
        )
    else:
        st.selectbox("Select Test", options=[], disabled=True, key="eval_doc_empty", placeholder="No tests found")
        selected_doc = None

can_run = selected_doc and len(selected_models) >= 1

# --- Run / Cancel button + status (same row) ---
if not running:
    run_clicked = st.button("Run", disabled=not can_run, type="primary")
    if run_clicked and can_run:
        st.session_state.eval_running = True
        st.session_state.eval_run_skill = selected_skill
        st.session_state.eval_run_models = selected_models
        st.session_state.eval_run_doc = selected_doc
        st.rerun()
else:
    btn_col, status_col = st.columns([1, 6], vertical_alignment="center")
    cancel_clicked = btn_col.button("Cancel", type="secondary")
    if cancel_clicked:
        st.session_state.eval_running = False
        st.rerun()
    spinner_container = status_col.empty()

versions = list_skill_versions(selected_skill)

# --- Running: execute evaluations with live table ---
if running:
    run_skill = st.session_state.eval_run_skill
    run_models = st.session_state.eval_run_models
    run_doc = st.session_state.eval_run_doc
    run_versions = list_skill_versions(run_skill)
    total = len(run_versions) * len(run_models)

    # Always judge if configured
    judge_model_key = st.session_state.get("judge1")
    judge_system_prompt = st.session_state.get("judge_system_prompt") if judge_model_key else None

    st.markdown("### Results")
    table_placeholder = st.empty()

    completed = 0
    results_map = {}
    model_names = [MODEL_CONFIGS.get(mk, {}).get("display_name", mk) for mk in run_models]

    judge_configured = judge_model_key is not None
    phase_label = "Evaluating + judging" if judge_configured else "Evaluating"

    with spinner_container.container():
        with st.spinner(f"{phase_label} ({total} evals)...", show_time=True):
            for version, model_key, result in run_evaluation(
                run_skill, run_models, run_doc,
                judge_model_key=judge_model_key,
                judge_system_prompt=judge_system_prompt,
            ):
                results_map[(version, model_key)] = result

                # Rebuild live table
                rows = []
                for v in run_versions:
                    row = {}
                    for mk, name in zip(run_models, model_names):
                        r = results_map.get((v, mk))
                        if r and "error" not in r:
                            pct = _get_cell_pct(r)
                            if pct is not None:
                                secs = r.get("elapsed_seconds", 0)
                                cost = est_cost(r, mk)
                                row[name] = f"{pct:.0f}%   [{secs:.0f}s \u00b7 ${cost:.2f}]"
                            else:
                                row[name] = "\u2014"
                        elif r and "error" in r:
                            row[name] = "ERR"
                        else:
                            row[name] = "\u00b7\u00b7\u00b7"
                    rows.append(row)

                df = pd.DataFrame(rows, index=run_versions)
                df.index.name = "Version"
                table_placeholder.dataframe(
                    df.style.map(_score_bg),
                    width="stretch",
                    hide_index=False,
                )

    spinner_container.caption(f"Complete! {len(results_map)} evaluations run.")

    # Store results and stop running
    st.session_state.eval_results = {
        "skill_id": run_skill,
        "models": run_models,
        "doc": run_doc,
        "results": results_map,
    }
    st.session_state.eval_running = False
    st.rerun()

# --- Display results (from session_state or disk) ---
if not running:
    # Check for fresh results in session_state
    eval_data = st.session_state.get("eval_results")
    if eval_data and eval_data["skill_id"] == selected_skill:
        st.markdown("### Results")
        render_results_matrix(
            eval_data["results"],
            versions,
            eval_data["models"],
            eval_data["skill_id"],
            eval_data["doc"],
        )
    else:
        # Fall back to saved results on disk, filtered to selected models
        existing = load_results(selected_skill)
        if existing and versions and selected_models:
            st.markdown("### Results")
            selected_set = set(selected_models)
            matrix = {}
            model_keys_seen = set()
            for r in existing:
                v = r.get("version", "")
                mk = r.get("model_key", "")
                if v and mk and mk in selected_set:
                    matrix[(v, mk)] = r
                    model_keys_seen.add(mk)

            if matrix:
                render_results_matrix(
                    matrix,
                    versions,
                    sorted(model_keys_seen),
                    selected_skill,
                    existing[0].get("doc_name", ""),
                )

# --- Judge unjudged results button ---
judge_configured = st.session_state.get("judge1") is not None
if not running and judge_configured and selected_doc:
    # Count unjudged results on disk
    all_existing = load_results(selected_skill)
    unjudged = [r for r in all_existing if r.get("judge_scores") is None]
    if unjudged:
        if st.button(f"Judge unjudged results ({len(unjudged)})", type="secondary"):
            judge_model_key = st.session_state.get("judge1")
            judge_sys = st.session_state.get("judge_system_prompt")
            progress = st.progress(0, text="Judging saved results...")
            updated = judge_saved_results(selected_skill, judge_model_key, judge_sys)
            progress.progress(1.0, text=f"Done! Judged {len(updated)} results.")
            # Clear cached eval_results so disk results reload
            if "eval_results" in st.session_state:
                del st.session_state["eval_results"]
            st.rerun()

# --- Sync current selections to localStorage (at bottom to avoid layout gaps) ---
ls.setItem("eval_models", ",".join(selected_models) if selected_models else "", key="save_models")
ls.setItem("eval_skill", selected_skill or "", key="save_skill")
if selected_doc:
    ls.setItem("eval_doc", selected_doc, key="save_doc")
