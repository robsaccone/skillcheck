"""Path constants for Skillcheck."""

from pathlib import Path

from dotenv import load_dotenv

load_dotenv(override=True)

BASE_DIR = Path(__file__).parent
SKILLS_DIR = BASE_DIR / "skills"
RESULTS_DIR = BASE_DIR / "results"

DEFAULT_SCORING_WEIGHTS = {
    "weighted_issue_score": 0.50,
    "completeness": 0.15,
    "precision": 0.10,
    "professional_quality": 0.15,
    "classification_accuracy": 0.10,
}
