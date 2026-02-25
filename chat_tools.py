"""Tool functions and system prompt for the data-aware chat feature.

Tools are plain Python functions with typed parameters and Google-style
docstrings.  aisuite auto-generates JSON schemas from these and handles
the tool-calling loop across providers.
"""

import contextlib
import io
import json

import db
from engine import discover_skills, list_skill_versions, list_test_docs


# ---------------------------------------------------------------------------
# Tool functions
# ---------------------------------------------------------------------------

def query_results(sql: str) -> str:
    """Run a read-only SQL query against the evaluation database.

    Use this for ad-hoc questions about scores, models, documents, or any
    data in the results and judge_scores tables.  Only SELECT queries are
    allowed.

    Args:
        sql: A SQL SELECT query.  Tables: results, judge_scores.
    """
    cleaned = sql.strip().lstrip("(").strip()
    first_word = cleaned.split()[0].upper() if cleaned else ""
    if first_word not in ("SELECT", "WITH", "EXPLAIN"):
        return "Error: only SELECT / WITH / EXPLAIN queries are allowed."

    try:
        con = db.get_connection()
        result = con.execute(sql)
        columns = [desc[0] for desc in result.description]
        rows = result.fetchmany(50)
    except Exception as e:
        return f"SQL error: {e}"

    if not rows:
        return "(no rows returned)"

    # Format as markdown table
    header = "| " + " | ".join(columns) + " |"
    sep = "| " + " | ".join("---" for _ in columns) + " |"
    lines = [header, sep]
    for row in rows:
        cells = []
        for v in row:
            s = str(v) if v is not None else ""
            if len(s) > 80:
                s = s[:77] + "..."
            cells.append(s)
        lines.append("| " + " | ".join(cells) + " |")

    total_count = ""
    if len(rows) == 50:
        total_count = "\n\n(truncated at 50 rows)"

    return "\n".join(lines) + total_count


def compare_batches(skill_id: str, version: str, last_n: int = 5) -> str:
    """Compare evaluation results across time-batched revisions.

    Groups results into batches by 20-minute time windows and shows
    per-document average scores, recommendation accuracy, and false positive
    rates.  Shows a delta between the first and last batch.

    Args:
        skill_id: The skill identifier (e.g. "nda_review").
        version: The prompt version to compare (e.g. "combined").
        last_n: Number of most recent batches to show.  Defaults to 5.
    """
    from cli import _doc_averages, _group_into_batches

    results = db.load_results(skill_id)
    filtered = [r for r in results if r.get("version") == version]
    if not filtered:
        return f"No results found for {skill_id}/{version}."

    docs = list_test_docs(skill_id)
    batches = _group_into_batches(filtered)
    if not batches:
        return "No scored results found."

    if last_n and last_n < len(batches):
        batches = batches[-last_n:]

    lines: list[str] = []
    batch_stats = []

    for i, batch in enumerate(batches):
        ts = str(batch[0].get("timestamp", ""))[:16]
        stats = _doc_averages(batch, docs)
        batch_stats.append(stats)

        all_s = [s["score"] for s in stats.values() if s["score"] is not None]
        all_r = [s["rec_pct"] for s in stats.values() if s["rec_pct"] is not None]
        all_f = [s["fp"] for s in stats.values() if s["fp"] is not None]
        avg = sum(all_s) / len(all_s) if all_s else 0
        avg_rec = sum(all_r) / len(all_r) if all_r else 0
        avg_fp = sum(all_f) / len(all_f) if all_f else 0

        parts = [f"run{i} ({ts}, n={len(batch)}): AVG={avg:.1f}%, Rec={avg_rec:.0f}%, FP={avg_fp:.1f}"]
        for doc in docs:
            s = stats[doc]
            if s["score"] is not None:
                parts.append(f"  {doc}: {s['score']:.1f}%")
        lines.append("\n".join(parts))

    # Delta
    if len(batch_stats) >= 2:
        first, last = batch_stats[0], batch_stats[-1]
        deltas = []
        for doc in docs:
            f_s, l_s = first[doc]["score"], last[doc]["score"]
            if f_s is not None and l_s is not None:
                deltas.append(f"  {doc}: {l_s - f_s:+.1f}%")
        if deltas:
            lines.append("DELTA (first -> last):\n" + "\n".join(deltas))

    return "\n\n".join(lines)


def diagnose_issues(skill_id: str, version: str, doc_name: str = "") -> str:
    """Diagnose evaluation failures for a skill version.

    Shows per-model issue detection matrix, false positive frequency, and
    recommendation accuracy.  Useful for understanding why scores are low
    and identifying specific prompt improvements.

    Args:
        skill_id: The skill identifier (e.g. "nda_review").
        version: The prompt version to diagnose (e.g. "combined").
        doc_name: Optional test document name to filter to.  Omit for all docs.
    """
    import argparse
    from cli import cmd_diagnose

    # Build a fake args namespace matching what cmd_diagnose expects
    args = argparse.Namespace(
        skill=skill_id,
        version=version,
        doc=doc_name or None,
        run="latest",
    )

    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            cmd_diagnose(args)
    except SystemExit:
        pass  # cmd_diagnose calls sys.exit on error

    output = buf.getvalue()
    if not output.strip():
        return f"No scored results for {skill_id}/{version}."
    # Replace em-dash separators with ASCII dashes to avoid unicode escaping
    # in aisuite's JSON serialization, and trim excessive separator lines.
    output = output.replace("—", "-")
    return output


def list_skills() -> str:
    """List all available skills, their prompt versions, and test documents.

    Returns a structured summary of what skill_id, version, and doc_name
    values are valid for use with other tools.
    """
    skills = discover_skills()
    if not skills:
        return "No skills found."

    lines: list[str] = []
    for s in skills:
        sid = s.get("skill_id", "?")
        name = s.get("display_name", sid)
        versions = list_skill_versions(sid)
        docs = list_test_docs(sid)
        lines.append(f"Skill: {name} (id={sid})")
        lines.append(f"  Versions: {', '.join(versions) if versions else '(none)'}")
        lines.append(f"  Test docs: {', '.join(docs) if docs else '(none)'}")

    return "\n".join(lines)


def get_db_schema() -> str:
    """Show database table schemas and row counts.

    Use this to understand column names and types before writing SQL queries
    with the query_results tool.
    """
    con = db.get_connection()
    lines: list[str] = []

    for table in ("results", "judge_scores"):
        cols = con.execute(f"DESCRIBE {table}").fetchall()
        count = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        lines.append(f"Table: {table} ({count} rows)")
        for col in cols:
            lines.append(f"  {col[0]}: {col[1]}")
        lines.append("")

    lines.append("Join pattern: results r JOIN judge_scores j ON j.eval_id = r.eval_id AND j.is_latest = TRUE")
    lines.append("Scores: composite_score is 0.0-1.0 — multiply by 100 for percentage.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tools list (passed to aisuite)
# ---------------------------------------------------------------------------

TOOLS = [query_results, compare_batches, diagnose_issues, list_skills, get_db_schema]


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

def build_system_prompt() -> str:
    """Build the system prompt with live skill/version/doc data."""
    skills = discover_skills()
    skill_lines = []
    for s in skills:
        sid = s.get("skill_id", "?")
        versions = list_skill_versions(sid)
        docs = list_test_docs(sid)
        skill_lines.append(f"- {sid}: versions=[{', '.join(versions)}], docs=[{', '.join(docs)}]")
    skills_block = "\n".join(skill_lines) if skill_lines else "(none discovered)"

    return f"""You are a data analyst for Skillcheck, an internal tool that evaluates AI models on legal document analysis.

## What Skillcheck Does
Skills (prompt templates) are tested against test documents with expert answer keys. Multiple AI models run each skill, then a judge LLM scores the response: composite score (0-100), per-issue detection, recommendation match, and false positives.

## Database
Two tables in DuckDB:
- results: eval_id, skill_id, version, doc_name, model_key, model_name, timestamp, response_text, input_tokens, output_tokens, elapsed_seconds
- judge_scores: eval_id, judge_model, composite_score (0.0-1.0), weighted_hit_rate, rec_match, rec_model_said, rec_correct, issues_found, issues_total, false_positive_count, false_positives (JSON), issues (JSON), is_latest
Join: results r JOIN judge_scores j ON j.eval_id = r.eval_id AND j.is_latest = TRUE

## Scoring
composite = severity-weighted issue hit rate (0-100) + recommendation bonus (+10 if correct) - FP penalty (2 per FP)
Stored as 0.0-1.0. Severity weights: H=3, M=2, L=1.

## Available Data
{skills_block}

## Guidelines
- Use compare_batches for trend analysis and diagnose_issues for failure investigation
- Use query_results for ad-hoc SQL questions
- Always multiply composite_score by 100 when showing percentages
- Keep answers concise — this is an internal dev tool"""
