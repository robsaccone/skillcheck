"""Home page — project overview and getting started guide."""

import streamlit as st
from pathlib import Path

ASSETS = Path(__file__).parent.parent / "assets"

st.image(str(ASSETS / "logo.svg"), width=300)
st.caption("Skills = playbooks = prompts. \n\nThey are written instructions that capture expertise and procedural knowledge on a given task. Skillcheck helps evaluate skills against different models, inputs, and scenarios.")

# ---------------------------------------------------------------------------
# What it does
# ---------------------------------------------------------------------------

st.markdown("### What it does")
st.markdown(
    """
- **Compare prompt versions** — run multiple prompt variants against the same
  test documents and see which one performs best.
- **Compare models** — evaluate the same prompt across different LLMs
  side-by-side.
- **Score automatically** — keyword-based quick scoring gives instant recall
  metrics; LLM-as-judge scoring adds qualitative depth.
- **Find consensus** — see where models agree and where they diverge, with
  per-issue detection rates and pairwise agreement analysis.
- **Chat with results** — ask questions about the evaluation data in natural
  language to explore patterns and outliers conversationally.
- **Track results** — every evaluation is saved to disk so you can revisit
  and compare over time.
"""
)

# ---------------------------------------------------------------------------
# How it works
# ---------------------------------------------------------------------------

st.markdown("### How it works")
st.markdown(
    """
1. Browse your skills and prompt versions on the **Skills** page.
2. Check which models have API keys configured on the **Models** page.
3. Optionally set up an LLM judge on the **Judges** page for richer scoring.
4. Run evaluations on the **Evaluate** page — pick a skill, select models,
   and compare results.
5. Explore the **Consensus** page to find agreement patterns, divergence,
   and chat with the results.
"""
)

# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

st.markdown("### Scoring")
st.markdown(
    """
Each answer key organises issues into three tiers with different weights:

| Tier | Weight | Description |
|------|--------|-------------|
| Must catch | **3x** | Critical issues that should never be missed |
| Should catch | **2x** | Important issues a thorough review would find |
| Nice to catch | **1x** | Subtle points that demonstrate deep analysis |

**Quick scoring** matches keywords from the answer key against the model's
response. **Judge scoring** sends the response to a second LLM that evaluates
it against the full answer key for more nuanced assessment.
"""
)

# ---------------------------------------------------------------------------
# Adding skills
# ---------------------------------------------------------------------------

st.markdown("### Adding your own skills")
st.markdown(
    """
Drop a new folder under `skills/` with this structure:

```
skills/my-skill/
  skill.json          # metadata and prompt templates
  v1.skill.md         # first prompt version
  v2.skill.md         # second prompt version
  tests/
    sample.md         # test document
    sample.json       # expected issues and scoring tiers
```

Restart the app and your skill will appear on the Skills page.
"""
)
