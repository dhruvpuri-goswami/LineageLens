"""Project links shown in the app (sidebar "GitHub" and "Sponsor" links).

This is the ONE place to configure them. Either edit the defaults below or set the
environment variables ``BUYMEACOFFEE_URL`` / ``GITHUB_REPO_URL`` before starting
LineageLens. Set a value to an empty string to hide that link. A value that still
contains the ``YOUR_USERNAME`` placeholder is treated as unset, so the Sponsor link
stays hidden until a real Buy Me a Coffee page is configured.

They are plain links: the app loads no external scripts, widgets or trackers, and
nothing is fetched from these URLs unless the user clicks them.
"""
from __future__ import annotations

import os

BUYMEACOFFEE_URL = "https://www.buymeacoffee.com/YOUR_USERNAME"
GITHUB_REPO_URL = "https://github.com/dhruvpuri-goswami/LineageLens"
PLACEHOLDER = "YOUR_USERNAME"


def _clean(value: str | None) -> str:
    v = (value or "").strip()
    if PLACEHOLDER in v:
        return ""
    return v if v.startswith(("https://", "http://")) else ""


def get_links() -> dict[str, str]:
    """Return configured links; unset, placeholder or non-http(s) values come back as ``""`` (hidden)."""
    return {
        "buymeacoffee_url": _clean(os.environ.get("BUYMEACOFFEE_URL", BUYMEACOFFEE_URL)),
        "github_repo_url": _clean(os.environ.get("GITHUB_REPO_URL", GITHUB_REPO_URL)),
    }
