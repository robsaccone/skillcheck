# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the App

```bash
streamlit run app.py          # standard
run.bat                       # Windows shortcut
run.bat --fast                # disables file watcher and reduces logging
```

The app runs at `http://localhost:8501`. Requires Python 3.12+ and at least one API key in `.env` (see `.env.example`).

## Architecture

Streamlit multi-page app that evaluates AI models on legal document analysis using structured "skills" (prompt templates + expert answer keys).

**Core data flow:**
1. **Discovery** (`engine.py`) — scans `skills/` filesystem for `skill.json` + `*.skill.md` versions + `tests/*.json` answer keys
2. **Prompt construction** (`engine.py:build_prompt`) — system = `system_prompt_prefix` + skill version text; user = template with `{document}` and `{business_context}`
3. **Parallel evaluation** (`engine.py:run_evaluation`) — ThreadPoolExecutor(8) runs all (version × model) combos, dispatching through `models.py:call_model` to provider-specific functions
4. **Judge scoring** (`judge.py`) — sends doc + answer_key + response to a judge LLM, parses structured JSON, computes composite score
5. **Result persistence** — JSON files at `results/{skill_id}/{version}/{model}__{doc}.json`

**Key modules:**
- `config.py` — paths, scoring constants (`SEVERITY_WEIGHTS`, `RECOMMENDATION_BONUS`, `FP_PENALTY_PER`)
- `models.py` — `MODEL_CONFIGS` dict + `call_model()` dispatcher (Anthropic, OpenAI, Google, Together)
- `engine.py` — orchestration: discovery, prompts, parallel eval, result I/O
- `judge.py` — LLM-as-judge pipeline: prompt → call → parse JSON → composite score
- `streaming.py` — provider-specific streaming generators (separate from `call_model` due to different API patterns)
- `components.py` — shared UI constants (`SEVERITY_LABEL`, `SEVERITY_EMOJI`) and `est_cost()`

## Scoring System

Three signals: **recommendation match** (+10 pts), **weighted issue hit rate** (0-100, severity H=3×/M=2×/L=1×), **false positive penalty** (-3 pts each).

`composite = weighted_hit_rate + rec_bonus - fp_penalty`, clamped [0,100], stored as 0.0–1.0.

Judge output format: binary per-issue detection (0/1), recommendation match, false positive count + list.

## Skill Format

Skills are filesystem-driven — no code changes needed to add new ones:
- `skills/{id}/skill.json` — metadata with `user_prompt_template` (uses `{document}`, `{business_context}`)
- `skills/{id}/*.skill.md` — prompt versions (each is a complete methodology document)
- `skills/{id}/tests/*.md` — test documents; `*.json` — answer keys with `issues[]` (id, section, title, severity H/M/L, description, rubric), `business_context`, `expected_recommendation`, optional `false_positive_traps[]`, `scoring_notes`
- Meta-issues (structural patterns) are merged into the `issues` array with `META-` prefixed IDs and severity `"H"`

## Code Conventions

- All functions, no classes. Section headers use `# ---...---` comment blocks.
- Python 3.12+ type hints (`str | None`, `list[dict]`).
- API clients are lazily imported inside functions to avoid import errors when keys are missing.
- Streamlit pages are standalone scripts with module-level code.
- `st.session_state` for cross-page state; `streamlit-local-storage` for browser-persistent selections.
- The `pages/evaluate.py` page is the main workspace (~660 lines) — handles run control, live results table, issue heatmap, and drill-down routing.

## Adding Models

Add an entry to `MODEL_CONFIGS` in `models.py`. Any OpenAI-compatible API can use the Together pattern (OpenAI client + custom `base_url`). Each entry needs: `provider`, `model_id`, `display_name`, `env_key`, `cost_in`, `cost_out`, `context_k`.
