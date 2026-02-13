# Skillcheck

**An evaluation harness that measures which AI "skills" actually perform best on legal document analysis.**

Skills — structured prompts that tell AI models how to do a specific job — are proliferating across the legal AI ecosystem. Anthropic ships them, indie developers publish them, startups sell them. But which ones actually work? Does a 2,500-token methodology outperform a 130-word sticky note? Does either beat a bare prompt?

Skillcheck answers these questions with data. Pick a task, pick your models, pick your skills, and run a controlled bake-off against an expert answer key.

---

## What It Does

Skillcheck runs AI models through legal document review tasks with different skills and scores the results against expert-graded answer keys. Every prompt is a skill — from a bare "review this NDA" to a 2,500-token methodology built on academic benchmarks. It measures:

- **Issue detection** — Did the model find what a senior attorney would find?
- **Skill comparison** — Which skill produces the best work product on which model?
- **Model comparison** — How do frontier, mid-tier, and open-source models stack up on the same task with the same playbook?

The first evaluation pack is **NDA Review**: a deliberately one-sided "mutual" NDA with 16 planted issues across three severity tiers. More packs can be added without code changes.

## Quick Start

```bash
git clone https://github.com/rsaccone/skillcheck.git
cd skillcheck
pip install -r requirements.txt

# Add your API keys
cp .env.example .env
# Edit .env with your keys (any subset works — models without keys are skipped)

# Fetch the latest skills from their open-source repos
python fetch_skills.py

# Launch the dashboard
streamlit run app.py
```

The dashboard opens at `http://localhost:8501`. You can run evaluations with whichever API keys you have configured — models without keys are grayed out but the app still works.

## Supported Models

| Model | Provider | API Key |
|-------|----------|---------|
| Claude Opus 4.6 | Anthropic | `ANTHROPIC_API_KEY` |
| Claude Sonnet 4.5 | Anthropic | `ANTHROPIC_API_KEY` |
| GPT-4o | OpenAI | `OPENAI_API_KEY` |
| Gemini 2.5 Pro | Google | `GOOGLE_API_KEY` |
| Llama 3.3 70B | Meta (via Together) | `TOGETHER_API_KEY` |

## Included Skills

Skills are organized by task type, with one file per source:

| Skill | Source | Tokens | License |
|-------|--------|--------|---------|
| `nda_review/baseline` | Skillcheck | ~20 | MIT |
| `nda_review/lawvable` | [Lawvable](https://github.com/lawvable/awesome-legal-skills) | ~170 | AGPL-3.0 |
| `nda_review/evolsb` | [evolsb](https://github.com/evolsb/claude-legal-skill) | ~2,500 | MIT |
| `nda_review/skala` | [Skala](https://www.skala.io/legal-skills) | ~800 | See source |
| `nda_review/custom` | Skillcheck | ~1,200 | MIT |
| `nda_triage/anthropic` | [Anthropic](https://github.com/anthropics/knowledge-work-plugins) | ~480 | Apache-2.0 |
| `contract_review/anthropic` | [Anthropic](https://github.com/anthropics/knowledge-work-plugins) | ~600 | Apache-2.0 |
| `contract_review/evolsb` | [evolsb](https://github.com/evolsb/claude-legal-skill) | ~2,500 | MIT |

## The Dashboard

Skillcheck ships as a Streamlit app with five views:

**Run Evaluation** — Pick a model, skill, and test document. Run a review and see auto-scored results with issue-by-issue detection chips.

**Side-by-Side Compare** — Select any two results and compare scores, issue detection, and full response text in parallel.

**Scorecard** — Leaderboard of all runs sorted by weighted score. Includes skill comparison across models and manual expert scoring.

**Skill Viewer** — Read the full text of any skill with provenance info. Compare two skills side-by-side.

**Test Documents & Answer Keys** — Browse the test NDA and expert answer key with severity badges and "what good looks like" for each issue.

## How Scoring Works

Each test document has an expert answer key with issues classified into three tiers:

| Tier | Weight | Standard |
|------|--------|----------|
| **Must-catch** | 3× | Miss these and you've committed malpractice |
| **Should-catch** | 2× | A competent reviewer finds these |
| **Nice-to-catch** | 1× | Senior associates and partners catch these |

Auto-scoring uses keyword detection from the answer key. It's conservative — it can miss a valid detection but rarely produces false positives. Manual expert scoring covers five qualitative dimensions: completeness, precision, accuracy, actionability, and professional judgment.

## Project Structure

```
skillcheck/
├── app.py                          # Streamlit dashboard
├── engine.py                       # API dispatch, scoring, results
├── config.py                       # Model configs
├── fetch_skills.py                 # Pull skills from source repos
├── requirements.txt
├── .env.example
│
├── eval_packs/                     # Self-contained evaluation packs
│   └── nda_review/
│       ├── pack.json
│       ├── test_docs/
│       │   └── one_sided_mutual.md
│       └── answer_keys/
│           └── one_sided_mutual.json
│
├── skills/                         # Organized by skill type, named by source
│   ├── _catalog.json
│   ├── nda_review/
│   │   ├── baseline.skill.md       # Minimal prompt — the control
│   │   ├── lawvable.skill.md
│   │   ├── evolsb.skill.md
│   │   ├── skala.skill.md
│   │   └── custom.skill.md
│   ├── nda_triage/
│   │   └── anthropic.skill.md
│   └── contract_review/
│       ├── anthropic.skill.md
│       └── evolsb.skill.md
│
└── results/                        # Mirrors skills structure
    └── nda_review/
        ├── nda_review/
        │   ├── baseline/
        │   ├── lawvable/
        │   ├── evolsb/
        │   └── ...
```

## Adding Your Own Eval Pack

Skillcheck is designed to be extended. To add a new evaluation:

1. Create a directory under `eval_packs/` with a `pack.json`, test documents, and answer keys
2. Add relevant skills to the `skills/` directory
3. Update `skills/_catalog.json` with the new skill metadata
4. Restart the app — your pack appears in the sidebar

See the [technical spec](docs/technical_spec.md) for data model details.

## Adding Your Own Skills

Drop a `{source}.skill.md` file into the appropriate `skills/{type}/` directory and add an entry to `_catalog.json`. The skill text is injected as system prompt context during evaluation.

## Background

This project grew out of an analysis of the emerging legal AI skills ecosystem — comparing catalogs from [Lawvable](https://github.com/lawvable/awesome-legal-skills), [Anthropic](https://github.com/anthropics/knowledge-work-plugins), [AgentSkills.legal](https://agentskills.legal), and others. The evaluation harness was built to answer a simple question: when multiple skills claim to improve AI performance on the same legal task, which one actually produces the best work product?

For the full show script and production notes, see [docs/show_overview.md](docs/show_overview.md).

## Contributing

Contributions welcome — especially new eval packs, test documents, and answer keys. The more tasks we can evaluate, the better we can hold legal AI tools accountable.

If you build an eval pack, please open a PR. If you find issues with the scoring methodology or answer keys, file an issue.

## License

MIT — see [LICENSE](LICENSE).

Skills included in this repo retain their original licenses as noted in `skills/_catalog.json`. The evaluation harness, test documents, answer keys, and custom skills are MIT licensed.

## Author

**Rob Saccone** · [NexLaw Partners](https://nexlawpartners.com) · [@rsaccone](https://github.com/rsaccone)

25+ years in legal technology. Previously CTO/co-founder at Lega, founder of XMLAW (acquired by Thomson Reuters), CEO of SeyfarthLean Consulting.
