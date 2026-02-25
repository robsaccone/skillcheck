"""DuckDB-backed result persistence for Skillcheck.

Replaces the old JSON-file-per-result scheme with append-only tables
that preserve full run history and support efficient querying.
"""

import hashlib
import json
import sys
import threading
from pathlib import Path

import duckdb

from config import DB_PATH, RESULTS_DIR


# ---------------------------------------------------------------------------
# Connection management
# ---------------------------------------------------------------------------

_local = threading.local()
_write_lock = threading.Lock()


def get_connection() -> duckdb.DuckDBPyConnection:
    """Return a thread-local DuckDB connection, creating schema on first call.

    DuckDB locks the file — only one process at a time (e.g. one Streamlit
    instance). A clear error is raised if the file is already locked.
    """
    con = getattr(_local, "con", None)
    if con is not None:
        try:
            con.execute("SELECT 1")
            return con
        except Exception:
            _local.con = None

    try:
        con = duckdb.connect(str(DB_PATH))
    except duckdb.IOException as e:
        raise RuntimeError(
            f"Could not open {DB_PATH} — is another Streamlit instance running? ({e})"
        ) from e

    _ensure_schema(con)
    _local.con = con
    return con


def _ensure_schema(con: duckdb.DuckDBPyConnection) -> None:
    """Create tables, sequences, and indexes if they don't exist (idempotent)."""
    # Sequence for judge_scores auto-increment PK
    con.execute("CREATE SEQUENCE IF NOT EXISTS judge_scores_id_seq START 1")

    con.execute("""
        CREATE TABLE IF NOT EXISTS results (
            eval_id          VARCHAR PRIMARY KEY,
            skill_id         VARCHAR NOT NULL,
            version          VARCHAR NOT NULL,
            doc_name         VARCHAR NOT NULL,
            model_key        VARCHAR NOT NULL,
            model_name       VARCHAR NOT NULL,
            timestamp        TIMESTAMPTZ NOT NULL,
            system_prompt    VARCHAR NOT NULL DEFAULT '',
            user_prompt      VARCHAR NOT NULL DEFAULT '',
            prompt_text      VARCHAR NOT NULL DEFAULT '',
            doc_text         VARCHAR NOT NULL DEFAULT '',
            answer_key       VARCHAR NOT NULL DEFAULT '',
            business_context VARCHAR NOT NULL DEFAULT '',
            prompt_hash      VARCHAR NOT NULL DEFAULT '',
            doc_hash         VARCHAR NOT NULL DEFAULT '',
            answer_key_hash  VARCHAR NOT NULL DEFAULT '',
            response_text    VARCHAR NOT NULL DEFAULT '',
            input_tokens     INTEGER DEFAULT 0,
            output_tokens    INTEGER DEFAULT 0,
            elapsed_seconds  DOUBLE DEFAULT 0
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS judge_scores (
            id                    INTEGER PRIMARY KEY DEFAULT nextval('judge_scores_id_seq'),
            eval_id               VARCHAR NOT NULL,
            judge_model           VARCHAR NOT NULL,
            timestamp             TIMESTAMPTZ NOT NULL,
            composite_score       DOUBLE,
            weighted_hit_rate     DOUBLE,
            rec_model_said        VARCHAR,
            rec_correct           VARCHAR,
            rec_match             BOOLEAN,
            issues_found          INTEGER,
            issues_total          INTEGER,
            false_positive_count  INTEGER DEFAULT 0,
            false_positives       VARCHAR,
            issues                VARCHAR,
            reasoning             VARCHAR,
            judge_input_tokens    INTEGER DEFAULT 0,
            judge_output_tokens   INTEGER DEFAULT 0,
            judge_elapsed_seconds DOUBLE DEFAULT 0,
            panel_size            INTEGER DEFAULT 1,
            panel_judges          VARCHAR,
            panel_scores          VARCHAR,
            is_latest             BOOLEAN DEFAULT TRUE
        )
    """)

    # Indexes — wrapped in try/except for idempotency
    try:
        con.execute("""
            CREATE INDEX idx_results_lookup
            ON results (skill_id, version, model_key, doc_name, timestamp DESC)
        """)
    except duckdb.CatalogException:
        pass

    try:
        con.execute("""
            CREATE INDEX idx_judge_eval_latest
            ON judge_scores (eval_id, is_latest)
        """)
    except duckdb.CatalogException:
        pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sha256(text: str) -> str:
    """SHA-256 hex digest of a string."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _row_to_result_dict(row: tuple, columns: list[str]) -> dict:
    """Reconstruct a result dict matching the old JSON shape.

    Joins results + latest judge_scores into one dict that the UI
    code already expects.
    """
    d = dict(zip(columns, row))

    result = {
        "eval_id": d.get("eval_id", ""),
        "skill_id": d.get("skill_id", ""),
        "version": d.get("version", ""),
        "doc_name": d.get("doc_name", ""),
        "model_key": d.get("model_key", ""),
        "model_name": d.get("model_name", ""),
        "timestamp": d.get("timestamp", ""),
        "response_text": d.get("response_text", ""),
        "input_tokens": d.get("input_tokens", 0),
        "output_tokens": d.get("output_tokens", 0),
        "elapsed_seconds": d.get("elapsed_seconds", 0),
        "quick_scores": None,
    }

    # Convert timestamp to ISO string if it's a datetime object
    ts = result["timestamp"]
    if hasattr(ts, "isoformat"):
        result["timestamp"] = ts.isoformat()

    # Reconstruct judge_scores sub-dict if judge data is present
    if d.get("j_eval_id") is not None and d.get("composite_score") is not None:
        judge = {
            "judge_model": d.get("judge_model", ""),
            "recommendation": {
                "model_said": d.get("rec_model_said", ""),
                "correct": d.get("rec_correct", ""),
                "match": d.get("rec_match", False),
            },
            "issues": json.loads(d["issues"]) if d.get("issues") else {},
            "false_positive_count": d.get("false_positive_count", 0),
            "false_positives": json.loads(d["false_positives"]) if d.get("false_positives") else [],
            "composite_score": d.get("composite_score", 0),
            "weighted_hit_rate": d.get("weighted_hit_rate", 0),
            "recommendation_match": d.get("rec_match", False),
            "issues_found": d.get("issues_found", 0),
            "issues_total": d.get("issues_total", 0),
            "judge_input_tokens": d.get("judge_input_tokens", 0),
            "judge_output_tokens": d.get("judge_output_tokens", 0),
            "judge_elapsed_seconds": d.get("judge_elapsed_seconds", 0),
        }
        # Panel fields
        if d.get("panel_size", 1) > 1:
            judge["panel_size"] = d.get("panel_size", 1)
            judge["panel_judges"] = json.loads(d["panel_judges"]) if d.get("panel_judges") else []
            judge["panel_scores"] = json.loads(d["panel_scores"]) if d.get("panel_scores") else []
        # Reasoning
        if d.get("reasoning"):
            judge["reasoning"] = json.loads(d["reasoning"])
        result["judge_scores"] = judge
    else:
        result["judge_scores"] = None

    return result


# ---------------------------------------------------------------------------
# Write functions
# ---------------------------------------------------------------------------

def save_result(
    skill_id: str,
    version: str,
    model_key: str,
    doc_name: str,
    result: dict,
) -> str:
    """INSERT a result row into the DB. Returns the eval_id.

    If the result dict contains judge_scores, also saves those.
    """
    eval_id = result.get("eval_id", "")
    if not eval_id:
        import uuid
        eval_id = str(uuid.uuid4())
        result["eval_id"] = eval_id

    con = get_connection()
    with _write_lock:
        # Upsert: skip if eval_id already exists (migration re-runs)
        existing = con.execute(
            "SELECT 1 FROM results WHERE eval_id = ?", [eval_id]
        ).fetchone()
        if existing:
            # If judge_scores present, save them separately
            if result.get("judge_scores"):
                save_judge_scores(eval_id, result["judge_scores"])
            return eval_id

        ts = result.get("timestamp", "")
        system_prompt = result.get("system_prompt", "")
        user_prompt = result.get("user_prompt", "")
        prompt_text = result.get("prompt_text", "")
        doc_text = result.get("doc_text", "")
        answer_key_str = result.get("answer_key", "")
        if isinstance(answer_key_str, dict):
            answer_key_str = json.dumps(answer_key_str, ensure_ascii=False)
        business_context = result.get("business_context", "")

        con.execute("""
            INSERT INTO results (
                eval_id, skill_id, version, doc_name, model_key, model_name,
                timestamp, system_prompt, user_prompt, prompt_text, doc_text,
                answer_key, business_context, prompt_hash, doc_hash,
                answer_key_hash, response_text, input_tokens, output_tokens,
                elapsed_seconds
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            eval_id,
            skill_id,
            version,
            doc_name,
            model_key,
            result.get("model_name", ""),
            ts,
            system_prompt,
            user_prompt,
            prompt_text,
            doc_text,
            answer_key_str,
            business_context,
            _sha256(prompt_text) if prompt_text else "",
            _sha256(doc_text) if doc_text else "",
            _sha256(answer_key_str) if answer_key_str else "",
            result.get("response_text", ""),
            result.get("input_tokens", 0),
            result.get("output_tokens", 0),
            result.get("elapsed_seconds", 0),
        ])

    # Save judge_scores if present
    if result.get("judge_scores"):
        save_judge_scores(eval_id, result["judge_scores"])

    return eval_id


def save_judge_scores(eval_id: str, judge_scores: dict) -> None:
    """Insert a new judge_scores row, marking previous rows as not latest."""
    con = get_connection()
    with _write_lock:
        # Mark existing rows as not latest
        con.execute("""
            UPDATE judge_scores SET is_latest = FALSE
            WHERE eval_id = ? AND is_latest = TRUE
        """, [eval_id])

        rec = judge_scores.get("recommendation", {})
        issues = judge_scores.get("issues", {})
        fps = judge_scores.get("false_positives", [])
        reasoning = judge_scores.get("reasoning")

        from datetime import datetime, timezone
        ts = datetime.now(timezone.utc)

        con.execute("""
            INSERT INTO judge_scores (
                eval_id, judge_model, timestamp, composite_score,
                weighted_hit_rate, rec_model_said, rec_correct, rec_match,
                issues_found, issues_total, false_positive_count,
                false_positives, issues, reasoning,
                judge_input_tokens, judge_output_tokens,
                judge_elapsed_seconds, panel_size, panel_judges, panel_scores,
                is_latest
            ) VALUES (
                ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?,
                ?, ?,
                ?, ?, ?, ?,
                TRUE
            )
        """, [
            eval_id,
            judge_scores.get("judge_model", ""),
            ts,
            judge_scores.get("composite_score"),
            judge_scores.get("weighted_hit_rate"),
            rec.get("model_said", ""),
            rec.get("correct", ""),
            rec.get("match", False),
            judge_scores.get("issues_found", 0),
            judge_scores.get("issues_total", 0),
            judge_scores.get("false_positive_count", 0),
            json.dumps(fps, ensure_ascii=False) if fps else "[]",
            json.dumps(issues, ensure_ascii=False) if issues else "{}",
            json.dumps(reasoning, ensure_ascii=False) if reasoning else None,
            judge_scores.get("judge_input_tokens", 0),
            judge_scores.get("judge_output_tokens", 0),
            judge_scores.get("judge_elapsed_seconds", 0),
            judge_scores.get("panel_size", 1),
            json.dumps(judge_scores["panel_judges"], ensure_ascii=False) if judge_scores.get("panel_judges") else None,
            json.dumps(judge_scores["panel_scores"], ensure_ascii=False) if judge_scores.get("panel_scores") else None,
        ])


# ---------------------------------------------------------------------------
# Read functions
# ---------------------------------------------------------------------------

_RESULTS_WITH_JUDGE_SQL = """
    SELECT r.*,
           j.eval_id          AS j_eval_id,
           j.judge_model,
           j.composite_score,
           j.weighted_hit_rate,
           j.rec_model_said,
           j.rec_correct,
           j.rec_match,
           j.issues_found,
           j.issues_total,
           j.false_positive_count,
           j.false_positives,
           j.issues,
           j.reasoning,
           j.judge_input_tokens,
           j.judge_output_tokens,
           j.judge_elapsed_seconds,
           j.panel_size,
           j.panel_judges,
           j.panel_scores
    FROM results r
    LEFT JOIN judge_scores j ON j.eval_id = r.eval_id AND j.is_latest = TRUE
"""


def load_results(skill_id: str) -> list[dict]:
    """Load all results (with latest judge scores) for a skill."""
    con = get_connection()
    rows = con.execute(
        _RESULTS_WITH_JUDGE_SQL + " WHERE r.skill_id = ? ORDER BY r.timestamp DESC",
        [skill_id],
    ).fetchall()
    columns = [desc[0] for desc in con.description]
    return [_row_to_result_dict(row, columns) for row in rows]


def load_latest_results(skill_id: str) -> list[dict]:
    """Load the most recent result per (version, model_key, doc_name)."""
    all_results = load_results(skill_id)
    latest: dict[tuple[str, str, str], dict] = {}
    for r in all_results:
        key = (r["version"], r["model_key"], r["doc_name"])
        existing = latest.get(key)
        if existing is None or r["timestamp"] > existing["timestamp"]:
            latest[key] = r
    return list(latest.values())


def build_results_map(
    skill_id: str,
    doc_name: str | None = None,
    model_filter: set[str] | None = None,
) -> tuple[dict[tuple[str, str], dict], set[str]]:
    """Build a {(version, model_key): result} dict from saved results.

    Returns (results_map, model_keys_seen). Same signature as the old
    engine.build_results_map for backward compat.
    """
    results = load_latest_results(skill_id)
    results_map = {}
    model_keys_seen: set[str] = set()
    for r in results:
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


def load_result_history(
    skill_id: str, version: str, model_key: str, doc_name: str,
) -> list[dict]:
    """All historical runs for a specific combo, newest first."""
    con = get_connection()
    rows = con.execute(
        _RESULTS_WITH_JUDGE_SQL + """
        WHERE r.skill_id = ? AND r.version = ?
          AND r.model_key = ? AND r.doc_name = ?
        ORDER BY r.timestamp DESC
        """,
        [skill_id, version, model_key, doc_name],
    ).fetchall()
    columns = [desc[0] for desc in con.description]
    return [_row_to_result_dict(row, columns) for row in rows]


def get_recent_runs(limit: int = 8) -> list[dict]:
    """Return recent (skill_id, doc_name, timestamp) groups for the sidebar.

    Groups by (skill_id, doc_name) and returns the most recent timestamp.
    """
    con = get_connection()
    rows = con.execute("""
        SELECT skill_id, doc_name, MAX(timestamp) AS latest_ts
        FROM results
        GROUP BY skill_id, doc_name
        ORDER BY latest_ts DESC
        LIMIT ?
    """, [limit]).fetchall()
    return [
        {"skill_id": r[0], "doc_name": r[1], "timestamp": r[2]}
        for r in rows
    ]


def get_unjudged_results(skill_id: str) -> list[dict]:
    """Results that have no is_latest judge_scores row."""
    con = get_connection()
    rows = con.execute("""
        SELECT r.*
        FROM results r
        LEFT JOIN judge_scores j ON j.eval_id = r.eval_id AND j.is_latest = TRUE
        WHERE r.skill_id = ? AND j.eval_id IS NULL
        ORDER BY r.timestamp DESC
    """, [skill_id]).fetchall()
    columns = [desc[0] for desc in con.description]

    results = []
    for row in rows:
        d = dict(zip(columns, row))
        result = {
            "eval_id": d.get("eval_id", ""),
            "skill_id": d.get("skill_id", ""),
            "version": d.get("version", ""),
            "doc_name": d.get("doc_name", ""),
            "model_key": d.get("model_key", ""),
            "model_name": d.get("model_name", ""),
            "timestamp": d.get("timestamp", ""),
            "response_text": d.get("response_text", ""),
            "input_tokens": d.get("input_tokens", 0),
            "output_tokens": d.get("output_tokens", 0),
            "elapsed_seconds": d.get("elapsed_seconds", 0),
            "quick_scores": None,
            "judge_scores": None,
        }
        ts = result["timestamp"]
        if hasattr(ts, "isoformat"):
            result["timestamp"] = ts.isoformat()
        results.append(result)
    return results


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------

def migrate_json_results(results_dir: Path | None = None) -> int:
    """Scan results/**/*.json and insert each into the DB.

    Skips duplicates by eval_id. Returns count of results migrated.
    """
    if results_dir is None:
        results_dir = RESULTS_DIR
    if not results_dir.exists():
        return 0

    count = 0
    for path in results_dir.rglob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue

        eval_id = data.get("eval_id")
        if not eval_id:
            continue

        # Derive skill_id and version from path: results/{skill_id}/{version}/{file}.json
        try:
            rel = path.relative_to(results_dir)
            parts = rel.parts
            if len(parts) >= 2:
                skill_id = parts[0]
                version = parts[1]
            else:
                skill_id = data.get("skill_id", "")
                version = data.get("version", "")
        except ValueError:
            skill_id = data.get("skill_id", "")
            version = data.get("version", "")

        model_key = data.get("model_key", "")
        doc_name = data.get("doc_name", "")

        # Migrated results don't have prompt/doc/answer_key text — store empty
        result = {
            "eval_id": eval_id,
            "skill_id": skill_id,
            "version": version,
            "doc_name": doc_name,
            "model_key": model_key,
            "model_name": data.get("model_name", ""),
            "timestamp": data.get("timestamp", ""),
            "system_prompt": "",
            "user_prompt": "",
            "prompt_text": "",
            "doc_text": "",
            "answer_key": "",
            "business_context": "",
            "response_text": data.get("response_text", ""),
            "input_tokens": data.get("input_tokens", 0),
            "output_tokens": data.get("output_tokens", 0),
            "elapsed_seconds": data.get("elapsed_seconds", 0),
            "judge_scores": data.get("judge_scores"),
        }

        try:
            save_result(skill_id, version, model_key, doc_name, result)
            count += 1
        except Exception as e:
            print(f"[migrate] Failed to import {path}: {e}", file=sys.stderr)

    return count
