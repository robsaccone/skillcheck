"""Core evaluation engine for Skillcheck.

Handles skill discovery, prompt construction, parallel evaluation,
judge integration, and result I/O.
"""

import json
import os
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

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
            # Count versions (including external) and docs
            ext_count = sum(1 for v in meta.get("versions", {}).values()
                           if isinstance(v, dict) and v.get("external"))
            meta["version_count"] = len(list(d.glob("*.skill.md"))) + ext_count
            meta["doc_count"] = len(list((d / "tests").glob("*.md"))) if (d / "tests").exists() else 0
            skills.append(meta)
    return skills


def list_skill_versions(skill_id: str) -> list[str]:
    """Return version names from .skill.md files + external versions in skill.json."""
    skill_dir = SKILLS_DIR / skill_id
    if not skill_dir.exists():
        return []
    # Discovered .skill.md versions
    versions = {p.stem.replace(".skill", "") for p in skill_dir.glob("*.skill.md")}
    # External versions from skill.json
    meta = load_skill_meta(skill_id)
    if meta:
        for name, info in meta.get("versions", {}).items():
            if isinstance(info, dict) and info.get("external"):
                versions.add(name)
    return sorted(versions)


def get_version_display_name(skill_id: str, version: str) -> str:
    """Return display_name from skill.json versions dict, falling back to the version ID."""
    meta = load_skill_meta(skill_id)
    if meta:
        info = meta.get("versions", {}).get(version)
        if isinstance(info, dict) and info.get("display_name"):
            return info["display_name"]
    return version


def load_skill_version(skill_id: str, version: str) -> str | None:
    """Read one .skill.md file."""
    path = SKILLS_DIR / skill_id / f"{version}.skill.md"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return None


def list_test_docs(skill_id: str) -> list[str]:
    """Glob skills/{skill_id}/tests/*.md, return doc names (stem)."""
    docs_dir = SKILLS_DIR / skill_id / "tests"
    if not docs_dir.exists():
        return []
    return sorted(p.stem for p in docs_dir.glob("*.md"))


def load_test_doc(skill_id: str, doc_name: str) -> str | None:
    """Read one test doc."""
    path = SKILLS_DIR / skill_id / "tests" / f"{doc_name}.md"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return None


def load_answer_key(skill_id: str, doc_name: str) -> dict | None:
    """Read skills/{skill_id}/tests/{doc_name}.json."""
    path = SKILLS_DIR / skill_id / "tests" / f"{doc_name}.json"
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
    business_context: str = "",
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

    user_prompt = skill_meta["user_prompt_template"].format(
        document=doc_text,
        business_context=business_context,
    )

    return system_prompt, user_prompt


def get_scores(result: dict) -> dict:
    """Read judge scores from a result dict, returning {} if absent."""
    return result.get("judge_scores") or {}


# ---------------------------------------------------------------------------
# Parallel Evaluation
# ---------------------------------------------------------------------------

def run_evaluation(
    skill_id: str,
    model_ids: list[str],
    doc_name: str,
    judge_model_key: str | None = None,
    judge_system_prompt: str | None = None,
    version_filter: list[str] | None = None,
    business_context: str = "",
    judge_model_keys: list[str] | None = None,
):
    """Run versions of a skill across selected models in parallel.

    Yields (version, model_id, result_dict) tuples as they complete.
    Uses ThreadPoolExecutor + as_completed().

    When judge_model_key is set, each result is also evaluated by the judge model.
    When judge_model_keys has multiple entries, uses a multi-judge panel
    following the PoLL methodology (Verga et al., 2024).
    When version_filter is set, only those versions are run.
    """
    skill_meta = load_skill_meta(skill_id)
    if not skill_meta:
        return

    versions = list_skill_versions(skill_id)
    if not versions:
        return

    if version_filter:
        versions = [v for v in versions if v in version_filter]
        if not versions:
            return

    doc_text = load_test_doc(skill_id, doc_name)
    if not doc_text:
        return

    answer_key = load_answer_key(skill_id, doc_name)

    def _eval_one(version: str, model_key: str) -> tuple[str, str, dict]:
        cfg = MODEL_CONFIGS[model_key]
        version_text = load_skill_version(skill_id, version)
        if not version_text:
            return version, model_key, {"error": f"Version file not found: {version}"}

        system_prompt, user_prompt = build_prompt(skill_meta, version_text, doc_text, business_context)

        try:
            # Pass model-specific kwargs (e.g. reasoning_effort, temperature)
            model_kwargs = {}
            if cfg.get("reasoning_effort"):
                model_kwargs["reasoning_effort"] = cfg["reasoning_effort"]
            if cfg.get("temperature") is not None:
                model_kwargs["temperature"] = cfg["temperature"]
            if cfg.get("max_tokens"):
                model_kwargs["max_tokens"] = cfg["max_tokens"]
            response = call_model(
                cfg["provider"], cfg["model_id"],
                system_prompt, user_prompt,
                **model_kwargs,
            )

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
                "judge_scores": None,
            }

            save_result(skill_id, version, model_key, doc_name, result)
            return version, model_key, result

        except Exception as e:
            print(f"[eval] {version} x {model_key}: {e}", file=sys.stderr)
            return version, model_key, {"error": str(e)}

    def _eval_external(version: str) -> tuple[str, str, dict]:
        """Load a pre-saved response for an external version."""
        response_text = load_external_response(skill_id, version, doc_name)
        if not response_text:
            return version, "external", {"error": f"Response file not found: responses/{version}/{doc_name}.[md|docx|pdf]"}

        version_info = skill_meta.get("versions", {}).get(version, {})
        source_name = version_info.get("source", "External")

        result = {
            "eval_id": str(uuid.uuid4()),
            "skill_id": skill_id,
            "version": version,
            "doc_name": doc_name,
            "model_key": "external",
            "model_name": source_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "response_text": response_text,
            "input_tokens": 0,
            "output_tokens": 0,
            "elapsed_seconds": 0,
            "quick_scores": None,
            "judge_scores": None,
        }

        save_result(skill_id, version, "external", doc_name, result)
        return version, "external", result

    def _judge_one(version: str, model_key: str, result: dict) -> tuple[str, str, dict]:
        from judge import judge_response, judge_panel

        # Build list of judge models: prefer explicit panel list, else single
        panel_keys = judge_model_keys or ([judge_model_key] if judge_model_key else [])
        panel_keys = [k for k in panel_keys if k]

        try:
            if len(panel_keys) > 1:
                # Multi-judge panel (PoLL methodology)
                judge_scores = judge_panel(
                    doc_text, answer_key, result["response_text"],
                    panel_keys, judge_system_prompt, skill_meta,
                )
            elif panel_keys:
                judge_scores = judge_response(
                    doc_text, answer_key, result["response_text"],
                    panel_keys[0], judge_system_prompt, skill_meta,
                )
            else:
                judge_scores = None

            result["judge_scores"] = judge_scores
            save_result(skill_id, version, model_key, doc_name, result)
        except Exception as e:
            print(f"[judge] {version} x {model_key}: {e}", file=sys.stderr)
        return version, model_key, result

    # Split versions into regular and external
    external_versions = [v for v in versions if is_external_version(skill_id, v)]
    regular_versions = [v for v in versions if v not in external_versions]

    # Build work items: regular versions x all models
    work_items = []
    for version in regular_versions:
        for model_key in model_ids:
            cfg = MODEL_CONFIGS.get(model_key)
            if not cfg or not os.environ.get(cfg["env_key"]):
                continue
            work_items.append((version, model_key))

    # 8 workers: balances API throughput vs rate-limit pressure across providers
    with ThreadPoolExecutor(max_workers=8) as executor:
        # Phase 1a: Run regular evaluations in parallel
        eval_futures = {
            executor.submit(_eval_one, v, mk): (v, mk)
            for v, mk in work_items
        }
        # Phase 1b: Run external evaluations in parallel
        ext_futures = {
            executor.submit(_eval_external, v): (v, "external")
            for v in external_versions
        }

        eval_results = {}
        for future in as_completed(eval_futures):
            version, model_key, result = future.result()
            eval_results[(version, model_key)] = result
            yield version, model_key, result

        for future in as_completed(ext_futures):
            version, model_key, result = future.result()
            eval_results[(version, model_key)] = result
            yield version, model_key, result

        # Phase 2: Run all judge scoring in parallel (if configured)
        if judge_model_key and answer_key:
            judge_futures = {}
            for (v, mk), result in eval_results.items():
                if "error" not in result:
                    future = executor.submit(_judge_one, v, mk, result)
                    judge_futures[future] = (v, mk)

            for future in as_completed(judge_futures):
                version, model_key, result = future.result()
                yield version, model_key, result


@st.cache_data(ttl=60)
def load_skill_meta(skill_id: str) -> dict | None:
    """Load skill.json for a skill_id (cached for 60s)."""
    path = SKILLS_DIR / skill_id / "skill.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def is_external_version(skill_id: str, version: str) -> bool:
    """Check if a version is marked as external in skill.json."""
    meta = load_skill_meta(skill_id)
    if not meta:
        return False
    info = meta.get("versions", {}).get(version)
    return isinstance(info, dict) and info.get("external", False)


def load_external_response(skill_id: str, version: str, doc_name: str) -> str | None:
    """Read a response file from skills/{skill_id}/responses/{version}/{doc_name}.{md,docx,pdf}."""
    resp_dir = SKILLS_DIR / skill_id / "responses" / version

    # Try formats in priority order
    md_path = resp_dir / f"{doc_name}.md"
    if md_path.exists():
        return md_path.read_text(encoding="utf-8")

    docx_path = resp_dir / f"{doc_name}.docx"
    if docx_path.exists():
        from docx import Document
        doc = Document(str(docx_path))
        return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())

    pdf_path = resp_dir / f"{doc_name}.pdf"
    if pdf_path.exists():
        import pymupdf
        doc = pymupdf.open(str(pdf_path))
        return "\n\n".join(page.get_text().strip() for page in doc if page.get_text().strip())

    return None


# ---------------------------------------------------------------------------
# Judge Saved Results
# ---------------------------------------------------------------------------

def judge_saved_results(
    skill_id: str,
    judge_model_key: str,
    judge_system_prompt: str | None = None,
    judge_model_keys: list[str] | None = None,
):
    """Run judge scoring on saved results that don't have judge_scores yet.

    When judge_model_keys has multiple entries, uses a multi-judge panel
    following the PoLL methodology (Verga et al., 2024).

    Yields (completed_count, total_count, result) tuples as each finishes.
    Uses ThreadPoolExecutor for parallel judging.
    """
    from judge import judge_response, judge_panel

    # Build panel list: prefer explicit list, else single key
    panel_keys = judge_model_keys or ([judge_model_key] if judge_model_key else [])
    panel_keys = [k for k in panel_keys if k]

    skill_meta = load_skill_meta(skill_id)
    all_results = load_results(skill_id)

    # Filter to judgeable results
    to_judge = []
    for result in all_results:
        if result.get("judge_scores") is not None:
            continue
        doc_name = result.get("doc_name", "")
        doc_text = load_test_doc(skill_id, doc_name)
        answer_key = load_answer_key(skill_id, doc_name)
        response_text = result.get("response_text", "")
        if doc_text and answer_key and response_text:
            to_judge.append((result, doc_text, answer_key, response_text))

    if not to_judge:
        return

    total = len(to_judge)

    def _judge_one(item):
        result, doc_text, answer_key, response_text = item
        if len(panel_keys) > 1:
            judge_scores = judge_panel(
                doc_text, answer_key, response_text,
                panel_keys, judge_system_prompt, skill_meta,
            )
        else:
            judge_scores = judge_response(
                doc_text, answer_key, response_text,
                panel_keys[0], judge_system_prompt, skill_meta,
            )
        result["judge_scores"] = judge_scores
        save_result(
            skill_id,
            result.get("version", ""),
            result.get("model_key", ""),
            result.get("doc_name", ""),
            result,
        )
        return result

    completed = 0
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(_judge_one, item): item for item in to_judge}
        for future in as_completed(futures):
            completed += 1
            try:
                result = future.result()
                yield completed, total, result
            except Exception:
                yield completed, total, None


def rescore_saved_results(skill_id: str) -> int:
    """Recompute composite scores from existing judge output without re-calling the judge.

    Useful after changing scoring parameters (weights, bonuses, penalties).
    Returns count of results updated.
    """
    from judge import compute_composite_scores

    all_results = load_results(skill_id)
    count = 0

    for result in all_results:
        judge = result.get("judge_scores")
        if not judge:
            continue

        doc_name = result.get("doc_name", "")
        answer_key = load_answer_key(skill_id, doc_name)
        if not answer_key:
            continue

        # Rebuild judge_output dict from stored fields
        judge_output = {
            "recommendation": judge.get("recommendation", {}),
            "issues": judge.get("issues", {}),
            "false_positive_count": judge.get("false_positive_count", 0),
            "false_positives": judge.get("false_positives", []),
        }

        composite = compute_composite_scores(judge_output, answer_key)

        # Update stored scores
        judge["composite_score"] = composite["composite_score"]
        judge["weighted_hit_rate"] = composite["weighted_hit_rate"]
        judge["recommendation_match"] = composite["recommendation_match"]
        judge["issues_found"] = composite["issues_found"]
        judge["issues_total"] = composite["issues_total"]

        save_result(
            skill_id,
            result.get("version", ""),
            result.get("model_key", ""),
            doc_name,
            result,
        )
        count += 1

    return count


# ---------------------------------------------------------------------------
# Result I/O
# ---------------------------------------------------------------------------

def save_result(
    skill_id: str,
    version: str,
    model_key: str,
    doc_name: str,
    result: dict,
) -> Path:
    """Save a result dict. Path: results/{skill_id}/{version}/{model_key}__{doc}.json"""
    out_dir = RESULTS_DIR / skill_id / version
    out_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{model_key}__{doc_name}.json"
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


def build_results_map(
    skill_id: str,
    doc_name: str | None = None,
    model_filter: set[str] | None = None,
) -> tuple[dict[tuple[str, str], dict], set[str]]:
    """Build a {(version, model_key): result} dict from saved results.

    Returns (results_map, model_keys_seen). Filters by doc_name and/or
    model_filter when provided.
    """
    results_map = {}
    model_keys_seen: set[str] = set()
    for r in load_results(skill_id):
        v = r.get("version", "")
        mk = r.get("model_key", "")
        dn = r.get("doc_name", "")
        if not v or not mk:
            continue
        if doc_name and dn != doc_name:
            continue
        if model_filter and mk not in model_filter:
            continue
        results_map[(v, mk)] = r
        model_keys_seen.add(mk)
    return results_map, model_keys_seen
