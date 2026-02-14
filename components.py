"""Shared UI helpers and constants for Skillcheck."""

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SEVERITY_EMOJI = {"CRITICAL": "\U0001f534", "HIGH": "\U0001f7e0", "MODERATE": "\U0001f535", "LOW": "\u26aa"}

TIER_LABEL = {"must_catch": "3\u00d7", "should_catch": "2\u00d7", "nice_to_catch": "1\u00d7"}


# ---------------------------------------------------------------------------
# Badge & chip helpers
# ---------------------------------------------------------------------------

def severity_badge_html(severity: str) -> str:
    s = severity.lower()
    return f'<span class="badge-{s}">{severity}</span>'


def severity_prefix(severity: str) -> str:
    return SEVERITY_EMOJI.get(severity.upper(), "") + " " + severity


def detection_chip(label: str, detected: bool) -> str:
    cls = "chip-hit" if detected else "chip-miss"
    icon = "\u2705" if detected else "\u274c"
    return f'<span class="{cls}">{icon} {label}</span>'
