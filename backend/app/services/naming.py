"""Episode naming: keep meaningful file names, replace generic ones with a date and time."""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

GENERIC = re.compile(
    r"^(?:audio|recording|record|rec|voice|voice memo|new recording|untitled|track|output|video|clip|sound|podcast|episode|"
    r"file|capture|screen recording|zoom|meeting|pasted transcript|transcript|text|download|remote episode)?[\s_.-]*\d*$"
    r"|^[0-9a-f-]{16,}$"
    r"|^(?:img|vid|mov|dsc|pxl|wa|audio|rec|voice)?[\s_.-]*\d{6,}.*$",
    re.IGNORECASE,
)


def dated_name(now: datetime | None = None) -> str:
    moment = now or datetime.now()
    return f"Episode {moment:%Y-%m-%d %H:%M}"


def is_generic(name: str) -> bool:
    stem = Path(name).stem if "." in name else name
    cleaned = re.sub(r"[_\-.]+", " ", stem).strip()
    return len(cleaned) < 3 or bool(GENERIC.match(cleaned))


def display_name_for(asset_name: str | None, now: datetime | None = None) -> str:
    """Empty string means "use the asset or generated title"; a generic or missing name gets a date."""
    if not asset_name or is_generic(asset_name):
        return dated_name(now)
    return ""


def adopt_title(job, title: str | None) -> None:  # noqa: ANN001 - ProcessingJob
    """A generated date name gives way to the first title the user chooses."""
    if title and title.strip() and job.auto_named:
        job.display_name = " ".join(title.split())[:200]
        job.auto_named = False


def file_name_for(display: str, suffix: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", display).strip("-").lower() or "episode"
    return f"{slug[:120]}{suffix}"
