"""Model configurations and constants for Skillcheck."""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(override=True)

BASE_DIR = Path(__file__).parent
SKILLS_DIR = BASE_DIR / "skills"
RESULTS_DIR = BASE_DIR / "results"

MODEL_CONFIGS = {
    "claude-opus-4-6": {
        "provider": "anthropic",
        "model_id": "claude-opus-4-6",
        "display_name": "Claude Opus 4.6",
        "env_key": "ANTHROPIC_API_KEY",
    },
    "claude-sonnet-4-5": {
        "provider": "anthropic",
        "model_id": "claude-sonnet-4-5-20250929",
        "display_name": "Claude Sonnet 4.5",
        "env_key": "ANTHROPIC_API_KEY",
    },
    "gpt-4o": {
        "provider": "openai",
        "model_id": "gpt-4o",
        "display_name": "GPT-4o",
        "env_key": "OPENAI_API_KEY",
    },
    "gemini-2.5-pro": {
        "provider": "google",
        "model_id": "gemini-2.5-pro-preview-06-05",
        "display_name": "Gemini 2.5 Pro",
        "env_key": "GOOGLE_API_KEY",
    },
    "llama-3.3-70b": {
        "provider": "together",
        "model_id": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
        "display_name": "Llama 3.3 70B",
        "env_key": "TOGETHER_API_KEY",
    },
}


def get_available_models():
    """Return model configs whose API keys are present in the environment."""
    available = {}
    for key, cfg in MODEL_CONFIGS.items():
        if os.environ.get(cfg["env_key"]):
            available[key] = cfg
    return available
