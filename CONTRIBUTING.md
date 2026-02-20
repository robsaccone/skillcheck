# Contributing to Skillcheck

Thanks for your interest in contributing! This project benefits most from new skills, test documents, and answer keys — the more tasks we can evaluate, the better.

## Ways to Contribute

### Add a New Skill

1. Create a directory under `skills/` with your skill ID (e.g., `skills/lease_review/`)
2. Add a `skill.json` with metadata:
   - `skill_id`, `display_name`, `system_prompt_prefix`, `user_prompt_template`
   - The user template should include `{document}` and `{business_context}` placeholders
3. Add one or more `.skill.md` files — each is a complete prompt version
4. Add test documents (`.md`) and expert answer keys (`.json`) to a `tests/` subdirectory
5. Restart the app — your skill appears automatically

See `skills/nda_review/` for a complete working example.

### Add Test Documents and Answer Keys

Good test documents have:
- Realistic content that an attorney would actually review
- A mix of obvious and subtle issues across severity tiers
- Clear, unambiguous answer keys with rubric descriptions

Answer key format (JSON):
- `issues[]` — each with `id`, `section`, `title`, `severity` (H/M/L), `description`, `rubric`
- `business_context` — scenario framing for the review
- `expected_recommendation` — what the correct overall recommendation should be
- Optional: `false_positive_traps[]`, `scoring_notes`

### Improve the Scoring Methodology

If you find cases where the scoring produces unintuitive results, file an issue with:
- The specific skill, model, and test document
- What the score was vs. what you expected
- Why you think the methodology should change

### Bug Fixes and Enhancements

1. Fork the repo and create a branch
2. Make your changes
3. Test locally with `streamlit run app.py`
4. Open a PR with a clear description of what changed and why

## Development Setup

```bash
git clone https://github.com/rsaccone/skillcheck.git
cd skillcheck
python -m venv .venv

# Activate
# macOS/Linux: source .venv/bin/activate
# Windows: .venv\Scripts\activate

pip install -r requirements.txt
cp .env.example .env
# Add at least one API key to .env

streamlit run app.py
```

## Code Style

- All functions, no classes
- Python 3.12+ type hints (`str | None`, `list[dict]`)
- Section headers use `# ---...---` comment blocks
- API clients are lazily imported inside functions

## Licensing

- The evaluation harness, test documents, answer keys, and custom skills are MIT licensed
- If you contribute a skill based on external work, note the original license in the skill file
- By opening a PR, you agree that your contribution is licensed under MIT

## Questions?

Open an issue or reach out to [@rsaccone](https://github.com/rsaccone).
