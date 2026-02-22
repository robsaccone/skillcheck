"""Judges page — select up to two LLM judges for evaluation grading."""

import streamlit as st
from streamlit_local_storage import LocalStorage

from judge import DEFAULT_JUDGE_SYSTEM_PROMPT, detect_self_enhancement_risk
from models import MODEL_CONFIGS, get_available_models

st.markdown("## Judges")

available = get_available_models()

if not available:
    st.warning("No models available. Add API keys to your .env file.")
    st.stop()

model_keys = list(available.keys())

st.caption(
    "Select one or two models to act as LLM judges. "
    "When two are selected, scores are aggregated via majority vote "
    "([PoLL methodology](https://arxiv.org/abs/2404.18796))."
)

col1, col2 = st.columns(2)

with col1:
    st.markdown("**Judge 1**")
    judge1 = st.selectbox(
        "Judge 1",
        options=model_keys,
        format_func=lambda k: MODEL_CONFIGS[k]["display_name"],
        label_visibility="collapsed",
        key="judge1_select",
    )

with col2:
    st.markdown("**Judge 2** (panel mode)")
    judge2_options = [None] + [k for k in model_keys if k != judge1]
    judge2 = st.selectbox(
        "Judge 2",
        options=judge2_options,
        format_func=lambda k: MODEL_CONFIGS[k]["display_name"] if k else "— None —",
        label_visibility="collapsed",
        key="judge2_select",
    )

# Persist selections in session_state for other pages
st.session_state.judge1 = judge1
st.session_state.judge2 = judge2

# Panel status indicator
panel_keys = [k for k in [judge1, judge2] if k]
if len(panel_keys) > 1:
    judge_names = [MODEL_CONFIGS.get(k, {}).get("display_name", k) for k in panel_keys]
    st.success(f"Panel mode: {' + '.join(judge_names)} (majority vote aggregation)")
    # Same-family warning
    j1_provider = MODEL_CONFIGS.get(judge1, {}).get("provider", "")
    j2_provider = MODEL_CONFIGS.get(judge2, {}).get("provider", "")
    if j1_provider and j1_provider == j2_provider:
        st.warning(
            f"Both judges are from the same provider ({j1_provider}). "
            "For best results, use judges from different model families to reduce "
            "correlated bias ([Verga et al., 2024](https://arxiv.org/abs/2404.18796))."
        )

st.divider()

col_how, col_prompt = st.columns(2, gap="large")

with col_how:
    st.markdown("**How judging works**")
    st.caption(
        "An LLM judge reads each response and grades it against the answer key "
        "— like a teacher marking an exam. The judge uses chain-of-thought reasoning "
        "before scoring ([G-Eval](https://arxiv.org/abs/2303.16634)) and binary scales "
        "for maximum reliability ([Husain, 2024](https://hamel.dev/blog/posts/llm-judge/)).\n\n"
        "**Three scoring signals:**\n\n"
        "| | |\n|---|---|\n"
        "| **Issue detection** | Binary per-issue check — did the response identify each issue? Weighted by severity (H=3x, M=2x, L=1x). |\n"
        "| **Recommendation** | Did the response reach the correct overall recommendation? (+10 pts) |\n"
        "| **False positives** | Issues flagged that aren't in the answer key. (-2 pts each) |\n\n"
        "These are combined into a single **composite score** (0–100) so you can "
        "compare results at a glance.\n\n"
        "**Anti-verbosity:** The prompt explicitly instructs the judge not to reward "
        "length, counteracting a known ~15% inflation bias "
        "([Zheng et al., 2024](https://arxiv.org/abs/2306.05685)).\n\n"
        "**Panel mode:** When two judges are selected, each scores independently "
        "and results are aggregated via majority vote — reducing individual bias "
        "and improving alignment with human judgments "
        "([Verga et al., 2024](https://arxiv.org/abs/2404.18796))."
    )

with col_prompt:
    st.markdown("**Judge Instructions**")
    st.caption(
        "The system prompt sent to the judge model when evaluating responses. "
        "Edit to adjust scoring criteria or emphasis."
    )

    # Initialize default prompt on first load (before widget renders)
    if "judge_system_prompt" not in st.session_state:
        st.session_state.judge_system_prompt = DEFAULT_JUDGE_SYSTEM_PROMPT

    judge_prompt = st.text_area(
        "Judge System Prompt",
        height=400,
        label_visibility="collapsed",
        key="judge_system_prompt",
    )

    if st.button("Reset to default", type="tertiary"):
        st.session_state.judge_system_prompt = DEFAULT_JUDGE_SYSTEM_PROMPT
        st.rerun()

# --- Research references ---
with st.expander("Research references"):
    st.markdown(
        "The judging system incorporates techniques from recent LLM-as-Judge research:\n\n"
        "- **G-Eval** (Liu et al., 2023) — Chain-of-thought reasoning before scoring "
        "improves human alignment by 10-15%. "
        "[arXiv:2303.16634](https://arxiv.org/abs/2303.16634)\n\n"
        "- **PoLL** (Verga et al., 2024) — A panel of judges from different model "
        "families correlates better with human judgments than a single large judge. "
        "[arXiv:2404.18796](https://arxiv.org/abs/2404.18796)\n\n"
        "- **Self-preference bias** (Wataoka et al., 2024) — LLMs assign higher "
        "scores to same-family outputs due to perplexity-based familiarity (~15% inflation). "
        "[arXiv:2410.21819](https://arxiv.org/abs/2410.21819)\n\n"
        "- **Verbosity bias** (Zheng et al., 2024) — Judges favor longer responses "
        "regardless of substance (~15% score inflation). "
        "[arXiv:2306.05685](https://arxiv.org/abs/2306.05685)\n\n"
        "- **Scale calibration** (Husain, 2024) — Binary/coarse scales are more "
        "reliable and reproducible than fine-grained Likert scales. "
        "[hamel.dev](https://hamel.dev/blog/posts/llm-judge/)"
    )

# --- Sync judge selections to localStorage ---
ls = LocalStorage(key="judges_storage")
ls.setItem("judge1", judge1 or "", key="save_judge1")
ls.setItem("judge2", judge2 or "", key="save_judge2")
