"""Core evaluation engine for Skillcheck.

Handles skill discovery, prompt construction, auto-scoring,
weighted score computation, parallel evaluation, and result I/O.
"""

import json
import os
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from config import RESULTS_DIR, SKILLS_DIR
from models import MODEL_CONFIGS, call_model


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def discover_skills() -> list[dict]:
    """Scan skills/ for directories containing skill.json."""
    skills = []
    if not SKILLS_DIR.exists():
        return skills
    for d in sorted(SKILLS_DIR.iterdir()):
        meta_file = d / "skill.json"
        if d.is_dir() and meta_file.exists():
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            meta["_dir"] = d
            # Count versions and docs
            meta["version_count"] = len(list(d.glob("*.skill.md")))
            meta["doc_count"] = len(list((d / "docs").glob("*.md"))) if (d / "docs").exists() else 0
            skills.append(meta)
    return skills


def list_skill_versions(skill_id: str) -> list[str]:
    """Glob skills/{skill_id}/*.skill.md, return version names (stem minus .skill)."""
    skill_dir = SKILLS_DIR / skill_id
    if not skill_dir.exists():
        return []
    return sorted(p.stem.replace(".skill", "") for p in skill_dir.glob("*.skill.md"))


def load_skill_version(skill_id: str, version: str) -> str | None:
    """Read one .skill.md file."""
    path = SKILLS_DIR / skill_id / f"{version}.skill.md"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return None


def list_test_docs(skill_id: str) -> list[str]:
    """Glob skills/{skill_id}/docs/*.md, return doc names (stem)."""
    docs_dir = SKILLS_DIR / skill_id / "docs"
    if not docs_dir.exists():
        return []
    return sorted(p.stem for p in docs_dir.glob("*.md"))


def load_test_doc(skill_id: str, doc_name: str) -> str | None:
    """Read one test doc."""
    path = SKILLS_DIR / skill_id / "docs" / f"{doc_name}.md"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return None


def load_answer_key(skill_id: str, doc_name: str) -> dict | None:
    """Read skills/{skill_id}/answer_keys/{doc_name}.json."""
    path = SKILLS_DIR / skill_id / "answer_keys" / f"{doc_name}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


# ---------------------------------------------------------------------------
# Prompt Construction
# ---------------------------------------------------------------------------

def build_prompt(
    skill_meta: dict,
    version_text: str,
    doc_text: str,
) -> tuple[str, str]:
    """Build system and user prompts for an evaluation run.

    Returns (system_prompt, user_prompt).
    """
    system_parts = [skill_meta["system_prompt_prefix"]]
    system_parts.append(
        "--- SKILL INSTRUCTIONS ---\n\n"
        "Apply the following analysis methodology:\n\n"
        + version_text
    )
    system_prompt = "\n\n".join(system_parts)

    perspective = skill_meta.get("default_perspective", "Recipient")
    user_prompt = skill_meta["user_prompt_template"].format(
        document=doc_text, perspective=perspective
    )

    return system_prompt, user_prompt


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def auto_score(response_text: str, answer_key: dict) -> dict:
    """Keyword-based auto-scoring against an answer key.

    Returns dict mapping issue IDs to booleans (detected or not).
    Also checks meta_issues.
    """
    text_lower = response_text.lower()

    issues_detected = {}
    for issue in answer_key.get("issues", []):
        keywords = issue.get("detection_keywords", [])
        detected = any(kw.lower() in text_lower for kw in keywords)
        issues_detected[issue["id"]] = detected

    meta_detected = {}
    for meta in answer_key.get("meta_issues", []):
        keywords = meta.get("detection_keywords", [])
        detected = any(kw.lower() in text_lower for kw in keywords)
        meta_detected[meta["id"]] = detected

    return {
        "issues_detected": issues_detected,
        "meta_issues_detected": meta_detected,
    }


def compute_weighted_scores(score_data: dict, answer_key: dict) -> dict:
    """Compute tier-weighted scores from auto_score output."""
    issues_detected = score_data["issues_detected"]
    meta_detected = score_data["meta_issues_detected"]
    guidance = answer_key["scoring_guidance"]
    weights = guidance["weights"]

    tier_results = {}
    weighted_score = 0
    weighted_max = 0

    for tier_name in ["must_catch", "should_catch", "nice_to_catch"]:
        tier_ids = guidance.get(tier_name, [])
        w = weights.get(tier_name, 1)
        found = sum(1 for iid in tier_ids if issues_detected.get(iid, False))
        total = len(tier_ids)
        tier_results[tier_name] = {"found": found, "total": total}
        weighted_score += found * w
        weighted_max += total * w

    total_found = sum(1 for v in issues_detected.values() if v)
    total_possible = len(issues_detected)

    return {
        "issues_detected": issues_detected,
        "meta_issues_detected": meta_detected,
        "total_found": total_found,
        "total_possible": total_possible,
        "recall_pct": round(total_found / total_possible * 100, 1) if total_possible else 0,
        "must_catch": tier_results.get("must_catch", {"found": 0, "total": 0}),
        "should_catch": tier_results.get("should_catch", {"found": 0, "total": 0}),
        "nice_to_catch": tier_results.get("nice_to_catch", {"found": 0, "total": 0}),
        "weighted_score": weighted_score,
        "weighted_max": weighted_max,
        "weighted_pct": round(weighted_score / weighted_max * 100, 1) if weighted_max else 0,
    }


# ---------------------------------------------------------------------------
# Parallel Evaluation
# ---------------------------------------------------------------------------

def run_evaluation(skill_id: str, model_ids: list[str], doc_name: str):
    """Run ALL versions of a skill across selected models in parallel.

    Yields (version, model_id, result_dict) tuples as they complete.
    Uses ThreadPoolExecutor + as_completed().
    """
    skill_meta = _load_skill_meta(skill_id)
    if not skill_meta:
        return

    versions = list_skill_versions(skill_id)
    if not versions:
        return

    doc_text = load_test_doc(skill_id, doc_name)
    if not doc_text:
        return

    answer_key = load_answer_key(skill_id, doc_name)

    def _run_one(version: str, model_key: str) -> tuple[str, str, dict]:
        cfg = MODEL_CONFIGS[model_key]
        version_text = load_skill_version(skill_id, version)
        if not version_text:
            return version, model_key, {"error": f"Version file not found: {version}"}

        system_prompt, user_prompt = build_prompt(skill_meta, version_text, doc_text)

        try:
            response = call_model(
                cfg["provider"], cfg["model_id"],
                system_prompt, user_prompt,
            )

            auto_scores = None
            if answer_key:
                score_data = auto_score(response["text"], answer_key)
                auto_scores = compute_weighted_scores(score_data, answer_key)

            result = {
                "eval_id": str(uuid.uuid4()),
                "skill_id": skill_id,
                "version": version,
                "doc_name": doc_name,
                "model_key": model_key,
                "model_name": cfg["display_name"],
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "response_text": response["text"],
                "input_tokens": response.get("input_tokens", 0),
                "output_tokens": response.get("output_tokens", 0),
                "elapsed_seconds": response.get("elapsed_seconds", 0),
                "auto_scores": auto_scores,
            }

            save_result(skill_id, version, model_key, doc_name, result)
            return version, model_key, result

        except Exception as e:
            return version, model_key, {"error": str(e)}

    # Build work items: all versions x all models
    futures = {}
    with ThreadPoolExecutor(max_workers=8) as executor:
        for version in versions:
            for model_key in model_ids:
                cfg = MODEL_CONFIGS.get(model_key)
                if not cfg or not os.environ.get(cfg["env_key"]):
                    continue
                future = executor.submit(_run_one, version, model_key)
                futures[future] = (version, model_key)

        for future in as_completed(futures):
            yield future.result()


def _load_skill_meta(skill_id: str) -> dict | None:
    """Load skill.json for a skill_id."""
    path = SKILLS_DIR / skill_id / "skill.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


# ---------------------------------------------------------------------------
# Result I/O
# ---------------------------------------------------------------------------

def save_result(
    skill_id: str,
    version: str,
    model_id: str,
    doc_name: str,
    result: dict,
) -> Path:
    """Save a result dict. Path: results/{skill_id}/{version}/{model}__{doc}.json"""
    out_dir = RESULTS_DIR / skill_id / version
    out_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{model_id}__{doc_name}.json"
    out_path = out_dir / filename

    out_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return out_path


def load_results(skill_id: str) -> list[dict]:
    """Load all saved results for a skill."""
    results = []
    skill_results_dir = RESULTS_DIR / skill_id
    if not skill_results_dir.exists():
        return results

    for path in skill_results_dir.rglob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            results.append(data)
        except (json.JSONDecodeError, OSError):
            continue

    return results
