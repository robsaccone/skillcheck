"""Shared UI helpers and constants for Skillcheck."""

import re

import pandas as pd
import streamlit as st

from models import MODEL_CONFIGS

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SEVERITY_LABEL = {"H": "3x", "M": "2x", "L": "1x"}

SEVERITY_EMOJI = {"H": "\U0001f534", "M": "\U0001f7e0", "L": "\u26aa"}


def severity_prefix(severity: str) -> str:
    return SEVERITY_EMOJI.get(severity, "") + " " + severity


def downshift_headings(md: str, levels: int = 2) -> str:
    """Shift markdown headings down by `levels` (# → ###, ## → ####, etc.)."""
    def _replace(m: re.Match) -> str:
        hashes = m.group(1)
        new_level = min(len(hashes) + levels, 6)
        return "#" * new_level + m.group(2)
    return re.sub(r"^(#{1,6})([ \t])", _replace, md, flags=re.MULTILINE)


def strip_front_matter(md: str) -> str:
    """Remove HTML comments and YAML front matter from markdown."""
    text = md
    while text.lstrip().startswith("<!--"):
        end = text.find("-->")
        if end == -1:
            break
        text = text[end + 3:].lstrip("\n")
    if text.startswith("---"):
        end = text.find("---", 3)
        if end != -1:
            text = text[end + 3:].lstrip("\n")
    return text


# ---------------------------------------------------------------------------
# Result drill-down
# ---------------------------------------------------------------------------

def handle_result_selection() -> bool:
    """Check for a selected result in session_state and render its detail page.

    Returns True if a result was rendered (caller should st.stop()),
    False if no selection or selection was invalid.
    """
    from engine import build_results_map
    from pages.result_detail import render_result_page

    sel = st.session_state.get("selected_result")
    if not sel:
        return False

    results_src = (
        st.session_state.get("selected_result_ctx")
        or st.session_state.get("viewer_results")
        or st.session_state.get("eval_results")
        or {}
    )
    results_map = results_src.get("results", {})
    if not results_map:
        skill_id = results_src.get("skill_id", "")
        results_map, _ = build_results_map(skill_id)

    v, mk = sel
    r = results_map.get((v, mk))
    if r and "error" not in r:
        skill_id = results_src.get("skill_id", r.get("skill_id", ""))
        doc_name = results_src.get("doc", r.get("doc_name", ""))
        render_result_page(r, v, mk, skill_id, doc_name)
        return True

    del st.session_state.selected_result
    return False


# ---------------------------------------------------------------------------
# Cost estimation
# ---------------------------------------------------------------------------

def est_cost(result: dict, model_key: str) -> float:
    """Estimate API cost in dollars from token counts and model pricing."""
    cfg = MODEL_CONFIGS.get(model_key, {})
    cost_in = cfg.get("cost_in", 0)
    cost_out = cfg.get("cost_out", 0)
    in_tok = result.get("input_tokens", 0)
    out_tok = result.get("output_tokens", 0)
    return (in_tok * cost_in + out_tok * cost_out) / 1_000_000


# ---------------------------------------------------------------------------
# Shared rendering helpers
# ---------------------------------------------------------------------------

def fmt_time(secs: float) -> str:
    """Format seconds as m:ss for readability."""
    m, s = divmod(int(secs), 60)
    return f"{m}:{s:02d}"


def score_bg(val):
    """Return background-color CSS for a score cell. Extracts % from strings like '94% · 12s · $0.18'."""
    if not isinstance(val, str) or "%" not in val:
        return ""
    try:
        pct = float(val.split("%")[0])
    except ValueError:
        return ""
    if pct >= 85:
        return "background-color: #065f46; color: #6ee7b7"
    elif pct >= 65:
        return "background-color: #92400e; color: #fde68a"
    return "background-color: #7f1d1d; color: #fca5a5"


def get_cell_pct(result: dict) -> float | None:
    """Extract display percentage from judge composite score. Returns None if not judged."""
    judge = result.get("judge_scores")
    if judge and "composite_score" in judge:
        return judge["composite_score"] * 100
    return None


def render_results_matrix(
    results_map: dict,
    versions: list,
    model_keys: list,
    skill_id: str,
    doc_name: str,
    widget_key: str = "results_matrix",
):
    """Render results as a styled dataframe. Cell selection drills into detail view.

    widget_key allows multiple instances on different pages without conflicts.
    """
    from engine import load_answer_key, get_version_display_name

    # Build display-name columns — exclude "external" (shown only in Score)
    display_keys = [mk for mk in model_keys if mk != "external"]
    model_names = []
    name_to_key = {}
    for mk in display_keys:
        name = MODEL_CONFIGS.get(mk, {}).get("display_name", mk)
        model_names.append(name)
        name_to_key[name] = mk

    # Build the dataframe: rows=versions, cols=model display names
    rows = []
    errors = []
    all_pcts = []
    all_secs = []
    all_costs = []

    for v in versions:
        row = {}
        pcts = []
        row_secs = []
        row_costs = []
        # Regular model columns
        for mk, name in zip(display_keys, model_names):
            r = results_map.get((v, mk))
            if r and "error" not in r:
                pct = get_cell_pct(r)
                if pct is not None:
                    secs = r.get("elapsed_seconds", 0)
                    cost = est_cost(r, mk)
                    row[name] = f"{pct:.0f}%   [{fmt_time(secs)} \u00b7 ${cost:.2f}]"
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
        # Include external result in Score computation
        ext_r = results_map.get((v, "external"))
        if ext_r and "error" not in ext_r:
            ext_pct = get_cell_pct(ext_r)
            if ext_pct is not None:
                pcts.append(ext_pct)
                row_secs.append(ext_r.get("elapsed_seconds", 0))
                row_costs.append(0)

        if pcts:
            avg_pct = sum(pcts) / len(pcts)
            max_secs = max(row_secs)
            total_cost = sum(row_costs)
            row["Score"] = f"{avg_pct:.0f}%   [{fmt_time(max_secs)} \u00b7 ${total_cost:.2f}]"
        else:
            row["Score"] = "\u2014"

        all_pcts.extend(pcts)
        all_secs.extend(row_secs)
        all_costs.extend(row_costs)
        rows.append(row)

    # Totals row
    totals_row = {}
    for name in model_names:
        m_pcts, m_secs, m_costs = [], [], []
        mk = name_to_key[name]
        for v in versions:
            r = results_map.get((v, mk))
            if r and "error" not in r:
                pct = get_cell_pct(r)
                if pct is not None:
                    m_pcts.append(pct)
                    m_secs.append(r.get("elapsed_seconds", 0))
                    m_costs.append(est_cost(r, mk))
        if m_pcts:
            totals_row[name] = f"{sum(m_pcts)/len(m_pcts):.0f}%   [{fmt_time(max(m_secs))} \u00b7 ${sum(m_costs):.2f}]"
        else:
            totals_row[name] = "\u2014"

    if all_pcts:
        totals_row["Score"] = f"{sum(all_pcts)/len(all_pcts):.0f}%   [{fmt_time(max(all_secs))} \u00b7 ${sum(all_costs):.2f}]"
    else:
        totals_row["Score"] = "\u2014"
    # Sort version rows descending by Score percentage
    def _extract_pct(cell: str) -> float:
        """Extract percentage from cell string like '94%   [1:23 · $0.18]'."""
        if isinstance(cell, str) and "%" in cell:
            try:
                return float(cell.split("%")[0])
            except ValueError:
                pass
        return -1.0

    version_rows = list(zip(versions, rows))
    version_rows.sort(key=lambda vr: _extract_pct(vr[1].get("Score", "")), reverse=True)
    sorted_versions = [v for v, _ in version_rows]
    sorted_rows = [r for _, r in version_rows]

    # Map version IDs to display names
    version_labels = [get_version_display_name(skill_id, v) for v in sorted_versions]
    # Reverse lookup: display name -> version ID (for cell click)
    version_label_to_id = dict(zip(version_labels, sorted_versions))

    # Sort model columns descending by Σ Total percentage
    model_order = sorted(model_names, key=lambda n: _extract_pct(totals_row.get(n, "")), reverse=True)
    col_order = model_order + ["Score"]

    sorted_rows.append(totals_row)
    index_labels = version_labels + ["\u03a3 Total"]

    df = pd.DataFrame(sorted_rows, index=index_labels, columns=col_order)
    df.index.name = "Version"

    # Apply conditional coloring via Pandas Styler
    summary_style = "font-weight: bold; background-color: rgba(255,255,255,0.05)"

    def _highlight_summaries(val, row_name, col_name):
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

    styled = df.style.map(score_bg).apply(_summary_style_fn, axis=None)

    # Render with cell selection enabled
    event = st.dataframe(
        styled,
        width="stretch",
        hide_index=False,
        on_select="rerun",
        selection_mode="single-cell",
        key=widget_key,
        column_config={
            "Version": st.column_config.TextColumn(label="Skill Version"),
            "Score": st.column_config.TextColumn(width="small"),
        },
    )

    # Handle cell click -> drill into detail view
    sel = event.selection if event else None
    if sel:
        cells = sel.get("cells", []) if isinstance(sel, dict) else getattr(sel, "cells", [])
        if cells:
            c = cells[0]
            if isinstance(c, dict):
                row_idx = c.get("row")
                col_val = c.get("column")
            elif isinstance(c, (list, tuple)) and len(c) >= 2:
                row_idx, col_val = c[0], c[1]
            else:
                row_idx = col_val = None

            if row_idx is not None and col_val is not None and row_idx < len(version_labels):
                col_name = col_val if isinstance(col_val, str) else (
                    model_order[col_val] if isinstance(col_val, int) and col_val < len(model_order) else None
                )
                mk = name_to_key.get(col_name) if col_name else None
                if mk:
                    label = version_labels[row_idx]
                    v = version_label_to_id.get(label)
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

    # Issue heatmap — binary checkmark/X per issue
    answer_key = load_answer_key(skill_id, doc_name)
    if not answer_key:
        return

    scored = []
    for v in versions:
        for mk in model_keys:
            r = results_map.get((v, mk))
            if r and "error" not in r and r.get("judge_scores"):
                scored.append((v, mk, r))

    if not scored:
        return

    issues = answer_key.get("issues", [])

    st.divider()
    st.markdown("### Issue Analysis")

    heatmap_models = list(dict.fromkeys(mk for _, mk, _ in scored))

    tab_labels = ["All"]
    for mk in heatmap_models:
        display = "External" if mk == "external" else MODEL_CONFIGS.get(mk, {}).get("display_name", mk)
        tab_labels.append(display)

    tabs = st.tabs(tab_labels)

    # --- "All" tab ---
    with tabs[0]:
        heatmap_rows = []
        issue_labels = []
        for issue in issues:
            iid = issue["id"]
            severity = issue.get("severity", "M")
            issue_labels.append(f"{SEVERITY_EMOJI.get(severity, '')} {issue['title']}")

            row = {}
            all_hits = []
            for mk in heatmap_models:
                model_results = [(v, r) for v, mk2, r in scored if mk2 == mk]
                hits = 0
                total = 0
                for v, r in model_results:
                    judge = r.get("judge_scores")
                    ji = judge.get("issues", {}) if judge else {}
                    hit = ji.get(iid, 0)
                    hits += hit
                    total += 1
                display = "External" if mk == "external" else MODEL_CONFIGS.get(mk, {}).get("display_name", mk)
                if total:
                    rate = hits / total * 100
                    row[display] = f"{rate:.0f}%"
                    all_hits.append(rate)
                else:
                    row[display] = "\u2014"

            avg = sum(all_hits) / len(all_hits) if all_hits else None
            row["Avg"] = f"{avg:.0f}%" if avg is not None else "\u2014"
            heatmap_rows.append(row)

        if heatmap_rows:
            heatmap_df = pd.DataFrame(heatmap_rows, index=issue_labels)
            heatmap_df.index.name = "Issue"
            st.dataframe(
                heatmap_df.style.map(score_bg, subset=["Avg"]),
                width="stretch",
                hide_index=False,
            )

    # --- Per-model tabs ---
    for tab, mk in zip(tabs[1:], heatmap_models):
        filtered = [(v, mk2, r) for v, mk2, r in scored if mk2 == mk]
        if not filtered:
            continue

        with tab:
            heatmap_rows = []
            issue_labels = []
            for issue in issues:
                iid = issue["id"]
                severity = issue.get("severity", "M")
                weight_tag = SEVERITY_LABEL.get(severity, "1x")
                issue_labels.append(f"{iid} {issue['title']}  {weight_tag}")

                row = {}
                total_hits = 0
                total_count = 0
                for v, _, r in filtered:
                    judge = r.get("judge_scores")
                    ji = judge.get("issues", {}) if judge else {}
                    hit = ji.get(iid, 0)
                    v_label = get_version_display_name(skill_id, v)
                    row[v_label] = "\u2713" if hit else "\u2717"
                    total_hits += hit
                    total_count += 1

                rate = f"{total_hits / total_count * 100:.0f}%" if total_count else "\u2014"
                row["Score"] = rate
                heatmap_rows.append(row)

            if heatmap_rows:
                heatmap_df = pd.DataFrame(heatmap_rows, index=issue_labels)
                heatmap_df.index.name = "Issue"
                st.dataframe(
                    heatmap_df.style.map(score_bg, subset=["Score"]),
                    width="stretch",
                    hide_index=False,
                )
