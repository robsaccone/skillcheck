"""LLM-as-Judge scoring for Skillcheck.

Builds judge prompts, calls the judge model, parses structured JSON output,
and computes composite scores from binary per-issue detection, recommendation
match, and false positive count.
"""

import json
import re
import time

from config import RECOMMENDATION_BONUS, FP_PENALTY_PER, SEVERITY_WEIGHTS
from models import MODEL_CONFIGS, call_model


# ---------------------------------------------------------------------------
# Default Judge System Prompt
# ---------------------------------------------------------------------------

DEFAULT_JUDGE_SYSTEM_PROMPT = """\
You are an expert legal-review evaluator. Your job is to assess the quality
of an AI model's analysis of a legal document, using the provided answer key.

You must evaluate THREE things:

## 1. Recommendation Match
Did the model give a clear recommendation to SIGN, NEGOTIATE, or DON'T SIGN?
Compare to the expected recommendation in the answer key.

## 2. Per-Issue Detection (binary)
For every issue in the answer key, score 1 if the model identified this issue
(even if imperfectly) or 0 if it missed it entirely. Use the rubric question
for each issue to decide. Be strict but fair — the model must show awareness
of the specific concern, not just mention the section.

## 3. False Positives
List any provisions the model flagged as problematic that are actually standard,
reasonable, or well-drafted. Use the false_positive_traps in the answer key
(if provided) as a guide, but also use your own judgment.

## Output Format

Return ONLY a JSON object with exactly this structure (no other text):

```json
{
  "recommendation": {
    "model_said": "sign" or "negotiate" or "dont_sign",
    "correct": "sign" or "negotiate" or "dont_sign",
    "match": true or false
  },
  "issues": {
    "ISSUE-01": 1,
    "ISSUE-02": 0,
    "META-01": 1
  },
  "false_positive_count": 2,
  "false_positives": ["flagged standard severability clause", "flagged counterparts provision"]
}
```

For `model_said`: extract the model's recommendation. Use "sign" if the model
said the agreement is acceptable as-is, "negotiate" if it recommended changes
before signing, "dont_sign" if it recommended rejecting or walking away.
If unclear, use your best judgment.

Be strict but fair. Score based on substance, not formatting.
"""


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

    user = (
        "## Document Under Review\n\n"
        f"{doc_text}\n\n"
        "## Answer Key\n\n"
        f"```json\n{json.dumps(answer_key, indent=2)}\n```\n\n"
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

def compute_composite_scores(
    judge_output: dict,
    answer_key: dict,
) -> dict:
    """Compute composite score from judge output.

    composite = weighted_hit_rate (0-100) + recommendation_bonus - fp_penalty
    Clamped to [0, 100], returned as 0.0-1.0 for UI compat.

    Returns {composite_score, weighted_hit_rate, recommendation_match,
             false_positive_count, issues_found, issues_total}.
    """
    # Build severity map from answer key issues
    issues_list = answer_key.get("issues", [])
    judge_issues = judge_output.get("issues", {})

    weighted_pts = 0.0
    weighted_max = 0.0
    found = 0
    total = len(issues_list)

    for issue in issues_list:
        iid = issue["id"]
        severity = issue.get("severity", "M")
        weight = SEVERITY_WEIGHTS.get(severity, 1)
        hit = judge_issues.get(iid, 0)
        if hit:
            found += 1
        weighted_pts += hit * weight
        weighted_max += weight

    weighted_hit_rate = (weighted_pts / weighted_max * 100) if weighted_max > 0 else 0.0

    # Recommendation bonus
    rec = judge_output.get("recommendation", {})
    rec_match = rec.get("match", False)
    rec_bonus = RECOMMENDATION_BONUS if rec_match else 0

    # False positive penalty
    fp_count = judge_output.get("false_positive_count", 0)
    fp_penalty = fp_count * FP_PENALTY_PER

    # Composite = hit_rate + rec_bonus - fp_penalty, clamped to [0, 100]
    raw_composite = weighted_hit_rate + rec_bonus - fp_penalty
    composite = max(0.0, min(100.0, raw_composite))

    return {
        "composite_score": round(composite / 100, 4),
        "weighted_hit_rate": round(weighted_hit_rate, 2),
        "recommendation_match": rec_match,
        "false_positive_count": fp_count,
        "issues_found": found,
        "issues_total": total,
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

    Returns dict with judge_model, recommendation, issues, false_positives,
    composite_score, component scores, token counts, elapsed time.
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

    composite = compute_composite_scores(parsed, answer_key)

    return {
        "judge_model": judge_model_key,
        "recommendation": parsed.get("recommendation", {}),
        "issues": parsed.get("issues", {}),
        "false_positive_count": parsed.get("false_positive_count", 0),
        "false_positives": parsed.get("false_positives", []),
        "composite_score": composite["composite_score"],
        "weighted_hit_rate": composite["weighted_hit_rate"],
        "recommendation_match": composite["recommendation_match"],
        "issues_found": composite["issues_found"],
        "issues_total": composite["issues_total"],
        "judge_input_tokens": response.get("input_tokens", 0),
        "judge_output_tokens": response.get("output_tokens", 0),
        "judge_elapsed_seconds": elapsed,
    }
