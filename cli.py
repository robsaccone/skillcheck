"""CLI tools for running evals, comparing revisions, and diagnosing failures.

Usage:
    python cli.py run-eval --skill nda_review --version combined
    python cli.py compare  --skill nda_review --version combined --last 5
    python cli.py diagnose --skill nda_review --version combined --doc vanilla_mutual
"""

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(override=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_skill_meta(skill_id: str) -> dict | None:
    """Load skill.json without Streamlit dependency."""
    from config import SKILLS_DIR

    path = SKILLS_DIR / skill_id / "skill.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def _parse_timestamp(ts: str) -> datetime:
    """Parse an ISO timestamp string, stripping timezone suffixes."""
    cleaned = str(ts).replace("+00:00", "").replace("Z", "")
    # Truncate sub-second precision if needed
    if "." in cleaned:
        cleaned = cleaned[:cleaned.index(".") + 7]  # max 6 decimal places
    return datetime.fromisoformat(cleaned)


def _group_into_batches(results: list[dict], gap_minutes: int = 20) -> list[list[dict]]:
    """Group results into time-based batches separated by gaps."""
    if not results:
        return []
    scored = [r for r in results
              if r.get("judge_scores") and "composite_score" in r.get("judge_scores", {})]
    scored.sort(key=lambda r: str(r.get("timestamp", "")))

    batches: list[list[dict]] = []
    current: list[dict] = []

    for r in scored:
        ts_str = str(r.get("timestamp", ""))
        if not current:
            current = [r]
            continue
        prev_str = str(current[-1].get("timestamp", ""))
        try:
            t1 = _parse_timestamp(prev_str)
            t2 = _parse_timestamp(ts_str)
            if (t2 - t1).total_seconds() > gap_minutes * 60:
                batches.append(current)
                current = [r]
            else:
                current.append(r)
        except (ValueError, TypeError):
            current.append(r)

    if current:
        batches.append(current)
    return batches


def _doc_averages(results: list[dict], docs: list[str]) -> dict[str, dict]:
    """Compute per-doc averages for score, rec accuracy, FP rate."""
    stats: dict[str, dict] = {}
    for doc in docs:
        doc_r = [r for r in results if r["doc_name"] == doc]
        if not doc_r:
            stats[doc] = {"score": None, "rec_pct": None, "fp": None, "n": 0}
            continue
        scores = [r["judge_scores"]["composite_score"] * 100 for r in doc_r]
        recs = [1 if r["judge_scores"].get("recommendation", {}).get("match") else 0 for r in doc_r]
        fps = [r["judge_scores"].get("false_positive_count", 0) for r in doc_r]
        stats[doc] = {
            "score": sum(scores) / len(scores),
            "rec_pct": sum(recs) / len(recs) * 100,
            "fp": sum(fps) / len(fps),
            "n": len(doc_r),
        }
    return stats


# ---------------------------------------------------------------------------
# run-eval
# ---------------------------------------------------------------------------

def cmd_run_eval(args: argparse.Namespace) -> None:
    """Run skill evaluations across models and test documents."""
    from engine import list_skill_versions, list_test_docs, load_answer_key, run_evaluation
    from models import get_available_models

    skill_id = args.skill
    meta = _load_skill_meta(skill_id)
    if not meta:
        print(f"Error: skill '{skill_id}' not found.", file=sys.stderr)
        sys.exit(1)

    # Resolve versions
    if args.version:
        versions = [v.strip() for v in args.version.split(",")]
    else:
        versions = list_skill_versions(skill_id)
    if not versions:
        print("Error: no versions found.", file=sys.stderr)
        sys.exit(1)

    # Resolve docs
    if args.docs:
        docs = [d.strip() for d in args.docs.split(",")]
    else:
        docs = list_test_docs(skill_id)
    if not docs:
        print("Error: no test documents found.", file=sys.stderr)
        sys.exit(1)

    # Resolve models
    available = get_available_models()
    if args.models:
        model_ids = [m.strip() for m in args.models.split(",")]
        missing = [m for m in model_ids if m not in available]
        if missing:
            print(f"Warning: models not available (no API key): {', '.join(missing)}", file=sys.stderr)
            model_ids = [m for m in model_ids if m in available]
    else:
        model_ids = list(available.keys())

    if not model_ids:
        print("Error: no models available. Check API keys in .env.", file=sys.stderr)
        sys.exit(1)

    judge_key = args.judge or "claude-opus-4-6"

    print(f"Skill:    {skill_id}")
    print(f"Versions: {', '.join(versions)}")
    print(f"Docs:     {', '.join(docs)}")
    print(f"Models:   {len(model_ids)} ({', '.join(model_ids)})")
    print(f"Judge:    {judge_key}")
    print()

    # Track results for summary
    summary: list[dict] = []

    for doc in docs:
        ak = load_answer_key(skill_id, doc)
        biz_ctx = ak.get("business_context", "") if ak else ""
        print(f"=== {doc} ({len(model_ids)} models) ===")

        for version, model_key, result in run_evaluation(
            skill_id, model_ids, doc,
            judge_model_key=judge_key,
            version_filter=versions,
            business_context=biz_ctx,
        ):
            if "error" in result:
                print(f"  {model_key}: ERROR - {result['error']}")
            else:
                js = result.get("judge_scores")
                if js and "composite_score" in js:
                    score = js["composite_score"] * 100
                    rec = js.get("recommendation", {}).get("model_said", "?")
                    fp = js.get("false_positive_count", 0)
                    found = js.get("issues_found", 0)
                    total = js.get("issues_total", 0)
                    print(f"  {model_key}: {score:.0f}% | rec={rec} | issues={found}/{total} | fp={fp}")
                    summary.append({
                        "doc": doc, "version": version, "model": model_key,
                        "score": score, "rec": rec, "fp": fp,
                        "found": found, "total": total,
                        "rec_match": js.get("recommendation", {}).get("match", False),
                    })
                else:
                    print(f"  {model_key}: eval done (no judge score yet)")
        print()

    # Summary table
    if summary:
        _print_run_summary(summary, docs)


def _print_run_summary(summary: list[dict], docs: list[str]) -> None:
    """Print a summary table after an eval run."""
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    for doc in docs:
        doc_rows = [s for s in summary if s["doc"] == doc]
        if not doc_rows:
            continue
        avg_score = sum(s["score"] for s in doc_rows) / len(doc_rows)
        rec_pct = sum(1 for s in doc_rows if s["rec_match"]) / len(doc_rows) * 100
        avg_fp = sum(s["fp"] for s in doc_rows) / len(doc_rows)
        print(f"  {doc}: {avg_score:.1f}% avg | rec={rec_pct:.0f}% | fp={avg_fp:.1f}")

    all_scores = [s["score"] for s in summary]
    all_rec = [s["rec_match"] for s in summary]
    all_fp = [s["fp"] for s in summary]
    overall = sum(all_scores) / len(all_scores)
    overall_rec = sum(all_rec) / len(all_rec) * 100
    overall_fp = sum(all_fp) / len(all_fp)
    print(f"\n  OVERALL: {overall:.1f}% avg | rec={overall_rec:.0f}% | fp={overall_fp:.1f}")


# ---------------------------------------------------------------------------
# compare
# ---------------------------------------------------------------------------

def cmd_compare(args: argparse.Namespace) -> None:
    """Compare evaluation results across skill revisions."""
    import db
    from engine import list_test_docs

    skill_id = args.skill
    version = args.version
    last_n = args.last

    results = db.load_results(skill_id)
    filtered = [r for r in results if r.get("version") == version]
    if not filtered:
        print(f"No results found for {skill_id}/{version}.", file=sys.stderr)
        sys.exit(1)

    docs = list_test_docs(skill_id)
    batches = _group_into_batches(filtered)

    if not batches:
        print("No scored results found.", file=sys.stderr)
        sys.exit(1)

    if last_n and last_n < len(batches):
        batches = batches[-last_n:]

    # Header
    print(f"{'Batch':<8} {'Time':<20} {'N':>3}", end="")
    for doc in docs:
        label = doc[:10]
        print(f" {label:>10}", end="")
    print(f" {'AVG':>8} {'Rec%':>6} {'FP':>5}")
    print("-" * (38 + 11 * len(docs)))

    batch_stats: list[dict[str, dict]] = []

    for i, batch in enumerate(batches):
        ts = str(batch[0].get("timestamp", ""))[:16]
        n = len(batch)
        stats = _doc_averages(batch, docs)
        batch_stats.append(stats)

        all_scores = [s["score"] for s in stats.values() if s["score"] is not None]
        all_recs = [s["rec_pct"] for s in stats.values() if s["rec_pct"] is not None]
        all_fps = [s["fp"] for s in stats.values() if s["fp"] is not None]
        avg = sum(all_scores) / len(all_scores) if all_scores else 0
        avg_rec = sum(all_recs) / len(all_recs) if all_recs else 0
        avg_fp = sum(all_fps) / len(all_fps) if all_fps else 0

        print(f"run{i:<4} {ts:<20} {n:>3}", end="")
        for doc in docs:
            s = stats[doc]
            if s["score"] is not None:
                print(f" {s['score']:>8.1f}%", end="")
            else:
                print(f" {'N/A':>9}", end="")
        print(f" {avg:>7.1f}% {avg_rec:>5.0f}% {avg_fp:>5.1f}")

    # Delta (first vs last)
    if len(batch_stats) >= 2:
        first = batch_stats[0]
        last = batch_stats[-1]
        print()
        print(f"{'DELTA':<8} {'(first->last)':<20} {'':>3}", end="")
        for doc in docs:
            f_s = first[doc]["score"]
            l_s = last[doc]["score"]
            if f_s is not None and l_s is not None:
                delta = l_s - f_s
                print(f" {delta:>+8.1f}%", end="")
            else:
                print(f" {'N/A':>9}", end="")
        # Overall delta
        f_all = [s["score"] for s in first.values() if s["score"] is not None]
        l_all = [s["score"] for s in last.values() if s["score"] is not None]
        if f_all and l_all:
            delta_avg = (sum(l_all) / len(l_all)) - (sum(f_all) / len(f_all))
            print(f" {delta_avg:>+7.1f}%", end="")
        print()


# ---------------------------------------------------------------------------
# diagnose
# ---------------------------------------------------------------------------

def cmd_diagnose(args: argparse.Namespace) -> None:
    """Diagnose evaluation failures — issue detection, FPs, recommendations."""
    import db
    from engine import list_test_docs, load_answer_key

    skill_id = args.skill
    version = args.version
    doc_filter = args.doc

    results = db.load_results(skill_id)
    filtered = [r for r in results if r.get("version") == version
                and r.get("judge_scores") and "composite_score" in r.get("judge_scores", {})]

    if not filtered:
        print(f"No scored results for {skill_id}/{version}.", file=sys.stderr)
        sys.exit(1)

    # Get the target batch
    batches = _group_into_batches(filtered)
    if not batches:
        print("No scored results found.", file=sys.stderr)
        sys.exit(1)

    if args.run == "latest":
        target = batches[-1]
    else:
        try:
            idx = int(args.run)
            target = batches[idx]
        except (ValueError, IndexError):
            print(f"Invalid --run value: {args.run}. Use 'latest' or a batch index.", file=sys.stderr)
            sys.exit(1)

    docs = [doc_filter] if doc_filter else list_test_docs(skill_id)

    for doc in docs:
        doc_results = [r for r in target if r["doc_name"] == doc]
        if not doc_results:
            continue
        doc_results.sort(key=lambda r: r["model_key"])

        ak = load_answer_key(skill_id, doc)
        if not ak:
            print(f"Warning: no answer key for {doc}, skipping.", file=sys.stderr)
            continue

        issues = ak.get("issues", [])
        expected_rec = ak.get("expected_recommendation", "?")

        print("=" * 80)
        print(f"{doc.upper()}: Per-model breakdown  (expected rec: {expected_rec})")
        print("=" * 80)

        # Per-model detail
        for r in doc_results:
            js = r["judge_scores"]
            model = r["model_key"]
            score = js["composite_score"] * 100
            rec = js.get("recommendation", {}).get("model_said", "?")
            rec_match = js.get("recommendation", {}).get("match", False)
            fp = js.get("false_positive_count", 0)
            fp_list = js.get("false_positives", [])
            issues_map = js.get("issues", {})

            status = "OK" if rec_match else "WRONG"
            print(f"\n{model:<25} {score:>5.0f}%  rec={rec:<12} [{status}]  fp={fp}")

            for iss in issues:
                found = issues_map.get(iss["id"], 0)
                marker = "Y" if found else "."
                print(f"  [{marker}] {iss['id']:<12} [{iss['severity']}] {iss['title']}")

            if fp_list:
                print(f"  FALSE POSITIVES:")
                for fp_item in fp_list:
                    desc = fp_item.get("issue", str(fp_item)) if isinstance(fp_item, dict) else str(fp_item)
                    print(f"    - {desc[:100]}")

        # Aggregate issue hit rates
        print(f"\n{'—' * 80}")
        print(f"{doc.upper()}: Issue hit rates across {len(doc_results)} models")
        print("—" * 80)
        for iss in issues:
            hits = sum(1 for r in doc_results
                       if r["judge_scores"].get("issues", {}).get(iss["id"], 0))
            total = len(doc_results)
            pct = hits / total * 100 if total else 0
            print(f"  {iss['id']:<12} [{iss['severity']}] {hits}/{total} ({pct:.0f}%)  {iss['title']}")

        # FP frequency
        print(f"\n{'—' * 80}")
        print(f"{doc.upper()}: False positive frequency")
        print("—" * 80)
        fp_counter: Counter = Counter()
        for r in doc_results:
            fps = r["judge_scores"].get("false_positives", [])
            for fp_item in fps:
                desc = fp_item.get("issue", str(fp_item)) if isinstance(fp_item, dict) else str(fp_item)
                fp_counter[desc] += 1

        if fp_counter:
            for fp_desc, count in fp_counter.most_common(20):
                print(f"  {count}x: {fp_desc[:100]}")
        else:
            print("  (none)")

        print()


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Skillcheck CLI — run evals, compare revisions, diagnose failures",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python cli.py run-eval --skill nda_review --version combined
  python cli.py compare  --skill nda_review --version combined --last 5
  python cli.py diagnose --skill nda_review --version combined --doc vanilla_mutual
        """,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # run-eval
    p_run = sub.add_parser("run-eval", help="Run skill evaluations across models and test docs")
    p_run.add_argument("--skill", required=True, help="Skill ID (e.g. nda_review)")
    p_run.add_argument("--version", help="Comma-separated versions (default: all)")
    p_run.add_argument("--docs", help="Comma-separated doc names (default: all)")
    p_run.add_argument("--models", help="Comma-separated model keys (default: all available)")
    p_run.add_argument("--judge", default="claude-opus-4-6", help="Judge model key (default: claude-opus-4-6)")
    p_run.set_defaults(func=cmd_run_eval)

    # compare
    p_cmp = sub.add_parser("compare", help="Compare results across revisions (time-batched)")
    p_cmp.add_argument("--skill", required=True, help="Skill ID")
    p_cmp.add_argument("--version", required=True, help="Version to compare")
    p_cmp.add_argument("--last", type=int, default=5, help="Show last N batches (default: 5)")
    p_cmp.set_defaults(func=cmd_compare)

    # diagnose
    p_diag = sub.add_parser("diagnose", help="Diagnose failures — issue matrix, FPs, recommendations")
    p_diag.add_argument("--skill", required=True, help="Skill ID")
    p_diag.add_argument("--version", required=True, help="Version to diagnose")
    p_diag.add_argument("--doc", help="Filter to one test doc (default: all)")
    p_diag.add_argument("--run", default="latest", help="Batch to analyze: 'latest' or index (default: latest)")
    p_diag.set_defaults(func=cmd_diagnose)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
