"""Consensus analysis engine for Skillcheck.

Looks across all evaluation results for a given (skill, doc) pair and computes:
- Per-issue detection rates and consensus classification
- Per-model agreement with majority and pairwise agreement
- Per-version effectiveness across models
- Divergence highlights (the most contested issues)
"""

from __future__ import annotations

from models import MODEL_CONFIGS


# ---------------------------------------------------------------------------
# Consensus categories
# ---------------------------------------------------------------------------

def _classify_rate(rate: float) -> str:
    """Classify an agreement rate into a consensus tier."""
    if rate >= 0.90:
        return "universal"
    if rate >= 0.70:
        return "strong"
    if rate >= 0.30:
        return "disputed"
    return "rare"


TIER_ORDER = {"universal": 0, "strong": 1, "disputed": 2, "rare": 3}


# ---------------------------------------------------------------------------
# Core analysis
# ---------------------------------------------------------------------------

def build_consensus(results: list[dict], answer_key: dict) -> dict:
    """Build full consensus analysis from a list of result dicts.

    All results should be for the same (skill_id, doc_name).

    Returns a dict with:
        issue_consensus: list of per-issue dicts
        model_summary: list of per-model dicts
        version_summary: list of per-version dicts
        pairwise_agreement: dict of (model_a, model_b) -> float
        overall: summary statistics
    """
    if not results or not answer_key:
        return _empty_consensus()

    all_issues = answer_key.get("issues", [])

    # Build severity-based tier map from issue severity
    tier_map = {}
    for issue in all_issues:
        tier_map[issue["id"]] = issue.get("severity", "M")

    # Build detection matrix: {issue_id: {(version, model_key): bool}}
    detection = {issue["id"]: {} for issue in all_issues}
    result_index = {}  # (version, model_key) -> result

    for r in results:
        v = r.get("version", "")
        mk = r.get("model_key", "")
        if not v or not mk:
            continue

        # Only include results that have judge scores
        judge = r.get("judge_scores")
        if not judge:
            continue

        key = (v, mk)
        result_index[key] = r

        for issue in all_issues:
            iid = issue["id"]
            ji = judge.get("issues", {}).get(iid, 0)
            detected = bool(ji)
            detection[iid][key] = detected

    all_keys = sorted(result_index.keys())
    n_results = len(all_keys)

    if n_results == 0:
        return _empty_consensus()

    # --- Per-issue consensus ---
    issue_consensus = []
    for issue in all_issues:
        iid = issue["id"]
        det = detection[iid]
        found_by = [k for k in all_keys if det.get(k, False)]
        missed_by = [k for k in all_keys if not det.get(k, False)]
        rate = len(found_by) / n_results if n_results else 0

        issue_consensus.append({
            "id": iid,
            "title": issue.get("title", iid),
            "tier": tier_map.get(iid, ""),
            "detection_rate": round(rate, 4),
            "classification": _classify_rate(rate),
            "found_count": len(found_by),
            "total_count": n_results,
            "found_by": [
                {"version": v, "model": mk, "model_name": MODEL_CONFIGS.get(mk, {}).get("display_name", mk)}
                for v, mk in found_by
            ],
            "missed_by": [
                {"version": v, "model": mk, "model_name": MODEL_CONFIGS.get(mk, {}).get("display_name", mk)}
                for v, mk in missed_by
            ],
        })

    # Sort: disputed first (most interesting), then by detection rate
    issue_consensus.sort(key=lambda x: (TIER_ORDER.get(x["classification"], 99), -x["detection_rate"]))

    # --- Per-model summary ---
    models_seen = sorted(set(mk for _, mk in all_keys))
    versions_seen = sorted(set(v for v, _ in all_keys))

    # Majority vote per issue
    majority = {}
    for issue in all_issues:
        iid = issue["id"]
        det = detection[iid]
        found = sum(1 for k in all_keys if det.get(k, False))
        majority[iid] = found > n_results / 2

    model_summary = []
    for mk in models_seen:
        model_keys = [(v, mk) for v in versions_seen if (v, mk) in result_index]
        if not model_keys:
            continue

        agrees_with_majority = 0
        total_judgments = 0
        for issue in all_issues:
            iid = issue["id"]
            for k in model_keys:
                det = detection[iid].get(k, False)
                if det == majority[iid]:
                    agrees_with_majority += 1
                total_judgments += 1

        agreement_rate = agrees_with_majority / total_judgments if total_judgments else 0

        # Unique finds: issues this model found that majority missed
        unique_finds = []
        unique_misses = []
        for issue in all_issues:
            iid = issue["id"]
            model_found = any(detection[iid].get(k, False) for k in model_keys)
            if model_found and not majority[iid]:
                unique_finds.append(iid)
            if not model_found and majority[iid]:
                unique_misses.append(iid)

        model_summary.append({
            "model_key": mk,
            "model_name": MODEL_CONFIGS.get(mk, {}).get("display_name", mk),
            "eval_count": len(model_keys),
            "majority_agreement": round(agreement_rate, 4),
            "unique_finds": unique_finds,
            "unique_misses": unique_misses,
        })

    model_summary.sort(key=lambda x: -x["majority_agreement"])

    # --- Per-version summary ---
    version_summary = []
    for v in versions_seen:
        version_keys = [(v, mk) for mk in models_seen if (v, mk) in result_index]
        if not version_keys:
            continue

        agrees = 0
        total = 0
        for issue in all_issues:
            iid = issue["id"]
            for k in version_keys:
                det = detection[iid].get(k, False)
                if det == majority[iid]:
                    agrees += 1
                total += 1

        rate = agrees / total if total else 0

        # Average score for this version
        scores = []
        for k in version_keys:
            r = result_index[k]
            judge = r.get("judge_scores")
            if judge and "composite_score" in judge:
                scores.append(judge["composite_score"] * 100)

        avg_score = sum(scores) / len(scores) if scores else None

        version_summary.append({
            "version": v,
            "eval_count": len(version_keys),
            "majority_agreement": round(rate, 4),
            "avg_score": round(avg_score, 1) if avg_score is not None else None,
        })

    version_summary.sort(key=lambda x: -(x["avg_score"] or 0))

    # --- Pairwise model agreement ---
    pairwise = {}
    for i, m1 in enumerate(models_seen):
        for m2 in models_seen[i + 1:]:
            shared_versions = [
                v for v in versions_seen
                if (v, m1) in result_index and (v, m2) in result_index
            ]
            if not shared_versions:
                continue
            agree = 0
            total = 0
            for issue in all_issues:
                iid = issue["id"]
                for v in shared_versions:
                    d1 = detection[iid].get((v, m1), False)
                    d2 = detection[iid].get((v, m2), False)
                    if d1 == d2:
                        agree += 1
                    total += 1
            rate = agree / total if total else 0
            pairwise[(m1, m2)] = round(rate, 4)

    # --- Overall stats ---
    n_universal = sum(1 for ic in issue_consensus if ic["classification"] == "universal")
    n_strong = sum(1 for ic in issue_consensus if ic["classification"] == "strong")
    n_disputed = sum(1 for ic in issue_consensus if ic["classification"] == "disputed")
    n_rare = sum(1 for ic in issue_consensus if ic["classification"] == "rare")

    return {
        "issue_consensus": issue_consensus,
        "model_summary": model_summary,
        "version_summary": version_summary,
        "pairwise_agreement": {
            f"{m1} vs {m2}": rate for (m1, m2), rate in pairwise.items()
        },
        "pairwise_detail": [
            {
                "model_a": m1,
                "model_a_name": MODEL_CONFIGS.get(m1, {}).get("display_name", m1),
                "model_b": m2,
                "model_b_name": MODEL_CONFIGS.get(m2, {}).get("display_name", m2),
                "agreement": rate,
            }
            for (m1, m2), rate in sorted(pairwise.items(), key=lambda x: -x[1])
        ],
        "overall": {
            "total_results": n_results,
            "total_models": len(models_seen),
            "total_versions": len(versions_seen),
            "total_issues": len(all_issues),
            "universal": n_universal,
            "strong": n_strong,
            "disputed": n_disputed,
            "rare": n_rare,
        },
        "detection_matrix": detection,
        "result_keys": all_keys,
        "models": models_seen,
        "versions": versions_seen,
    }


def _empty_consensus() -> dict:
    return {
        "issue_consensus": [],
        "model_summary": [],
        "version_summary": [],
        "pairwise_agreement": {},
        "pairwise_detail": [],
        "overall": {
            "total_results": 0, "total_models": 0, "total_versions": 0,
            "total_issues": 0, "universal": 0, "strong": 0, "disputed": 0, "rare": 0,
        },
        "detection_matrix": {},
        "result_keys": [],
        "models": [],
        "versions": [],
    }


# ---------------------------------------------------------------------------
# Chat context builder
# ---------------------------------------------------------------------------

def build_chat_context(
    consensus: dict,
    results: list[dict],
    answer_key: dict,
    skill_id: str,
    doc_name: str,
) -> str:
    """Build a system prompt context string that summarizes all evaluation data
    for use in the chat-with-data feature.
    """
    lines = [
        f"You are analyzing evaluation results for skill '{skill_id}', test document '{doc_name}'.",
        "",
        f"## Overview",
        f"- {consensus['overall']['total_results']} evaluations across "
        f"{consensus['overall']['total_models']} models and "
        f"{consensus['overall']['total_versions']} skill versions",
        f"- {consensus['overall']['total_issues']} issues in the answer key",
        f"- Consensus breakdown: {consensus['overall']['universal']} universal, "
        f"{consensus['overall']['strong']} strong, "
        f"{consensus['overall']['disputed']} disputed, "
        f"{consensus['overall']['rare']} rare",
        "",
        "## Issue Consensus",
    ]

    for ic in consensus["issue_consensus"]:
        tier_label = {"H": "HIGH", "M": "MED", "L": "LOW"}.get(ic["tier"], "")
        found_models = ", ".join(f"{f['model_name']}/{f['version']}" for f in ic["found_by"])
        missed_models = ", ".join(f"{f['model_name']}/{f['version']}" for f in ic["missed_by"])
        lines.append(
            f"- **{ic['id']}** ({ic['title']}) [{tier_label}]: "
            f"{ic['detection_rate']*100:.0f}% detection ({ic['classification']}). "
            f"Found by: [{found_models}]. Missed by: [{missed_models}]."
        )

    lines.append("")
    lines.append("## Model Performance Summary")
    for ms in consensus["model_summary"]:
        lines.append(
            f"- **{ms['model_name']}**: {ms['majority_agreement']*100:.0f}% majority agreement, "
            f"{ms['eval_count']} evals"
        )
        if ms["unique_finds"]:
            lines.append(f"  - Unique finds (found by this model, missed by majority): {', '.join(ms['unique_finds'])}")
        if ms["unique_misses"]:
            lines.append(f"  - Unique misses (missed by this model, found by majority): {', '.join(ms['unique_misses'])}")

    lines.append("")
    lines.append("## Version Effectiveness")
    for vs in consensus["version_summary"]:
        score_str = f", avg score {vs['avg_score']:.1f}%" if vs["avg_score"] is not None else ""
        lines.append(
            f"- **{vs['version']}**: {vs['majority_agreement']*100:.0f}% majority agreement{score_str}"
        )

    if consensus["pairwise_detail"]:
        lines.append("")
        lines.append("## Pairwise Model Agreement")
        for pw in consensus["pairwise_detail"]:
            lines.append(
                f"- {pw['model_a_name']} vs {pw['model_b_name']}: {pw['agreement']*100:.0f}%"
            )

    # Add answer key issue details for reference
    lines.append("")
    lines.append("## Answer Key Reference")
    for issue in answer_key.get("issues", []):
        lines.append(
            f"- **{issue['id']}** ({issue.get('title', '')}): {issue.get('description', '')} "
            f"[severity: {issue.get('severity', 'N/A')}]"
        )

    # Include individual model responses (truncated) for detailed queries
    lines.append("")
    lines.append("## Individual Evaluation Results")
    for r in results:
        v = r.get("version", "")
        mk = r.get("model_key", "")
        model_name = MODEL_CONFIGS.get(mk, {}).get("display_name", mk)

        judge = r.get("judge_scores")

        score_str = ""
        if judge and "composite_score" in judge:
            score_str = f"judge={judge['composite_score']*100:.0f}%"

        # Truncate response to keep context manageable
        resp = r.get("response_text", "")
        if len(resp) > 2000:
            resp = resp[:2000] + "\n... [truncated]"

        lines.append(f"\n### {model_name} / {v} ({score_str})")
        lines.append(resp)

    return "\n".join(lines)
