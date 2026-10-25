"""Project links shown in the app (sidebar "Support this project" and "Star on GitHub").

This is the ONE place to configure them. Either edit the defaults below or set the
environment variables ``BUYMEACOFFEE_URL`` / ``GITHUB_REPO_URL`` before starting
LineageLens. Set a value to an empty string to hide that link.

They are plain links: the app loads no external scripts, widgets or trackers, and
nothing is fetched from these URLs unless the user clicks them.
"""
from __future__ import annotations

import os

BUYMEACOFFEE_URL = "https://www.buymeacoffee.com/YOUR_USERNAME"
GITHUB_REPO_URL = "https://github.com/YOUR_USERNAME/lineagelens"


def _clean(value: str | None) -> str:
    v = (value or "").strip()
    return v if v.startswith(("https://", "http://")) else ""


def get_links() -> dict[str, str]:
    """Return configured links; unset or non-http(s) values come back as ``""`` (hidden)."""
    return {
        "buymeacoffee_url": _clean(os.environ.get("BUYMEACOFFEE_URL", BUYMEACOFFEE_URL)),
        "github_repo_url": _clean(os.environ.get("GITHUB_REPO_URL", GITHUB_REPO_URL)),
    }
