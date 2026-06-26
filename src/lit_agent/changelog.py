from __future__ import annotations

import datetime as dt
from typing import Any

from .discover import candidate_key, normalize_text


# Fields whose changes are worth recording in the changelog. Volatile bookkeeping
# fields (e.g. needs_review) are deliberately excluded.
TRACKED_FIELDS = (
    "title",
    "year",
    "authors",
    "venue",
    "doi",
    "url",
    "type",
    "category",
    "abstract",
    "summary",
    "design",
    "findings",
    "keywords",
    "pdf_url",
    "cited_by_count",
)


def index_papers(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Map each paper to its stable candidate_key (bare DOI, else title)."""
    index: dict[str, dict[str, Any]] = {}
    for paper in data.get("papers", []) or []:
        key = candidate_key(paper.get("doi", ""), paper.get("title", ""))
        if key and key not in index:
            index[key] = paper
    return index


def _normalize_value(value: Any) -> Any:
    """Comparable form of a field value so cosmetic differences don't register."""
    if isinstance(value, list):
        return [normalize_text(v) if isinstance(v, str) else v for v in value]
    if isinstance(value, str):
        return normalize_text(value)
    return value


def changed_fields(old: dict[str, Any], new: dict[str, Any]) -> list[str]:
    """Tracked fields whose value differs between two records."""
    fields = []
    for field in TRACKED_FIELDS:
        if _normalize_value(old.get(field)) != _normalize_value(new.get(field)):
            fields.append(field)
    return fields


def diff_reviews(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    """Compare two review-data states and return added/removed/updated papers."""
    old_index = index_papers(old)
    new_index = index_papers(new)

    added = [new_index[k] for k in new_index if k not in old_index]
    removed = [old_index[k] for k in old_index if k not in new_index]
    updated = []
    for key in new_index:
        if key not in old_index:
            continue
        fields = changed_fields(old_index[key], new_index[key])
        if fields:
            updated.append({"paper": new_index[key], "fields": fields})
    return {"added": added, "removed": removed, "updated": updated}


def diff_is_empty(diff: dict[str, Any]) -> bool:
    return not (diff.get("added") or diff.get("removed") or diff.get("updated"))


def paper_label(paper: dict[str, Any]) -> str:
    """One-line human label: 'Family et al. (Year) Title'."""
    authors = paper.get("authors", []) or []
    if authors:
        first = normalize_text(authors[0]).split(",")[0]
        who = first + (" et al." if len(authors) > 1 else "")
    else:
        who = "Unknown"
    year = normalize_text(paper.get("year", ""))
    title = normalize_text(paper.get("title", "")) or "(untitled)"
    head = f"{who} ({year})" if year else who
    return f"{head} {title}".strip()


def render_changelog_section(diff: dict[str, Any], date: str = "", action: str = "") -> str:
    """Render a single dated changelog section in Markdown."""
    date = date or str(dt.date.today())
    heading = f"## {date}" + (f" — {action}" if action else "")
    lines = [heading, ""]
    if diff_is_empty(diff):
        lines.append("_No changes._")
        return "\n".join(lines) + "\n"

    added = diff.get("added", [])
    removed = diff.get("removed", [])
    updated = diff.get("updated", [])

    if added:
        lines.append(f"### Added ({len(added)})")
        lines.append("")
        for paper in added:
            lines.append(f"- {paper_label(paper)}")
        lines.append("")
    if removed:
        lines.append(f"### Removed ({len(removed)})")
        lines.append("")
        for paper in removed:
            lines.append(f"- {paper_label(paper)}")
        lines.append("")
    if updated:
        lines.append(f"### Updated ({len(updated)})")
        lines.append("")
        for entry in updated:
            fields = ", ".join(entry.get("fields", []))
            lines.append(f"- {paper_label(entry['paper'])} — {fields}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def prepend_changelog(existing: str, section: str, title: str = "Changelog") -> str:
    """Put the newest section at the top, below a stable top-level title."""
    section = section.rstrip() + "\n"
    header = f"# {title}\n\n"
    existing = existing or ""
    if existing.startswith(f"# {title}"):
        # Strip the existing title line(s) and keep the prior sections.
        rest = existing.split("\n", 1)[1] if "\n" in existing else ""
        rest = rest.lstrip("\n")
        return f"{header}{section}\n{rest}".rstrip() + "\n"
    return f"{header}{section}\n{existing}".rstrip() + "\n"
