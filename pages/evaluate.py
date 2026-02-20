"""Evaluate page — run evaluations, display results matrix and detail views."""

import pandas as pd
import streamlit as st
from streamlit_local_storage import LocalStorage

from models import MODEL_CONFIGS, get_available_models
from engine import (
    build_results_map,
    discover_skills,
    get_version_display_name,
    judge_saved_results,
    rescore_saved_results,
    list_skill_versions,
    list_test_docs,
    load_answer_key,
    load_results,
    run_evaluation,
)
from components import (
    est_cost,
    fmt_time,
    handle_result_selection,
    score_bg,
    get_cell_pct,
    render_results_matrix,
)


# ---------------------------------------------------------------------------
# Full-page detail view when a result is selected
# ---------------------------------------------------------------------------

if handle_result_selection():
    st.stop()

# ---------------------------------------------------------------------------
# Results viewer mode (entered from sidebar recent runs)
# ---------------------------------------------------------------------------

if st.session_state.get("viewer_mode"):
    from datetime import datetime as _dt

    _skill_id = st.session_state.get("viewer_skill")
    _doc_name = st.session_state.get("viewer_doc")

    if not _skill_id or not _doc_name:
        st.session_state.pop("viewer_mode", None)
        st.rerun()

    if st.button("\u2190 Back to evaluate", type="tertiary"):
        st.session_state.pop("viewer_mode", None)
        st.session_state.pop("viewer_skill", None)
        st.session_state.pop("viewer_doc", None)
        st.rerun()

    st.markdown(f"## Results: {_skill_id} / {_doc_name}")

    _versions = list_skill_versions(_skill_id)
    _matrix, _model_keys_seen = build_results_map(_skill_id, doc_name=_doc_name)

    if not _versions or not _matrix:
        st.info(f"No results found for test document '{_doc_name}'.")
        st.stop()

    _timestamps = [_r.get("timestamp", "") for _r in _matrix.values() if _r.get("timestamp")]
    if _timestamps:
        _latest = max(_timestamps)
        try:
            _dt_obj = _dt.fromisoformat(_latest).astimezone()
            st.caption(f"Last run: {_dt_obj.strftime('%b %d, %Y at %I:%M %p')}")
        except ValueError:
            pass

    st.session_state.viewer_results = {
        "skill_id": _skill_id,
        "doc": _doc_name,
        "results": _matrix,
    }

    render_results_matrix(
        _matrix,
        _versions,
        sorted(_model_keys_seen),
        _skill_id,
        _doc_name,
        widget_key="results_viewer_matrix",
    )
    st.stop()

# ---------------------------------------------------------------------------
# Evaluate mode (default)
# ---------------------------------------------------------------------------

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

# Restore judge selections from localStorage (saved by judges page)
if "judge1" not in st.session_state:
    judge_ls = LocalStorage(key="judges_storage")
    saved = judge_ls.getItem("judge1")
    if saved and saved in model_options:
        st.session_state.judge1 = saved
    else:
        st.session_state.judge1 = model_options[0] if model_options else None
    st.session_state.judge2 = None
    saved2 = judge_ls.getItem("judge2")
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
    all_versions = list_skill_versions(selected_skill)
    selected_versions = st.multiselect(
        "Versions (leave empty for all)",
        options=all_versions,
        format_func=lambda v: get_version_display_name(selected_skill, v),
        default=[],
        disabled=running,
        key="eval_versions",
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

# --- Business context (editable) ---
if selected_doc and selected_skill:
    ak = load_answer_key(selected_skill, selected_doc)
    default_ctx = ak.get("business_context", "") if ak else ""

    # Initialize from answer key on first load or doc change
    ctx_key = f"biz_ctx_{selected_skill}_{selected_doc}"
    if ctx_key not in st.session_state:
        st.session_state[ctx_key] = default_ctx

    business_context = st.text_area(
        "Business Context",
        key=ctx_key,
        height=100,
        disabled=running,
        help="This context is injected into the model's prompt. Edit to test different scenarios.",
    )
else:
    business_context = ""

can_run = selected_doc and len(selected_models) >= 1

# --- Run / Cancel button + status (same row) ---
if not running:
    run_clicked = st.button("Run", disabled=not can_run, type="primary")
    if run_clicked and can_run:
        st.session_state.eval_running = True
        st.session_state.eval_run_skill = selected_skill
        st.session_state.eval_run_models = selected_models
        st.session_state.eval_run_doc = selected_doc
        st.session_state.eval_run_versions = selected_versions or None
        st.session_state.eval_run_biz_ctx = business_context
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
    version_filter = st.session_state.get("eval_run_versions")
    run_versions = version_filter if version_filter else list_skill_versions(run_skill)
    run_biz_ctx = st.session_state.get("eval_run_biz_ctx", "")
    total = len(run_versions) * len(run_models)

    # Always judge if configured
    judge_model_key = st.session_state.get("judge1")
    judge_system_prompt = st.session_state.get("judge_system_prompt") if judge_model_key else None

    st.markdown("### Results")
    table_placeholder = st.empty()

    completed = 0
    results_map = {}

    col_keys = list(run_models)
    col_names = [MODEL_CONFIGS.get(mk, {}).get("display_name", mk) for mk in run_models]
    run_version_labels = [get_version_display_name(run_skill, v) for v in run_versions]

    judge_configured = judge_model_key is not None
    phase_label = "Evaluating + judging" if judge_configured else "Evaluating"

    # Skeleton table — show immediately before any results arrive
    skeleton_rows = []
    for v in run_versions:
        row = {name: "\u00b7\u00b7\u00b7" for name in col_names}
        skeleton_rows.append(row)
    skeleton_df = pd.DataFrame(skeleton_rows, index=run_version_labels)
    skeleton_df.index.name = "Version"
    table_placeholder.dataframe(skeleton_df, width="stretch", hide_index=False)

    with spinner_container.container():
        with st.spinner(f"{phase_label} ({total} evals)...", show_time=True):
            for version, model_key, result in run_evaluation(
                run_skill, run_models, run_doc,
                judge_model_key=judge_model_key,
                judge_system_prompt=judge_system_prompt,
                version_filter=version_filter,
                business_context=run_biz_ctx,
            ):
                results_map[(version, model_key)] = result

                # Rebuild live table
                rows = []
                for v in run_versions:
                    row = {}
                    for mk, name in zip(col_keys, col_names):
                        r = results_map.get((v, mk))
                        if r and "error" not in r:
                            pct = get_cell_pct(r)
                            secs = r.get("elapsed_seconds", 0)
                            cost = est_cost(r, mk)
                            if pct is not None:
                                row[name] = f"{pct:.0f}%   [{fmt_time(secs)} \u00b7 ${cost:.2f}]"
                            else:
                                row[name] = f"[{fmt_time(secs)} \u00b7 ${cost:.2f}]"
                        elif r and "error" in r:
                            row[name] = "ERR"
                        else:
                            row[name] = "\u00b7\u00b7\u00b7"
                    rows.append(row)

                df = pd.DataFrame(rows, index=run_version_labels)
                df.index.name = "Version"
                table_placeholder.dataframe(
                    df.style.map(score_bg),
                    width="stretch",
                    hide_index=False,
                )

    errors = {k: r["error"] for k, r in results_map.items() if "error" in r}
    ok_count = len(results_map) - len(errors)
    spinner_container.caption(f"Complete! {ok_count} evaluations run.")

    if errors:
        with st.expander(f":material/error: {len(errors)} failed", expanded=False):
            for (v, mk), msg in errors.items():
                model_name = MODEL_CONFIGS.get(mk, {}).get("display_name", mk)
                st.caption(f"**{v}** x **{model_name}**: {msg}")

    # Merge new results with existing disk results for complete display
    full_results, model_keys_seen = build_results_map(run_skill)
    model_keys_seen.update(run_models)
    full_results.update(results_map)  # new results override disk

    st.session_state.eval_results = {
        "skill_id": run_skill,
        "models": sorted(model_keys_seen),
        "doc": run_doc,
        "results": full_results,
    }
    st.session_state.eval_running = False
    st.rerun()

# --- Display results (from session_state or disk) ---
if not running:
    # Check for fresh results in session_state
    eval_data = st.session_state.get("eval_results")
    if eval_data and eval_data["skill_id"] == selected_skill and eval_data.get("doc") == selected_doc:
        st.markdown("### Results")
        render_results_matrix(
            eval_data["results"],
            versions,
            eval_data["models"],
            eval_data["skill_id"],
            eval_data["doc"],
        )
    else:
        # Fall back to saved results on disk, filtered to selected models and doc
        if versions and selected_models and selected_doc:
            matrix, model_keys_seen = build_results_map(
                selected_skill, doc_name=selected_doc, model_filter=set(selected_models),
            )
            if matrix:
                st.markdown("### Results")
                render_results_matrix(
                    matrix,
                    versions,
                    sorted(model_keys_seen),
                    selected_skill,
                    selected_doc,
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
            judged_count = 0
            for completed, total, result in judge_saved_results(selected_skill, judge_model_key, judge_sys):
                judged_count += 1 if result else 0
                progress.progress(completed / total, text=f"Judging saved results... ({completed}/{total})")
            progress.progress(1.0, text=f"Done! Judged {judged_count} results.")
            # Clear cached eval_results so disk results reload
            if "eval_results" in st.session_state:
                del st.session_state["eval_results"]
            st.rerun()

# --- Rescore button (recompute composites from existing judge output) ---
if not running and selected_doc:
    judged = [r for r in load_results(selected_skill) if r.get("judge_scores") is not None]
    if judged:
        if st.button(f"Rescore results ({len(judged)})", type="secondary",
                      help="Recompute composite scores from existing judge output using current scoring parameters. No API calls."):
            count = rescore_saved_results(selected_skill)
            st.toast(f"Rescored {count} results.")
            if "eval_results" in st.session_state:
                del st.session_state["eval_results"]
            st.rerun()

# --- Sync current selections to localStorage (at bottom to avoid layout gaps) ---
ls.setItem("eval_models", ",".join(selected_models) if selected_models else "", key="save_models")
ls.setItem("eval_skill", selected_skill or "", key="save_skill")
if selected_doc:
    ls.setItem("eval_doc", selected_doc, key="save_doc")
