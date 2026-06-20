from __future__ import annotations

import re
import unicodedata
from typing import Any


def parse_bibtex(text: str) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for part in re.split(r"\n(?=@)", text.strip()):
        match = re.match(r"@(\w+)\{([^,]+),", part)
        if not match:
            continue
        entry_type, key = match.group(1).lower(), match.group(2).strip()
        fields = {"entry_type": entry_type, "key": key}
        for field, value in re.findall(r"(\w+)\s*=\s*[\{\"]((?:[^{}\"]|\{[^{}]*\})*)[\}\"]", part, re.S):
            value = value.replace("\n", " ")
            value = re.sub(r"\s+", " ", value).strip()
            value = value.replace("{", "").replace("}", "")
            fields[field.lower()] = value
        entries.append(fields)
    return entries


def ascii_id(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    return text or "paper"


def split_authors(author_field: str) -> list[str]:
    if not author_field:
        return []
    return [a.strip() for a in re.split(r"\s+and\s+", author_field) if a.strip()]


def infer_type(entry: dict[str, str]) -> str:
    entry_type = entry.get("entry_type", "")
    title = entry.get("title", "").lower()
    journal = entry.get("journal", "").lower()
    haystack = " ".join([entry_type, title, journal])
    title_only = " ".join([entry_type, title])
    if entry_type == "book":
        return "book"
    if entry_type in {"incollection", "inproceedings"}:
        return "chapter"
    if any(word in title_only for word in ["meta-analysis", "literature review", "systematic review", "survey"]):
        return "review"
    if any(word in haystack for word in ["scale", "measuring", "measurement", "validity", "construct"]):
        return "measurement"
    if any(word in haystack for word in ["experiment", "game", "trust", "deception", "cheating", "betrayal"]):
        return "experiment"
    if any(word in haystack for word in ["theory", "model", "equilibrium", "bayesian", "informational cascade"]):
        return "theory"
    if any(word in haystack for word in ["algorithm", "machine learning", "neural", "transformer", "llm", "benchmark"]):
        return "ai_ml"
    if any(word in haystack for word in ["data", "regression", "panel", "instrument", "development"]):
        return "empirical"
    return "other"


def citation(entry: dict[str, str]) -> str:
    authors = split_authors(entry.get("author", ""))
    author_text = ", ".join(authors)
    year = entry.get("year", "")
    title = entry.get("title", "")
    venue = entry.get("journal") or entry.get("booktitle") or entry.get("publisher") or ""
    volume = entry.get("volume", "")
    number = entry.get("number", "")
    pages = entry.get("pages", "")
    bits: list[str] = []
    if author_text:
        bits.append(author_text)
    if year:
        bits.append(f"({year}).")
    if title:
        bits.append(title + ".")
    if venue:
        venue_bit = venue
        if volume:
            venue_bit += f", {volume}"
        if number:
            venue_bit += f"({number})"
        if pages:
            venue_bit += f", {pages}"
        bits.append(venue_bit + ".")
    return " ".join(bits)


def record_from_bib(entry: dict[str, str], category: str) -> dict[str, Any]:
    doi = entry.get("doi", "")
    url = f"https://doi.org/{doi}" if doi else entry.get("url", "")
    title = entry.get("title", "")
    rec_id = entry.get("key") or ascii_id(f"{entry.get('year', '')}-{title}")
    return {
        "id": rec_id,
        "type": infer_type(entry),
        "category": category,
        "citation": citation(entry),
        "year": entry.get("year", ""),
        "title": title,
        "authors": split_authors(entry.get("author", "")),
        "doi": doi,
        "url": url,
        "summary": "",
        "design": [],
        "findings": [],
        "keywords": [],
        "project_note": "",
        "needs_review": True,
        "source": "BibTeX metadata",
    }
