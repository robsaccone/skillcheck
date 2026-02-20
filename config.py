"""Path constants and scoring parameters for Skillcheck."""

from pathlib import Path

from dotenv import load_dotenv

load_dotenv(override=True)

BASE_DIR = Path(__file__).parent
SKILLS_DIR = BASE_DIR / "skills"
RESULTS_DIR = BASE_DIR / "results"

# Scoring: composite = severity-weighted hit rate (0-100) + rec bonus - FP penalty
RECOMMENDATION_BONUS = 10
FP_PENALTY_PER = 2
SEVERITY_WEIGHTS = {"H": 3, "M": 2, "L": 1}
