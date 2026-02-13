"""Skillcheck — Streamlit Dashboard.

Three-page evaluation harness for comparing AI skills on legal document analysis.
Uses st.navigation + st.Page for proper multipage routing.
"""

import streamlit as st

from config import MODEL_CONFIGS, SKILLS_DIR, get_available_models
from engine import (
    discover_skills,
    list_skill_versions,
    load_skill_version,
    list_test_docs,
    load_test_doc,
    load_answer_key,
    load_results,
    run_evaluation,
)

# ---------------------------------------------------------------------------
# Page Config & Shared CSS (entrypoint — runs on every rerun)
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Skillcheck",
    page_icon="\u26a1",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Sans:wght@400;500;700&family=JetBrains+Mono:wght@400;500&display=swap');

h1, h2, h3 { font-family: 'DM Serif Display', serif !important; }

.chip-hit { background: #065f46; color: #6ee7b7; padding: 3px 12px; border-radius: 12px; font-size: 0.82em; font-weight: 500; display: inline-block; margin: 3px 2px; }
.chip-miss { background: #7f1d1d; color: #fca5a5; padding: 3px 12px; border-radius: 12px; font-size: 0.82em; font-weight: 500; display: inline-block; margin: 3px 2px; }

.badge-critical { background: #991b1b; color: #fecaca; padding: 3px 10px; border-radius: 6px; font-weight: 700; font-size: 0.75em; text-transform: uppercase; letter-spacing: 0.03em; }
.badge-high { background: #92400e; color: #fde68a; padding: 3px 10px; border-radius: 6px; font-weight: 700; font-size: 0.75em; text-transform: uppercase; letter-spacing: 0.03em; }
.badge-moderate { background: #1e3a5f; color: #93c5fd; padding: 3px 10px; border-radius: 6px; font-weight: 700; font-size: 0.75em; text-transform: uppercase; letter-spacing: 0.03em; }

.score-green { color: #6ee7b7; font-weight: 700; }
.score-yellow { color: #fde68a; font-weight: 700; }
.score-red { color: #fca5a5; font-weight: 700; }

.score-badge { padding: 2px 8px; border-radius: 10px; font-size: 0.78em; font-weight: 700; display: inline-block; margin-left: 4px; }
.score-badge-green { background: #065f46; color: #6ee7b7; }
.score-badge-yellow { background: #92400e; color: #fde68a; }
.score-badge-red { background: #7f1d1d; color: #fca5a5; }

/* Score button base styling */
[data-testid="stColumn"] button[data-testid="stBaseButton-tertiary"] {
    border-radius: 6px !important; font-weight: 700 !important;
    padding: 1px 10px !important; border: none !important; min-height: 0 !important;
}

/* Inline model selector: name + badge on same line, left-aligned */
[data-testid="stVerticalBlock"] > div:has(.model-sel-marker) + div [data-testid="stColumn"] [data-testid="stVerticalBlock"] {
    flex-direction: row !important;
    align-items: center !important;
    gap: 8px !important;
}
[data-testid="stVerticalBlock"] > div:has(.model-sel-marker) + div [data-testid="stColumn"] [data-testid="stVerticalBlock"] > div {
    flex-shrink: 0 !important;
    width: auto !important;
}
[data-testid="stVerticalBlock"] > div:has(.model-sel-marker) + div [data-testid="stColumn"] button[data-testid="stBaseButton-tertiary"] {
    flex-shrink: 0 !important;
    width: auto !important;
    white-space: nowrap !important;
}
[data-testid="stVerticalBlock"] > div:has(.model-sel-marker) + div [data-testid="stColumn"] p {
    white-space: nowrap !important;
}
.model-sel-marker, .model-dim { display: none; }
/* Dim unselected model badges */
[data-testid="stVerticalBlock"] > div:has(.model-sel-marker) + div [data-testid="stColumn"]:has(.model-dim) button[data-testid="stBaseButton-tertiary"] {
    opacity: 0.4 !important;
}

/* Table styling marker */
.tbl-marker { display: none; }

</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SEVERITY_EMOJI = {"CRITICAL": "\U0001f534", "HIGH": "\U0001f7e0", "MODERATE": "\U0001f535", "LOW": "\u26aa"}


def severity_badge_html(severity: str) -> str:
    s = severity.lower()
    return f'<span class="badge-{s}">{severity}</span>'


def severity_prefix(severity: str) -> str:
    return SEVERITY_EMOJI.get(severity.upper(), "") + " " + severity


def detection_chip(label: str, detected: bool) -> str:
    cls = "chip-hit" if detected else "chip-miss"
    icon = "\u2705" if detected else "\u274c"
    return f'<span class="{cls}">{icon} {label}</span>'


def score_class(pct: float, max_pct: float) -> str:
    if max_pct == 0:
        return "score-yellow"
    ratio = pct / max_pct if max_pct else 0
    if ratio >= 0.7:
        return "score-green"
    elif ratio >= 0.4:
        return "score-yellow"
    return "score-red"


def score_emoji(pct: float) -> str:
    if pct >= 70:
        return "\U0001f7e2"
    elif pct >= 40:
        return "\U0001f7e1"
    return "\U0001f534"


def score_badge_html(pct: float) -> str:
    if pct >= 70:
        cls = "score-badge-green"
    elif pct >= 40:
        cls = "score-badge-yellow"
    else:
        cls = "score-badge-red"
    return f'<span class="score-badge {cls}">{pct:.0f}%</span>'


def _score_marker_cls(pct: float) -> str:
    if pct >= 70:
        return "sb-green"
    elif pct >= 40:
        return "sb-yellow"
    return "sb-red"


def score_button(container, pct: float, key: str) -> bool:
    """Render a clickable badge-styled button. Colors applied via JS injection."""
    return container.button(f"{pct:.0f}%", key=key, type="tertiary")


def score_badge_label(pct: float) -> str:
    """Return a colored circle + percentage for use as button labels."""
    if pct >= 70:
        return f"\U0001f7e2 {pct:.1f}%"
    elif pct >= 40:
        return f"\U0001f7e1 {pct:.1f}%"
    return f"\U0001f534 {pct:.1f}%"


def render_result_detail(result: dict, skill_id: str, doc_name: str):
    """Render full-width detail panel: stats left, response right."""
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
    """Render results matrix. Clicking a score drills into a full-page detail view."""
    st.markdown('<div class="tbl-marker"></div>', unsafe_allow_html=True)
    header_cols = st.columns([2] + [1] * len(model_keys), vertical_alignment="center")
    header_cols[0].markdown("**Version**")
    for i, mk in enumerate(model_keys):
        header_cols[i + 1].markdown(f"**{MODEL_CONFIGS.get(mk, {}).get('display_name', mk)}**")

    for v in versions:
        row_cols = st.columns([2] + [1] * len(model_keys), vertical_alignment="center")
        row_cols[0].markdown(v)
        for i, mk in enumerate(model_keys):
            r = results_map.get((v, mk))
            if r and "error" not in r:
                scores = r.get("auto_scores", {})
                pct = scores.get("weighted_pct", 0)
                if score_button(row_cols[i + 1], pct, f"score_{v}_{mk}"):
                    st.session_state.selected_result = (v, mk)
                    st.rerun()
            elif r and "error" in r:
                row_cols[i + 1].error("ERR")
            else:
                row_cols[i + 1].markdown("\u2014")

    # Issue heatmap — shows per-issue detection across all version×model combos
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

    TIER_LABEL = {"must_catch": "3\u00d7", "should_catch": "2\u00d7", "nice_to_catch": "1\u00d7"}

    st.divider()
    st.markdown("### Issue Analysis")

    heatmap_models = list(dict.fromkeys(mk for _, mk, _ in scored))
    all_issues_list = issues + meta_issues

    # Compute aggregate detection rate per model and per version×model
    model_agg = {}
    version_agg = {}
    for mk in heatmap_models:
        hits = 0
        total = 0
        for v, mk2, r in scored:
            if mk2 != mk:
                continue
            det = r["auto_scores"].get("issues_detected", {})
            meta_det = r["auto_scores"].get("meta_issues_detected", {})
            v_hits = 0
            v_total = 0
            for issue in all_issues_list:
                total += 1
                v_total += 1
                if det.get(issue["id"], False) or meta_det.get(issue["id"], False):
                    hits += 1
                    v_hits += 1
            version_agg[(v, mk)] = v_hits / v_total * 100 if v_total else 0
        model_agg[mk] = hits / total * 100 if total else 0

    # Model selector — inline: name + badge on same line, left-aligned
    all_issues = issues + meta_issues

    if "heatmap_model" not in st.session_state or st.session_state.heatmap_model not in heatmap_models:
        st.session_state.heatmap_model = heatmap_models[0]

    st.markdown('<div class="model-sel-marker"></div>', unsafe_allow_html=True)
    n_models = len(heatmap_models)
    sel_cols = st.columns([2] * n_models + [1], vertical_alignment="center")
    for idx, mk in enumerate(heatmap_models):
        pct = model_agg.get(mk, 0)
        display = MODEL_CONFIGS.get(mk, {}).get("display_name", mk)
        is_selected = mk == st.session_state.heatmap_model
        if is_selected:
            sel_cols[idx].markdown(f"**{display}**")
        else:
            sel_cols[idx].markdown(f'<div class="model-dim"></div><span style="opacity:0.5">{display}</span>', unsafe_allow_html=True)
        if score_button(sel_cols[idx], pct, f"hm_model_{mk}"):
            st.session_state.heatmap_model = mk
            st.rerun()

    heatmap_model = st.session_state.heatmap_model

    filtered = [(v, mk, r) for v, mk, r in scored if mk == heatmap_model]
    ncols = len(filtered)

    hdr = st.columns([3] + [1] * ncols + [1], vertical_alignment="center")
    hdr[0].markdown("**Issue**")
    for i, (v, mk, _) in enumerate(filtered):
        pct = version_agg.get((v, mk), 0)
        hdr[i + 1].markdown(v)
        score_button(hdr[i + 1], pct, f"hm_ver_{v}_{mk}")
    hdr[-1].caption("**Rate**")

    for issue in all_issues:
        iid = issue["id"]
        tier = tier_map.get(iid, "")
        tier_tag = TIER_LABEL.get(tier, "")

        row = st.columns([3] + [1] * ncols + [1], vertical_alignment="center")
        row[0].markdown(f"**{iid}** {issue['title']}  {tier_tag}")

        hit_count = 0
        for j, (v, mk, r) in enumerate(filtered):
            sc = r["auto_scores"]
            det = sc.get("issues_detected", {})
            meta_det = sc.get("meta_issues_detected", {})
            detected = det.get(iid, False) or meta_det.get(iid, False)
            row[j + 1].markdown("\u2705" if detected else "\u274c")
            if detected:
                hit_count += 1

        rate = hit_count / ncols * 100 if ncols else 0
        score_button(row[-1], rate, f"hm_rate_{iid}")

    # Apply table borders + score button colors via JS
    import streamlit.components.v1 as components
    components.html("""<script>
    setTimeout(() => {
        const doc = parent.document;
        // Table row borders
        doc.querySelectorAll('.tbl-marker').forEach(m => {
            let sib = m.closest('[data-testid="stElementContainer"]').nextElementSibling;
            while (sib) {
                if (sib.getAttribute('data-testid') === 'stLayoutWrapper') {
                    const hb = sib.querySelector('[data-testid="stHorizontalBlock"]');
                    if (hb) {
                        hb.style.borderBottom = '1px solid rgba(255,255,255,0.15)';
                        hb.style.paddingBottom = '4px';
                        hb.style.marginBottom = '2px';
                    }
                }
                sib = sib.nextElementSibling;
            }
        });
        // Color score buttons by their percentage text
        doc.querySelectorAll('[data-testid="stColumn"] button[data-testid="stBaseButton-tertiary"]').forEach(btn => {
            const m = btn.textContent.trim().match(/^(\\d+)%$/);
            if (!m) return;
            const pct = parseInt(m[1]);
            let bg, fg;
            if (pct >= 70) { bg = '#065f46'; fg = '#6ee7b7'; }
            else if (pct >= 40) { bg = '#92400e'; fg = '#fde68a'; }
            else { bg = '#7f1d1d'; fg = '#fca5a5'; }
            btn.style.background = bg;
            btn.style.color = fg;
        });
    }, 100);
    </script>""", height=0)


# ---------------------------------------------------------------------------
# Page: Skills
# ---------------------------------------------------------------------------

def page_skills():
    st.markdown("## Skills Library")

    skills = discover_skills()
    if not skills:
        st.info("No skills found. Add skill directories with skill.json to the skills/ folder.")
        return

    for skill in skills:
        skill_id = skill["skill_id"]
        with st.expander(
            f"**{skill['display_name']}** — {skill.get('description', '')}  "
            f"({skill['version_count']} versions, {skill['doc_count']} docs)",
            expanded=False,
        ):
            # Versions
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


# ---------------------------------------------------------------------------
# Page: Models
# ---------------------------------------------------------------------------

def page_models():
    st.markdown("## Models")

    available = get_available_models()

    table_data = []
    for key, cfg in MODEL_CONFIGS.items():
        has_key = key in available
        table_data.append({
            "Model": cfg["display_name"],
            "Provider": cfg["provider"].capitalize(),
            "Model ID": cfg["model_id"],
            "API Key Env": cfg["env_key"],
            "Status": "\u2705 Available" if has_key else "\u26aa Unavailable",
        })

    st.dataframe(table_data, width="stretch", hide_index=True)

    if not available:
        st.warning("No API keys configured. Add keys to your .env file to enable models.")


# ---------------------------------------------------------------------------
# Page: Evaluate
# ---------------------------------------------------------------------------

def page_evaluate():
    # Full-page detail view when a result is selected
    sel = st.session_state.get("selected_result")
    if sel:
        results_src = st.session_state.get("eval_results") or {}
        results_map = results_src.get("results", {})
        # Also check disk results
        if not results_map:
            skill_id = results_src.get("skill_id", sel[2] if len(sel) > 2 else "")
            from engine import load_results as _lr
            for r in _lr(skill_id):
                v, mk = r.get("version", ""), r.get("model_key", "")
                if v and mk:
                    results_map[(v, mk)] = r
        v, mk = sel
        r = results_map.get((v, mk))
        if r and "error" not in r:
            skill_id = results_src.get("skill_id", r.get("skill_id", ""))
            doc_name = results_src.get("doc", r.get("doc_name", ""))
            render_result_page(r, v, mk, skill_id, doc_name)
            return
        else:
            del st.session_state.selected_result

    st.markdown("## Evaluate")

    skills = discover_skills()
    available = get_available_models()

    if not skills:
        st.info("No skills found.")
        return

    if not available:
        st.warning("No models available. Add API keys to your .env file.")
        return

    running = st.session_state.get("eval_running", False)

    # Controls — disabled while running
    skill_map = {s["skill_id"]: s["display_name"] for s in skills}
    model_options = list(available.keys())

    col1, col2, col3 = st.columns(3)

    with col1:
        selected_models = st.multiselect(
            "Select Models",
            options=model_options,
            default=model_options[:2] if len(model_options) >= 2 else model_options,
            format_func=lambda k: MODEL_CONFIGS[k]["display_name"],
            disabled=running,
            key="eval_models",
        )

    with col2:
        selected_skill = st.selectbox(
            "Select Skill",
            options=list(skill_map.keys()),
            format_func=lambda k: skill_map[k],
            disabled=running,
            key="eval_skill",
        )

    with col3:
        docs = list_test_docs(selected_skill)
        if docs:
            selected_doc = st.selectbox(
                "Select Document",
                options=docs,
                disabled=running,
                key="eval_doc",
            )
        else:
            st.selectbox("Select Document", options=[], disabled=True, key="eval_doc_empty")
            st.caption("No test documents for this skill.")
            selected_doc = None

    # Prompt input — inline text field; Enter submits
    can_run = selected_doc and len(selected_models) >= 2

    def _on_prompt_submit():
        val = st.session_state.get("eval_prompt_input", "").strip()
        if val and can_run and not running:
            st.session_state.eval_running = True
            st.session_state.eval_run_skill = selected_skill
            st.session_state.eval_run_models = selected_models
            st.session_state.eval_run_doc = selected_doc
            st.session_state.eval_prompt = val
            st.session_state.eval_prompt_input = ""

    prompt_col, btn_col = st.columns([6, 1], vertical_alignment="bottom")
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
        use_container_width=True,
    )

    # Button click also triggers run
    if run_clicked and can_run and not running:
        prompt_val = st.session_state.get("eval_prompt_input", "").strip() or "run"
        st.session_state.eval_running = True
        st.session_state.eval_run_skill = selected_skill
        st.session_state.eval_run_models = selected_models
        st.session_state.eval_run_doc = selected_doc
        st.session_state.eval_prompt = prompt_val
        st.session_state.eval_prompt_input = ""
        st.rerun()

    versions = list_skill_versions(selected_skill)

    # --- Running: execute evaluations with progress ---
    if running:
        run_skill = st.session_state.eval_run_skill
        run_models = st.session_state.eval_run_models
        run_doc = st.session_state.eval_run_doc
        run_versions = list_skill_versions(run_skill)
        total = len(run_versions) * len(run_models)

        progress = st.progress(0, text="Starting evaluation...")
        completed = 0
        results_map = {}

        for version, model_key, result in run_evaluation(run_skill, run_models, run_doc):
            completed += 1
            results_map[(version, model_key)] = result
            progress.progress(
                completed / total,
                text=f"{completed}/{total} — {version} x {MODEL_CONFIGS[model_key]['display_name']}",
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
            # Fall back to saved results on disk
            existing = load_results(selected_skill)
            if existing and versions:
                st.markdown("### Results")
                matrix = {}
                model_keys_seen = set()
                for r in existing:
                    v = r.get("version", "")
                    mk = r.get("model_key", "")
                    if v and mk:
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


# ---------------------------------------------------------------------------
# Navigation (entrypoint router)
# ---------------------------------------------------------------------------

pg = st.navigation([
    st.Page(page_skills, title="Skills", icon=":material/description:"),
    st.Page(page_models, title="Models", icon=":material/smart_toy:"),
    st.Page(page_evaluate, title="Evaluate", icon=":material/play_circle:", default=True),
])

with st.sidebar:
    st.markdown("---")
    st.caption("Skillcheck \u00b7 Built by Rob Saccone \u00b7 NexLaw Partners")

pg.run()
