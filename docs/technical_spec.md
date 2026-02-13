# Skillcheck — Technical Specification

## Purpose

Build a Streamlit-based evaluation harness that measures how well AI "skills" (structured prompts/instructions) improve model performance on legal document analysis tasks. The harness should be **domain-general** — NDA review is the first evaluation pack, but the architecture must support adding new packs (e.g., contract review, deposition prep, compliance analysis) without code changes.

The project is called **Skillcheck**.

---

## Architecture Overview

```
skillcheck/
├── app.py                          # Streamlit dashboard (main entry)
├── engine.py                       # API dispatch, scoring, result management
├── config.py                       # Model configs, constants
├── requirements.txt
├── .env.example                    # Template for API keys
│
├── eval_packs/                     # Each subdirectory is a self-contained evaluation
│   └── nda_review/
│       ├── pack.json               # Pack metadata, prompts, scoring config
│       ├── test_docs/              # Source documents to evaluate against
│       │   └── one_sided_mutual.md
│       └── answer_keys/            # Expert answer keys (1:1 with test_docs)
│           └── one_sided_mutual.json
│
├── skills/                         # Skills library — organized by SKILL TYPE
│   ├── _catalog.json               # Master catalog of all skills with provenance
│   ├── nda_review/                 # All NDA review skills, one per source
│   │   ├── baseline.skill.md       # Minimal prompt — the control
│   │   ├── lawvable.skill.md
│   │   ├── evolsb.skill.md
│   │   ├── skala.skill.md
│   │   └── custom.skill.md
│   ├── nda_triage/                 # NDA triage / intake skills
│   │   └── anthropic.skill.md
│   └── contract_review/            # General contract review skills
│       ├── anthropic.skill.md
│       └── evolsb.skill.md
│
└── results/                        # Mirrors skills structure
    └── nda_review/                 # Results for the nda_review eval pack
        ├── nda_review/             # Results grouped by skill type
        │   ├── baseline/           # Minimal prompt — the control, not a special case
        │   │   ├── claude-opus-4-6__one_sided_mutual.json
        │   │   ├── gpt-4o__one_sided_mutual.json
        │   │   └── ...
        │   ├── lawvable/
        │   ├── anthropic/
        │   ├── evolsb/
        │   ├── skala/
        │   └── custom/
        ├── nda_triage/
        │   └── anthropic/
        └── contract_review/
            ├── anthropic/
            └── evolsb/
```

### Key Design Principles

**Every prompt is a skill.** There is no "baseline" vs. "with skill" distinction. A bare prompt like "Review this NDA and identify any issues" is just the laziest skill. It lives in `skills/nda_review/baseline.skill.md` and is scored identically to everything else. The question isn't "does a skill help?" — it's "which skill does this job best?"

**Skills are organized by what they do, then by who made them.** The folder `skills/nda_review/` contains every NDA review skill from every source. The filename `lawvable.skill.md` tells you who made it. This makes it trivial to compare competing skills for the same task.

**Results mirror the skills structure.** If the skill lives at `skills/nda_review/lawvable.skill.md`, its results live at `results/{pack}/nda_review/lawvable/{model}__{doc}.json`. The file system itself is browsable as a comparison tool.

**Evaluation packs are self-contained.** Each pack declares what documents to test, what the answer keys are, which skill types are relevant, and how to score results.

**Skills are independent of packs.** They live in `skills/` tagged with types. When you select an eval pack, the UI filters to show relevant skill types but allows selecting any skill.

---

## Naming Conventions

| Thing | Pattern | Example |
|-------|---------|---------|
| Skill file | `skills/{skill_type}/{source}.skill.md` | `skills/nda_review/lawvable.skill.md` |
| Skill ID | `{skill_type}/{source}` | `nda_review/lawvable` |
| Result file | `results/{pack}/{skill_type}/{source}/{model}__{doc}.json` | `results/nda_review/nda_review/lawvable/claude-opus-4-6__one_sided_mutual.json` |
| Test doc | `eval_packs/{pack}/test_docs/{doc}.md` | `eval_packs/nda_review/test_docs/one_sided_mutual.md` |
| Answer key | `eval_packs/{pack}/answer_keys/{doc}.json` | `eval_packs/nda_review/answer_keys/one_sided_mutual.json` |

---

## Data Models

### pack.json

```json
{
  "pack_id": "nda_review",
  "display_name": "NDA Review",
  "description": "Evaluates AI performance on Non-Disclosure Agreement review tasks.",
  "relevant_skill_types": ["nda_review", "nda_triage", "contract_review"],
  "default_perspective": "Recipient",
  "test_docs": ["one_sided_mutual.md"],
  "system_prompt_prefix": "You are an experienced corporate attorney reviewing a Non-Disclosure Agreement. Provide a thorough, structured review identifying all risks, issues, and recommended changes.",
  "user_prompt_template": "I represent the {perspective} party in the following agreement. Please review this document and identify all issues, risks, and recommended changes.\n\n---\n\n{document}"
}
```

### Skills Catalog (_catalog.json)

```json
{
  "skills": [
    {
      "skill_id": "nda_review/baseline",
      "skill_type": "nda_review",
      "source": "baseline",
      "display_name": "Baseline — Minimal Prompt",
      "source_org": "Skillcheck",
      "source_url": null,
      "license": "MIT",
      "path": "nda_review/baseline.skill.md",
      "token_estimate": 20,
      "notes": "Bare-minimum prompt. The control — not a special case, just the laziest skill."
    },
    {
      "skill_id": "nda_review/lawvable",
      "skill_type": "nda_review",
      "source": "lawvable",
      "display_name": "Lawvable — NDA Reviewer",
      "source_org": "Lawvable / awesome-legal-skills",
      "source_url": "https://github.com/lawvable/awesome-legal-skills",
      "license": "AGPL-3.0",
      "path": "nda_review/lawvable.skill.md",
      "token_estimate": 170,
      "notes": "Minimal 5-step procedure + 4 guidelines. Illustrative example from their README. The actual repo skill in the 🌐 directory may be more detailed — fetch full version if accessible."
    },
    {
      "skill_id": "nda_triage/anthropic",
      "skill_type": "nda_triage",
      "source": "anthropic",
      "display_name": "Anthropic — NDA Triage",
      "source_org": "Anthropic / knowledge-work-plugins",
      "source_url": "https://github.com/anthropics/knowledge-work-plugins/blob/main/legal/skills/nda-triage/SKILL.md",
      "license": "Apache-2.0",
      "path": "nda_triage/anthropic.skill.md",
      "token_estimate": 480,
      "notes": "GREEN/YELLOW/RED categorization. Designed for intake triage, not deep review. Part of the Cowork legal plugin."
    },
    {
      "skill_id": "contract_review/anthropic",
      "skill_type": "contract_review",
      "source": "anthropic",
      "display_name": "Anthropic — Contract Review",
      "source_org": "Anthropic / knowledge-work-plugins",
      "source_url": "https://github.com/anthropics/knowledge-work-plugins/blob/main/legal/skills/contract-review/SKILL.md",
      "license": "Apache-2.0",
      "path": "contract_review/anthropic.skill.md",
      "token_estimate": 600,
      "notes": "Generic contract review with playbook integration. Not NDA-specific but applicable. Part of the Cowork legal plugin."
    },
    {
      "skill_id": "nda_review/evolsb",
      "skill_type": "nda_review",
      "source": "evolsb",
      "display_name": "evolsb — Legal Contract Review",
      "source_org": "evolsb/claude-legal-skill",
      "source_url": "https://github.com/evolsb/claude-legal-skill/blob/main/skill.md",
      "license": "MIT",
      "path": "nda_review/evolsb.skill.md",
      "token_estimate": 2500,
      "notes": "Most technically sophisticated. Built on CUAD dataset (41 risk categories) and ContractEval benchmarks. Party-aware, leverage-aware, contract-type-aware. Author reports F1 ~0.62 on clause extraction. Also applicable to SaaS, M&A, and other contract types."
    },
    {
      "skill_id": "contract_review/evolsb",
      "skill_type": "contract_review",
      "source": "evolsb",
      "display_name": "evolsb — Legal Contract Review",
      "source_org": "evolsb/claude-legal-skill",
      "source_url": "https://github.com/evolsb/claude-legal-skill/blob/main/skill.md",
      "license": "MIT",
      "path": "contract_review/evolsb.skill.md",
      "token_estimate": 2500,
      "notes": "Same skill as nda_review/evolsb — it covers multiple contract types. Symlinked or duplicated here for discoverability under contract_review."
    },
    {
      "skill_id": "nda_review/skala",
      "skill_type": "nda_review",
      "source": "skala",
      "display_name": "Skala — NDA Review",
      "source_org": "Skala.io Legal Skills",
      "source_url": "https://www.skala.io/legal-skills",
      "license": "Unknown — check source",
      "path": "nda_review/skala.skill.md",
      "token_estimate": 800,
      "notes": "Designed for startups. Compares against standard templates. Needs to be fetched from Skala's platform or reconstructed from their public descriptions."
    },
    {
      "skill_id": "nda_review/custom",
      "skill_type": "nda_review",
      "source": "custom",
      "display_name": "Custom — Comprehensive NDA Review",
      "source_org": "Skillcheck (custom-built)",
      "source_url": null,
      "license": "MIT",
      "path": "nda_review/custom.skill.md",
      "token_estimate": 1200,
      "notes": "Built for this evaluation. 9-section analysis framework with structured output. Composite of evolsb's approach, Anthropic's structure, and expert NDA review practices."
    }
  ]
}
```

### Answer Key (per test document)

```json
{
  "doc_id": "one_sided_mutual",
  "doc_title": "One-Sided 'Mutual' NDA — Acme Technologies",
  "perspective": "Recipient / Counter-party to Acme",
  "overall_risk": "RED",
  "overall_risk_rationale": "Labeled 'Mutual' but one-sided in drafter's favor on every material term.",

  "scoring_guidance": {
    "must_catch": ["ISSUE-01", "ISSUE-02", "ISSUE-09", "ISSUE-11", "ISSUE-12", "ISSUE-13"],
    "should_catch": ["ISSUE-03", "ISSUE-05", "ISSUE-06", "ISSUE-08", "ISSUE-10"],
    "nice_to_catch": ["ISSUE-04", "ISSUE-07", "ISSUE-14", "ISSUE-15", "ISSUE-16"],
    "weights": { "must_catch": 3, "should_catch": 2, "nice_to_catch": 1 }
  },

  "issues": [
    {
      "id": "ISSUE-01",
      "section": "2.1 / 2.2",
      "title": "Asymmetric Definition of Confidential Information",
      "severity": "CRITICAL",
      "description": "Acme's CI needs no marking. Recipient's requires written marking plus 5-day written summary for oral disclosures.",
      "what_good_looks_like": "Identifies the asymmetry, explains why it matters, recommends symmetric treatment.",
      "detection_keywords": [
        "asymmetric definition", "marking requirement",
        "oral disclosure", "written summary",
        "5 business days", "five business days",
        "definition of confidential"
      ]
    }
  ],

  "meta_issues": [
    {
      "id": "META-01",
      "title": "Structural Asymmetry Pattern",
      "description": "Labeled 'Mutual' but one-sided on every material term.",
      "detection_keywords": ["one-sided", "asymmetric", "mutual in name only", "not truly mutual"]
    }
  ]
}
```

Note: `detection_keywords` live in the answer key, not the engine. This makes scoring logic fully generic.

### Result File

```json
{
  "eval_id": "uuid",
  "pack_id": "nda_review",
  "doc_id": "one_sided_mutual",
  "model_key": "claude-opus-4-6",
  "model_name": "Claude Opus 4.6",
  "skill_id": "nda_review/lawvable",
  "skill_name": "Lawvable — NDA Reviewer",
  "timestamp": "2026-02-13T14:30:00Z",

  "response_text": "...",
  "input_tokens": 3200,
  "output_tokens": 4100,
  "elapsed_seconds": 18.4,

  "auto_scores": {
    "issues_detected": { "ISSUE-01": true, "ISSUE-02": true },
    "meta_issues_detected": { "META-01": true },
    "total_found": 12,
    "total_possible": 16,
    "recall_pct": 75.0,
    "must_catch": { "found": 6, "total": 6 },
    "should_catch": { "found": 4, "total": 5 },
    "nice_to_catch": { "found": 2, "total": 5 },
    "weighted_score": 32,
    "weighted_max": 43,
    "weighted_pct": 74.4
  },

  "manual_scores": {
    "completeness": null,
    "precision": null,
    "accuracy": null,
    "actionability": null,
    "judgment": null
  },

  "notes": ""
}
```

Saved to: `results/nda_review/nda_review/lawvable/claude-opus-4-6__one_sided_mutual.json`

---

## Model Configuration

```python
MODEL_CONFIGS = {
    "claude-opus-4-6": {
        "provider": "anthropic",
        "model_id": "claude-opus-4-6",
        "display_name": "Claude Opus 4.6",
        "env_key": "ANTHROPIC_API_KEY",
    },
    "claude-sonnet-4-5": {
        "provider": "anthropic",
        "model_id": "claude-sonnet-4-5-20250929",
        "display_name": "Claude Sonnet 4.5",
        "env_key": "ANTHROPIC_API_KEY",
    },
    "gpt-4o": {
        "provider": "openai",
        "model_id": "gpt-4o",
        "display_name": "GPT-4o",
        "env_key": "OPENAI_API_KEY",
    },
    "gemini-2.5-pro": {
        "provider": "google",
        "model_id": "gemini-2.5-pro-preview-06-05",
        "display_name": "Gemini 2.5 Pro",
        "env_key": "GOOGLE_API_KEY",
    },
    "llama-3.3-70b": {
        "provider": "together",
        "model_id": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
        "display_name": "Llama 3.3 70B",
        "env_key": "TOGETHER_API_KEY",
    },
}
```

Provider dispatch for Together uses the OpenAI-compatible API at `https://api.together.xyz/v1`.

---

## Engine (engine.py)

### Core Functions

**`discover_packs()`** — Scans `eval_packs/` for directories containing `pack.json`. Returns list of pack configs.

**`discover_skills(skill_types=None)`** — Reads `skills/_catalog.json`. Optionally filters by `skill_type`. Returns skill catalog entries.

**`load_skill(skill_id)`** — Given a skill_id like `nda_review/lawvable`, reads `skills/nda_review/lawvable.skill.md` and returns the text content.

**`build_prompt(pack, doc_text, skill_text=None, perspective=None)`** — Constructs system and user prompts. If skill_text is provided, it's appended to the system prompt after the pack's `system_prompt_prefix`. The user prompt uses the pack's `user_prompt_template` with `{document}` and `{perspective}` substituted.

**`call_model(provider, model_id, system, user, max_tokens=8192)`** — Dispatches to the correct API client. Returns `{ text, input_tokens, output_tokens, elapsed_seconds }`.

Provider implementations:
- `anthropic` — `anthropic.Anthropic().messages.create()`
- `openai` — `openai.OpenAI().chat.completions.create()`
- `google` — `google.generativeai.GenerativeModel().generate_content()`
- `together` — OpenAI client with `base_url="https://api.together.xyz/v1"`

**`auto_score(response_text, answer_key)`** — Generic keyword-based scoring. For each issue in the answer key, checks if ANY of its `detection_keywords` appear in the lowercased response. Returns `{ issue_id: bool }` dict. Also checks `meta_issues`.

**`compute_weighted_scores(issues_detected, answer_key)`** — Takes the `auto_score` output and computes weighted totals using the answer key's `scoring_guidance`. Returns the `auto_scores` block for the result file.

**`save_result(result)`** — Derives the output path from `result['pack_id']`, `result['skill_id']`, and `result['model_key']`. Creates directories as needed.

**`load_results(pack_id=None, skill_type=None, source=None)`** — Walks the `results/` directory tree. Optionally filters by pack, skill type, or source. Returns list of result dicts.

**`get_available_models()`** — Returns models whose API keys are present in the environment.

### Batch Runner

**`run_batch(pack_id, doc_id, model_keys, skill_ids, perspective=None)`** — Runs all combinations of models × skills for a given document. Yields results as they complete. Used by the "Run All" button.

---

## Streamlit App (app.py)

### Page Title & Branding

Title: "Skillcheck" with a subtle subtitle per eval pack. Page icon: ✓ or ⚡.

### Layout

Dark theme. DM Serif Display for headings, DM Sans for body, JetBrains Mono for code/data. Color palette: dark navy background (#0a0f1c), indigo accents (#6366f1), severity colors (red #ef4444, amber #f59e0b, green #10b981, blue #3b82f6).

### Sidebar

- **Eval Pack selector** — dropdown of discovered packs
- **Available models** — shows which API keys are configured (green check vs. gray)
- **Attribution footer** — "Skillcheck · Built by Rob Saccone · NexLaw Partners"

### Tab 1: 🚀 Run Evaluation

Three-column selector:
- **Model** — from MODEL_CONFIGS, grayed out if no API key
- **Skill** — filtered by pack's `relevant_skill_types` (baseline is just another skill in the list)
- **Test Document** — from pack's `test_docs`

"Run" button — calls engine, auto-scores, saves result, shows:
- Metric cards: weighted %, issues found, must-catch score
- Issue detection chips (green = hit, red = miss)
- Expandable full response text

"Run All Combinations" button — iterates all available models × all relevant skills × all docs. Progress bar. Saves all results.

### Tab 2: 🔍 Side-by-Side Compare

Two dropdowns to select any two saved results (labeled as "Model + Skill"). Shows:
- Score comparison metrics with deltas
- Issue-by-issue comparison table (✅/❌ grid with severity column)
- Full response text in two columns with timing and token counts

### Tab 3: 📊 Scorecard

Summary table sorted by weighted score. Columns: Model, Skill (showing `{type}/{source}`), Weighted %, Issues Found, Must-Catch, Should-Catch, Nice-to-Catch, Time (s), Tokens Out.

Horizontal bar chart of weighted scores, color-coded by skill source.

**Skill Comparison** — For each model, shows every skill's score side by side. The baseline is just the floor — compared the same way as everything else. Key output: which skill does this job best on which model?

**Manual Expert Scoring** — Select a result, adjust five sliders (completeness, precision, accuracy, actionability, judgment), save back to the result file.

### Tab 4: 📜 Skill Viewer

Dropdown of all skills (from `_catalog.json`), showing `{display_name}` and grouped by skill type. Shows:
- Source, license, URL, notes from catalog
- Word count, estimated tokens, line count
- Full skill text in styled monospace viewer

**Compare mode**: pick two skills to view side-by-side in equal columns.

### Tab 5: 📄 Test Documents & Answer Keys

Two-column layout:
- Left: rendered test document markdown
- Right: answer key with severity badges, issue descriptions, "what good looks like"

---

## Test NDA Content

### one_sided_mutual.md

Use the existing NDA text (currently at `nda_02_one_sided_mutual.md` in the prototype). Rename to `one_sided_mutual.md`.

A "Mutual Non-Disclosure Agreement" between Acme Technologies, Inc. (Delaware corp) and [Company Name] (Recipient). One-sided in Acme's favor across every material provision.

**16 planted issues across three severity tiers:**

**CRITICAL (must-catch, weight 3x):**
1. Asymmetric CI definition (§2.1/2.2)
2. Asymmetric disclosure permissions (§3.4/3.5)
3. Perpetual vs. 1-year survival (§8.2/8.3)
4. One-way indemnification (§9.2)
5. $1,000 liability cap (§9.3)
6. Non-solicitation in NDA (§10)

**HIGH (should-catch, weight 2x):**
7. Missing third-party receipt exclusion (§4)
8. One-way compelled disclosure (§5)
9. One-way return/destruction (§6.1/6.2)
10. Unilateral termination (§8.1)
11. One-way injunctive relief without bond (§9.1)

**MODERATE (nice-to-catch, weight 1x):**
12. Onerous proof standard (§4(b)/4(c))
13. One-way warranty disclaimer (§7.2)
14. One-sided forum selection (§11.2)
15. Asymmetric assignment (§11.3)
16. Missing residuals clause (absent)

**Meta-issues (bonus):**
- META-01: Structural asymmetry pattern
- META-02: Non-compete scope creep

Full issue descriptions, detection keywords, and "what good looks like" guidance are in the answer key JSON. Use the existing answer key content from the prototype.

---

## Skills to Include

Fetch and include the full SKILL.md content for each. Skill files contain the actual text injected as system prompt context.

### nda_review/baseline.skill.md
**Source:** Skillcheck (built-in)
The control. A minimal prompt: "Review this NDA and identify any issues, risks, and recommended changes." Not a special case — just the laziest skill in the lineup. Every model runs this so there's a floor to compare against.

### nda_review/lawvable.skill.md
**Source:** https://github.com/lawvable/awesome-legal-skills
The example from their README. 5-step procedure + 4 guidelines. ~130 words. Check the 🌐 directory for a full version — use it if accessible, otherwise use the README version and note it in the catalog.

### nda_triage/anthropic.skill.md
**Source:** https://github.com/anthropics/knowledge-work-plugins/blob/main/legal/skills/nda-triage/SKILL.md
Fetch the actual file from GitHub raw content. GREEN/YELLOW/RED categorization from the Cowork legal plugin.

### contract_review/anthropic.skill.md
**Source:** https://github.com/anthropics/knowledge-work-plugins/blob/main/legal/skills/contract-review/SKILL.md
Fetch from GitHub. Playbook-based contract review, not NDA-specific.

### nda_review/evolsb.skill.md AND contract_review/evolsb.skill.md
**Source:** https://github.com/evolsb/claude-legal-skill/blob/main/skill.md
Fetch from GitHub. One source skill that covers multiple contract types. Place in both `nda_review/` and `contract_review/` (same content, or symlink). Built on CUAD dataset, ContractEval benchmarks, party-aware.

### nda_review/skala.skill.md
**Source:** https://www.skala.io/legal-skills
May need reconstruction from public descriptions. Designed for startups, template comparison approach. Note provenance in catalog.

### nda_review/custom.skill.md
Use the existing `comprehensive_nda_review.md` content from the prototype. 9-section analysis framework, ~900 words.

### Fetching Skills at Build Time

Include a `fetch_skills.py` utility:
1. Reads `_catalog.json` for source URLs
2. Fetches each via HTTP (converting GitHub blob URLs to raw.githubusercontent.com)
3. Saves to the correct `skills/{type}/{source}.skill.md` path
4. Reports success/failure per skill
5. For failures, creates a placeholder file with a TODO note

---

## Styling

Dark theme optimized for screen share. Key elements:

- Hero banner with Skillcheck branding and current eval pack name
- Metric cards with severity-colored borders
- Issue detection chips (green hit / red miss)
- Severity badges: CRITICAL (dark red), HIGH (dark amber), MODERATE (dark blue), LOW (gray)
- Equal-column side-by-side views
- Monospace skill viewer
- Google Fonts: DM Serif Display, DM Sans, JetBrains Mono

---

## Dependencies

```
streamlit>=1.40.0
anthropic>=0.43.0
openai>=1.60.0
google-generativeai>=0.8.0
python-dotenv>=1.0.0
requests>=2.31.0
```

---

## Build Instructions for Claude Code

1. Create the full project structure as specified
2. Run `fetch_skills.py` to pull skills from source URLs
3. For skills that fail to fetch, create placeholder files noting manual download needed
4. Populate `eval_packs/nda_review/` with test NDA and answer key from prototype content
5. Build `engine.py` with provider dispatchers, generic scoring, and result I/O following the directory conventions above
6. Build `app.py` with five-tab layout
7. Verify the app launches with `streamlit run app.py` with no API keys (graceful degradation — show what's missing, don't crash)
8. Self-test: run `auto_score` against a synthetic model response to verify scoring produces expected results

---

## Future Eval Packs

The following can be added later without code changes:

- **Contract Review** — MSAs, SaaS agreements, vendor contracts
- **Deposition Prep** — Using AgentSkills.legal's deposition skills
- **Compliance Analysis** — GDPR, privacy policy review
- **Due Diligence** — M&A document review checklists

Each gets its own `eval_packs/{name}/` directory. Skills from the shared `skills/` library are discovered by matching `relevant_skill_types` in the pack config.
