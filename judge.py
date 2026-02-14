"""LLM-as-Judge scoring for Skillcheck.

Builds judge prompts, calls the judge model, parses structured JSON output,
and computes composite scores from per-issue rubric evaluations.
"""

import copy
import json
import re
import time

from config import DEFAULT_SCORING_WEIGHTS
from models import MODEL_CONFIGS, call_model


# ---------------------------------------------------------------------------
# Default Judge System Prompt
# ---------------------------------------------------------------------------

DEFAULT_JUDGE_SYSTEM_PROMPT = """\
You are an expert legal-review evaluator. Your job is to assess the quality
of an AI model's analysis of a legal document, using the provided answer key
as a rubric.

## Scoring Dimensions

### Per-Issue Rubric (score each 0 or 1)
For every issue in the answer key, evaluate whether the model response:
- **identified**: Did the response identify this issue at all?
- **correctly_characterized**: Did it accurately describe the nature and impact?
- **severity_appropriate**: Did it assign an appropriate severity/risk level?
- **actionable**: Did it provide a concrete, useful recommendation?

### Per-Meta-Issue Rubric (score each 0 or 1)
For every meta_issue in the answer key, evaluate whether the model response:
- **identified**: Did the response recognize this overarching pattern?
- **synthesized**: Did it connect multiple individual issues into this theme?
- **strategic**: Did it provide strategic-level guidance beyond individual fixes?

### Document-Level Scores (score each 0.0 to 1.0)
- **overall_classification**: Did the response correctly classify the overall
  risk level of the document?
- **completeness**: What fraction of the important issues were identified?
- **precision**: Of the issues raised, what fraction were actually valid
  (not false positives or fabricated)?
- **professional_quality**: Is the response well-structured, clearly written,
  and suitable for a professional audience?

## Output Format

Return ONLY a JSON object with exactly this structure (no other text):

```json
{
  "issues": {
    "<issue_id>": {
      "identified": 0 or 1,
      "correctly_characterized": 0 or 1,
      "severity_appropriate": 0 or 1,
      "actionable": 0 or 1
    }
  },
  "meta_issues": {
    "<meta_issue_id>": {
      "identified": 0 or 1,
      "synthesized": 0 or 1,
      "strategic": 0 or 1
    }
  },
  "document_level": {
    "overall_classification": 0.0 to 1.0,
    "completeness": 0.0 to 1.0,
    "precision": 0.0 to 1.0,
    "professional_quality": 0.0 to 1.0
  }
}
```

Be strict but fair. Score based on substance, not formatting.
"""


# ---------------------------------------------------------------------------
# Answer Key Sanitization
# ---------------------------------------------------------------------------

def _sanitize_answer_key(answer_key: dict) -> dict:
    """Remove keyword-based fields so the judge evaluates semantically.

    Strips `quick_screen_keywords` and `detection_keywords` from issues
    and meta_issues to prevent the judge from keyword-matching.
    """
    ak = copy.deepcopy(answer_key)

    for issue in ak.get("issues", []):
        issue.pop("quick_screen_keywords", None)
        issue.pop("detection_keywords", None)

    for meta in ak.get("meta_issues", []):
        meta.pop("quick_screen_keywords", None)
        meta.pop("detection_keywords", None)

    return ak


# ---------------------------------------------------------------------------
# Prompt Construction
# ---------------------------------------------------------------------------

def build_judge_prompt(
    doc_text: str,
    answer_key: dict,
    response_text: str,
    judge_system_prompt: str | None = None,
) -> tuple[str, str]:
    """Build (system, user) prompts for the judge model.

    Returns (system_prompt, user_prompt).
    """
    system = judge_system_prompt or DEFAULT_JUDGE_SYSTEM_PROMPT

    sanitized_ak = _sanitize_answer_key(answer_key)

    user = (
        "## Document Under Review\n\n"
        f"{doc_text}\n\n"
        "## Answer Key\n\n"
        f"```json\n{json.dumps(sanitized_ak, indent=2)}\n```\n\n"
        "## Model Response to Evaluate\n\n"
        f"{response_text}"
    )

    return system, user


# ---------------------------------------------------------------------------
# Output Parsing
# ---------------------------------------------------------------------------

def parse_judge_output(raw_text: str) -> dict | None:
    """Extract JSON from judge model response.

    Handles:
    - Raw JSON
    - ```json ... ``` fenced blocks
    - JSON with preamble/postamble text
    Returns None on parse failure.
    """
    if not raw_text:
        return None

    text = raw_text.strip()

    # Try raw JSON first
    if text.startswith("{"):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

    # Try fenced JSON block
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if fence_match:
        try:
            return json.loads(fence_match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Try finding JSON object anywhere in the text
    brace_match = re.search(r"\{.*\}", text, re.DOTALL)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            pass

    return None


# ---------------------------------------------------------------------------
# Composite Scoring
# ---------------------------------------------------------------------------

def _resolve_scoring_weights(answer_key: dict, skill_meta: dict | None) -> dict:
    """Resolve scoring weights with fallback chain:
    answer_key > skill_meta > DEFAULT_SCORING_WEIGHTS.
    """
    weights = answer_key.get("scoring_weights")
    if weights:
        return weights

    if skill_meta:
        weights = skill_meta.get("scoring_weights")
        if weights:
            return weights

    return DEFAULT_SCORING_WEIGHTS


def compute_composite_scores(
    judge_output: dict,
    answer_key: dict,
    scoring_weights: dict,
) -> dict:
    """Compute weighted composite from judge rubric scores.

    Issue scores are weighted by tier (must_catch=3x, should_catch=2x,
    nice_to_catch=1x). Document-level scores are combined per scoring_weights.

    Returns {composite_score: float, component_scores: {...}}.
    """
    guidance = answer_key.get("scoring_guidance", {})
    tier_weights = guidance.get("weights", {
        "must_catch": 3, "should_catch": 2, "nice_to_catch": 1,
    })

    # Build tier map: issue_id -> tier_name
    tier_map = {}
    for tier_name in ["must_catch", "should_catch", "nice_to_catch"]:
        for iid in guidance.get(tier_name, []):
            tier_map[iid] = tier_name

    # Compute weighted issue score
    judge_issues = judge_output.get("issues", {})
    weighted_issue_pts = 0.0
    weighted_issue_max = 0.0

    for iid, tier_name in tier_map.items():
        tw = tier_weights.get(tier_name, 1)
        issue_scores = judge_issues.get(iid, {})
        # Average the rubric dimensions for this issue
        dims = ["identified", "correctly_characterized", "severity_appropriate", "actionable"]
        dim_values = [issue_scores.get(d, 0) for d in dims]
        issue_avg = sum(dim_values) / len(dims) if dims else 0
        weighted_issue_pts += issue_avg * tw
        weighted_issue_max += tw

    weighted_issue_score = (
        weighted_issue_pts / weighted_issue_max
        if weighted_issue_max > 0
        else 0.0
    )

    # Document-level scores
    doc_level = judge_output.get("document_level", {})
    completeness = doc_level.get("completeness", 0.0)
    precision = doc_level.get("precision", 0.0)
    professional_quality = doc_level.get("professional_quality", 0.0)
    classification_accuracy = doc_level.get("overall_classification", 0.0)

    component_scores = {
        "weighted_issue_score": round(weighted_issue_score, 4),
        "completeness": completeness,
        "precision": precision,
        "professional_quality": professional_quality,
        "classification_accuracy": classification_accuracy,
    }

    # Compute composite using scoring weights
    composite = 0.0
    for key, weight in scoring_weights.items():
        composite += component_scores.get(key, 0.0) * weight

    return {
        "composite_score": round(composite, 4),
        "component_scores": component_scores,
    }


# ---------------------------------------------------------------------------
# Main Entry Point
# ---------------------------------------------------------------------------

def judge_response(
    doc_text: str,
    answer_key: dict,
    response_text: str,
    judge_model_key: str,
    judge_system_prompt: str | None = None,
    skill_meta: dict | None = None,
) -> dict | None:
    """Run LLM-as-judge evaluation on a model response.

    Returns dict with judge_model, issues, meta_issues, document_level,
    composite_score, component_scores, token counts, elapsed time.
    Returns None on failure.
    """
    cfg = MODEL_CONFIGS.get(judge_model_key)
    if not cfg:
        return None

    system, user = build_judge_prompt(
        doc_text, answer_key, response_text, judge_system_prompt,
    )

    start = time.time()
    try:
        response = call_model(
            cfg["provider"], cfg["model_id"],
            system, user,
        )
    except Exception:
        return None
    elapsed = round(time.time() - start, 2)

    parsed = parse_judge_output(response.get("text", ""))
    if not parsed:
        return None

    scoring_weights = _resolve_scoring_weights(answer_key, skill_meta)
    composite = compute_composite_scores(parsed, answer_key, scoring_weights)

    return {
        "judge_model": judge_model_key,
        "issues": parsed.get("issues", {}),
        "meta_issues": parsed.get("meta_issues", {}),
        "document_level": parsed.get("document_level", {}),
        "composite_score": composite["composite_score"],
        "component_scores": composite["component_scores"],
        "judge_input_tokens": response.get("input_tokens", 0),
        "judge_output_tokens": response.get("output_tokens", 0),
        "judge_elapsed_seconds": elapsed,
    }
