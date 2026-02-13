"""Path constants for Skillcheck."""

from pathlib import Path

from dotenv import load_dotenv

load_dotenv(override=True)

BASE_DIR = Path(__file__).parent
SKILLS_DIR = BASE_DIR / "skills"
RESULTS_DIR = BASE_DIR / "results"
