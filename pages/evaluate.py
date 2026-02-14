"""Evaluate page — run evaluations, display results matrix and detail views."""

import pandas as pd
import streamlit as st
from streamlit_local_storage import LocalStorage

from models import MODEL_CONFIGS, get_available_models
from engine import (
    discover_skills,
    list_skill_versions,
    list_test_docs,
    load_answer_key,
    load_results,
    run_evaluation,
)
from components import (
    TIER_LABEL,
    detection_chip,
)


# ---------------------------------------------------------------------------
# Styling helpers
# ---------------------------------------------------------------------------

def _score_bg(val):
    """Return background-color CSS for a formatted score cell like '97%'."""
    if not isinstance(val, str) or not val.endswith("%"):
        return ""
    try:
        pct = float(val[:-1])
    except ValueError:
        return ""
    if pct >= 70:
        return "background-color: #065f46; color: #6ee7b7"
    elif pct >= 40:
        return "background-color: #92400e; color: #fde68a"
    return "background-color: #7f1d1d; color: #fca5a5"


# ---------------------------------------------------------------------------
# Local rendering helpers
# ---------------------------------------------------------------------------

def render_result_page(result: dict, version: str, model_key: str, skill_id: str, doc_name: str):
    """Full-page detail view for a single result. Stats left, response right."""
    model_name = MODEL_CONFIGS.get(model_key, {}).get("display_name", model_key)

    if st.button("\u2190 Back to results", type="tertiary"):
        del st.session_state.selected_result
        st.rerun()

    st.markdown(f"## {version} x {model_name}")

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
    # Pre-format values as strings so the renderer shows exactly what we want
    rows = []
    for v in versions:
        row = {}
        pcts = []
        for mk, name in zip(model_keys, model_names):
            r = results_map.get((v, mk))
            if r and "error" not in r:
                pct = r.get("auto_scores", {}).get("weighted_pct", 0)
                row[name] = f"{pct:.0f}%"
                pcts.append(pct)
            elif r and "error" in r:
                row[name] = "ERR"
            else:
                row[name] = "\u2014"
        row["Score"] = f"{sum(pcts) / len(pcts):.0f}%" if pcts else "\u2014"
        rows.append(row)

    df = pd.DataFrame(rows, index=versions)
    df.index.name = "Version"

    # Apply conditional coloring via Pandas Styler
    styled = df.style.map(_score_bg)

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

            if row_idx is not None and col_val is not None:
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

    # Issue heatmap — shows per-issue detection across all version x model combos
    answer_key = load_answer_key(skill_id, doc_name)
    if not answer_key:
        return

    # Collect all results that have scores
    scored = []
    for v in versions:
        for mk in model_keys:
            r = results_map.get((v, mk))
            if r and "error" not in r and r.get("auto_scores"):
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

    # Build tab labels with aggregate detection rate
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
                tier = tier_map.get(iid, "")
                tier_tag = TIER_LABEL.get(tier, "")
                issue_labels.append(f"{iid} {issue['title']}  {tier_tag}")

                row = {}
                hits = 0
                for v, _, r in filtered:
                    sc = r["auto_scores"]
                    det = sc.get("issues_detected", {})
                    meta_det = sc.get("meta_issues_detected", {})
                    detected = det.get(iid, False) or meta_det.get(iid, False)
                    row[v] = "\u2705" if detected else "\u274c"
                    if detected:
                        hits += 1
                rate = f"{hits / ncols * 100:.0f}%" if ncols else "\u2014"
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
            "Select Document",
            options=docs,
            disabled=running,
            key="eval_doc",
        )
    else:
        st.selectbox("Select Document", options=[], disabled=True, key="eval_doc_empty", placeholder="No documents found")
        selected_doc = None

# Prompt input and judge checkbox — inline row
can_run = selected_doc and len(selected_models) >= 2

judge_configured = st.session_state.get("judge1") is not None
judge_model_name = (
    MODEL_CONFIGS.get(st.session_state.get("judge1", ""), {}).get("display_name", "")
    if judge_configured else ""
)


def _on_prompt_submit():
    val = st.session_state.get("eval_prompt_input", "").strip()
    if val and can_run and not running:
        st.session_state.eval_running = True
        st.session_state.eval_run_skill = selected_skill
        st.session_state.eval_run_models = selected_models
        st.session_state.eval_run_doc = selected_doc
        st.session_state.eval_prompt = val
        st.session_state.eval_prompt_input = ""
        st.session_state.eval_run_judge_active = run_judge


prompt_col, btn_col, judge_col = st.columns([6, 1, 2], vertical_alignment="bottom")
prompt_col.text_input(
    "Prompt",
    placeholder="Type a prompt and press Enter...",
    disabled=not can_run or running,
    label_visibility="collapsed",
    key="eval_prompt_input",
    on_change=_on_prompt_submit,
)
run_clicked = btn_col.button(
    "Run",
    disabled=not can_run or running,
    type="primary",
    width="stretch",
)
run_judge = judge_col.checkbox(
    "Judge",
    value=judge_configured,
    disabled=not judge_configured or running,
    key="eval_run_judge",
    help=f"Judge: {judge_model_name}" if judge_configured else "Configure on Judges page",
)

# Button click also triggers run
if run_clicked and can_run and not running:
    prompt_val = st.session_state.get("eval_prompt_input", "").strip() or "run"
    st.session_state.eval_running = True
    st.session_state.eval_run_skill = selected_skill
    st.session_state.eval_run_models = selected_models
    st.session_state.eval_run_doc = selected_doc
    st.session_state.eval_prompt = prompt_val
    st.session_state.eval_run_judge_active = run_judge
    st.rerun()

versions = list_skill_versions(selected_skill)

# --- Running: execute evaluations with progress ---
if running:
    run_skill = st.session_state.eval_run_skill
    run_models = st.session_state.eval_run_models
    run_doc = st.session_state.eval_run_doc
    run_versions = list_skill_versions(run_skill)
    total = len(run_versions) * len(run_models)

    # Resolve judge params
    use_judge = st.session_state.get("eval_run_judge_active", False)
    judge_model_key = st.session_state.get("judge1") if use_judge else None
    judge_system_prompt = st.session_state.get("judge_system_prompt") if use_judge else None
    judge_suffix = " (judging)" if judge_model_key else ""

    progress = st.progress(0, text=f"Starting evaluation...{judge_suffix}")
    completed = 0
    results_map = {}

    for version, model_key, result in run_evaluation(
        run_skill, run_models, run_doc,
        judge_model_key=judge_model_key,
        judge_system_prompt=judge_system_prompt,
    ):
        completed += 1
        results_map[(version, model_key)] = result
        progress.progress(
            completed / total,
            text=f"{completed}/{total} — {version} x {MODEL_CONFIGS[model_key]['display_name']}{judge_suffix}",
        )

    progress.progress(1.0, text=f"Complete! {completed} evaluations run.")

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

# --- Sync current selections to localStorage (at bottom to avoid layout gaps) ---
ls.setItem("eval_models", ",".join(selected_models) if selected_models else "", key="save_models")
ls.setItem("eval_skill", selected_skill or "", key="save_skill")
if selected_doc:
    ls.setItem("eval_doc", selected_doc, key="save_doc")
