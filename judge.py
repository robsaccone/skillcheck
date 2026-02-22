"""LLM-as-Judge scoring for Skillcheck.

Builds judge prompts, calls the judge model, parses structured JSON output,
and computes composite scores from binary per-issue detection, recommendation
match, and false positive count.

Enhancements informed by:

- G-Eval (Liu et al., 2023) — chain-of-thought before scoring improves
  human alignment by 10-15%.  https://arxiv.org/abs/2303.16634

- PoLL / Panel of LLM Evaluators (Verga et al., 2024) — an ensemble of
  smaller models from different families correlates better with human
  judgments than a single large judge, at lower cost.
  https://arxiv.org/abs/2404.18796

- Self-preference bias (Wataoka et al., 2024) — LLMs assign higher scores
  to outputs from their own model family due to perplexity-based familiarity.
  https://arxiv.org/abs/2410.21819

- Verbosity bias (Zheng et al., 2024) — judges favor longer responses,
  inflating scores ~15% for verbose answers regardless of substance.
  https://arxiv.org/abs/2306.05685

- Scale calibration (Husain, 2024) — binary scales are the most reliable
  and reproducible; few-shot anchors reduce variance.
  https://hamel.dev/blog/posts/llm-judge/
"""

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from config import RECOMMENDATION_BONUS, FP_PENALTY_PER, SEVERITY_WEIGHTS
from models import MODEL_CONFIGS, call_model


# ---------------------------------------------------------------------------
# Default Judge System Prompt
#
# Key design choices, backed by research:
# 1. Chain-of-thought reasoning BEFORE scores (G-Eval)
# 2. Few-shot calibration examples for binary detection (Husain)
# 3. Explicit anti-verbosity instruction (Zheng et al.)
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
for each issue to decide.

### Calibration Examples

**Score 1 (detected)**: The model explicitly names or substantively discusses
the concern, even using different terminology. E.g., the answer key says
"unilateral termination clause" and the model discusses "one-sided right to
end the agreement." The model must show awareness of the *specific risk*,
not just mention the section heading.

**Score 0 (missed)**: The issue is not mentioned at all, or only tangentially
referenced without substantive analysis. Merely listing a clause heading
without analyzing the underlying risk does NOT count as detection.

## 3. False Positives
List any provisions the model flagged as problematic that are actually standard,
reasonable, or well-drafted. Use the false_positive_traps in the answer key
(if provided) as a guide, but also use your own judgment.

## Important: Avoid Verbosity Bias

Do NOT give credit for length. A concise response that identifies an issue in
one sentence scores the same as a verbose response that takes a paragraph.
Penalize responses that pad length without adding analytical substance.

## Output Format

For each issue, FIRST write a brief reasoning explanation, THEN assign a score.
This ensures more accurate evaluation.

Return ONLY a JSON object with exactly this structure (no other text):

```json
{
  "recommendation": {
    "model_said": "sign" or "negotiate" or "dont_sign",
    "correct": "sign" or "negotiate" or "dont_sign",
    "match": true or false,
    "reasoning": "1 sentence explaining how you determined the model's recommendation"
  },
  "issues": {
    "ISSUE-01": {
      "detected": 1 or 0,
      "reasoning": "1 sentence explaining what the model did or did not cover"
    }
  },
  "false_positive_count": 2,
  "false_positives": ["flagged standard severability clause", "flagged counterparts provision"]
}
```

For `model_said`: extract the model's recommendation. Use "sign" if the model
said the agreement is acceptable as-is, "negotiate" if it recommended changes
before signing, "dont_sign" if it recommended rejecting or walking away.
If unclear, use your best judgment.

Be strict but fair. Score based on substance, not formatting or length.
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

def _normalize_issues(raw_issues: dict) -> tuple[dict, dict]:
    """Normalize issues from judge output to flat {id: 0|1} + reasoning dict.

    Handles both new format ({"ISSUE-01": {"detected": 1, "reasoning": "..."}})
    and legacy format ({"ISSUE-01": 1}).

    Returns (flat_issues, reasoning_dict).
    """
    flat = {}
    reasoning = {}
    for iid, val in raw_issues.items():
        if isinstance(val, dict):
            flat[iid] = val.get("detected", 0)
            if "reasoning" in val:
                reasoning[iid] = val["reasoning"]
        else:
            flat[iid] = val
    return flat, reasoning


def parse_judge_output(raw_text: str) -> dict | None:
    """Extract JSON from judge model response.

    Handles:
    - Raw JSON
    - ```json ... ``` fenced blocks
    - JSON with preamble/postamble text (e.g. chain-of-thought before JSON)
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
        # Handle both flat (int) and nested (dict with "detected") formats
        raw = judge_issues.get(iid, 0)
        hit = raw.get("detected", 0) if isinstance(raw, dict) else raw
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
# Self-Enhancement Bias Detection
#
# LLMs assign higher scores to outputs from their own model family
# (Wataoka et al., 2024). We flag this so users can make informed decisions.
# ---------------------------------------------------------------------------

def detect_self_enhancement_risk(judge_model_key: str, evaluated_model_key: str) -> str | None:
    """Check if the judge and evaluated model share a provider (family).

    Returns a warning string if self-enhancement bias risk is detected,
    None otherwise.

    Reference: Wataoka et al. (2024) "Self-Preference Bias in LLM-as-a-Judge"
    https://arxiv.org/abs/2410.21819
    """
    judge_cfg = MODEL_CONFIGS.get(judge_model_key, {})
    eval_cfg = MODEL_CONFIGS.get(evaluated_model_key, {})

    judge_provider = judge_cfg.get("provider", "")
    eval_provider = eval_cfg.get("provider", "")

    if judge_provider and judge_provider == eval_provider:
        judge_name = judge_cfg.get("display_name", judge_model_key)
        eval_name = eval_cfg.get("display_name", evaluated_model_key)
        return (
            f"Self-enhancement risk: {judge_name} judging {eval_name} "
            f"(same family: {judge_provider}). Same-family scores may be "
            f"inflated ~15% (Wataoka et al., 2024)."
        )
    return None


# ---------------------------------------------------------------------------
# Single-Judge Entry Point
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
    composite_score, component scores, reasoning, token counts, elapsed time.
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

    # Normalize issues to flat format and extract reasoning
    raw_issues = parsed.get("issues", {})
    flat_issues, issue_reasoning = _normalize_issues(raw_issues)

    # Extract recommendation reasoning
    rec = parsed.get("recommendation", {})
    rec_reasoning = rec.pop("reasoning", None) if isinstance(rec, dict) else None

    # Build reasoning dict
    reasoning = {}
    reasoning.update(issue_reasoning)
    if rec_reasoning:
        reasoning["recommendation"] = rec_reasoning

    # Compute composite with flat issues
    normalized_output = {
        "recommendation": rec,
        "issues": flat_issues,
        "false_positive_count": parsed.get("false_positive_count", 0),
        "false_positives": parsed.get("false_positives", []),
    }
    composite = compute_composite_scores(normalized_output, answer_key)

    return {
        "judge_model": judge_model_key,
        "recommendation": rec,
        "issues": flat_issues,
        "false_positive_count": parsed.get("false_positive_count", 0),
        "false_positives": parsed.get("false_positives", []),
        "composite_score": composite["composite_score"],
        "weighted_hit_rate": composite["weighted_hit_rate"],
        "recommendation_match": composite["recommendation_match"],
        "issues_found": composite["issues_found"],
        "issues_total": composite["issues_total"],
        "reasoning": reasoning,
        "judge_input_tokens": response.get("input_tokens", 0),
        "judge_output_tokens": response.get("output_tokens", 0),
        "judge_elapsed_seconds": elapsed,
    }


# ---------------------------------------------------------------------------
# Multi-Judge Panel
#
# Implements the PoLL methodology (Verga et al., 2024): run multiple judges
# from different model families and aggregate scores. This reduces
# self-enhancement bias and improves correlation with human judgments.
#
# Aggregation strategy:
# - Binary per-issue scores (0/1): majority vote
# - Recommendation match: majority vote
# - False positives: union of unique items, count = average
# - Reasoning: concatenated from all judges
# ---------------------------------------------------------------------------

def judge_panel(
    doc_text: str,
    answer_key: dict,
    response_text: str,
    judge_model_keys: list[str],
    judge_system_prompt: str | None = None,
    skill_meta: dict | None = None,
) -> dict | None:
    """Run a panel of LLM judges and aggregate their scores.

    Uses majority vote for binary scores and average pooling for counts,
    following the PoLL methodology (Verga et al., 2024).

    Returns aggregated judge_scores dict, or None if all judges fail.
    """
    if not judge_model_keys:
        return None

    # Single judge — no panel needed
    if len(judge_model_keys) == 1:
        result = judge_response(
            doc_text, answer_key, response_text,
            judge_model_keys[0], judge_system_prompt, skill_meta,
        )
        if result:
            result["panel_size"] = 1
            result["panel_judges"] = [judge_model_keys[0]]
        return result

    # Run judges in parallel
    individual_results = []

    def _run_judge(model_key):
        return judge_response(
            doc_text, answer_key, response_text,
            model_key, judge_system_prompt, skill_meta,
        )

    with ThreadPoolExecutor(max_workers=len(judge_model_keys)) as executor:
        futures = {
            executor.submit(_run_judge, mk): mk
            for mk in judge_model_keys
        }
        for future in as_completed(futures):
            result = future.result()
            if result is not None:
                individual_results.append(result)

    if not individual_results:
        return None

    n = len(individual_results)

    # --- Aggregate per-issue scores via majority vote ---
    all_issue_ids = set()
    for r in individual_results:
        all_issue_ids.update(r.get("issues", {}).keys())

    aggregated_issues = {}
    aggregated_reasoning = {}
    for iid in all_issue_ids:
        votes = [r.get("issues", {}).get(iid, 0) for r in individual_results]
        # Majority vote (ties go positive — benefit of the doubt)
        aggregated_issues[iid] = 1 if sum(votes) >= n / 2 else 0

        # Merge reasoning from all judges
        reasonings = []
        for r in individual_results:
            text = r.get("reasoning", {}).get(iid)
            if text:
                judge_name = MODEL_CONFIGS.get(r["judge_model"], {}).get("display_name", r["judge_model"])
                reasonings.append(f"[{judge_name}] {text}")
        if reasonings:
            aggregated_reasoning[iid] = " | ".join(reasonings)

    # --- Aggregate recommendation via majority vote ---
    rec_votes = [r.get("recommendation_match", False) for r in individual_results]
    rec_match = sum(rec_votes) >= n / 2
    # Take recommendation details from first judge that matches majority
    agg_rec = {}
    for r in individual_results:
        if r.get("recommendation_match", False) == rec_match:
            agg_rec = r.get("recommendation", {})
            break
    agg_rec["match"] = rec_match

    # Merge recommendation reasoning
    rec_reasonings = []
    for r in individual_results:
        text = r.get("reasoning", {}).get("recommendation")
        if text:
            judge_name = MODEL_CONFIGS.get(r["judge_model"], {}).get("display_name", r["judge_model"])
            rec_reasonings.append(f"[{judge_name}] {text}")
    if rec_reasonings:
        aggregated_reasoning["recommendation"] = " | ".join(rec_reasonings)

    # --- Aggregate false positives: average count, union of items ---
    fp_counts = [r.get("false_positive_count", 0) for r in individual_results]
    agg_fp_count = round(sum(fp_counts) / n)

    all_fps = set()
    for r in individual_results:
        all_fps.update(r.get("false_positives", []))

    # --- Compute composite on aggregated output ---
    aggregated_output = {
        "recommendation": agg_rec,
        "issues": aggregated_issues,
        "false_positive_count": agg_fp_count,
        "false_positives": sorted(all_fps),
    }
    composite = compute_composite_scores(aggregated_output, answer_key)

    # Sum token costs, take max elapsed (they ran in parallel)
    total_in = sum(r.get("judge_input_tokens", 0) for r in individual_results)
    total_out = sum(r.get("judge_output_tokens", 0) for r in individual_results)
    total_elapsed = max(r.get("judge_elapsed_seconds", 0) for r in individual_results)

    return {
        "judge_model": "+".join(r["judge_model"] for r in individual_results),
        "recommendation": agg_rec,
        "issues": aggregated_issues,
        "false_positive_count": agg_fp_count,
        "false_positives": sorted(all_fps),
        "composite_score": composite["composite_score"],
        "weighted_hit_rate": composite["weighted_hit_rate"],
        "recommendation_match": composite["recommendation_match"],
        "issues_found": composite["issues_found"],
        "issues_total": composite["issues_total"],
        "reasoning": aggregated_reasoning,
        "judge_input_tokens": total_in,
        "judge_output_tokens": total_out,
        "judge_elapsed_seconds": total_elapsed,
        # Panel metadata
        "panel_size": n,
        "panel_judges": [r["judge_model"] for r in individual_results],
        "panel_scores": [
            {
                "judge_model": r["judge_model"],
                "composite_score": r["composite_score"],
            }
            for r in individual_results
        ],
    }
