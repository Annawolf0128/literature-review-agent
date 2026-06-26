from __future__ import annotations

import csv
import html
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


CROSSREF_API = "https://api.crossref.org/works"

ECON_TOP_VENUES = {
    "american economic review",
    "econometrica",
    "quarterly journal of economics",
    "journal of political economy",
    "review of economic studies",
    "review of economics and statistics",
    "journal of economic literature",
    "journal of economic perspectives",
}

ECON_FIELD_VENUE_TERMS = [
    "games and economic behavior",
    "experimental economics",
    "journal of economic behavior",
    "journal of economic theory",
    "journal of public economics",
    "journal of development economics",
    "journal of finance",
    "journal of financial economics",
    "review of financial studies",
    "management science",
]

INTERDISCIPLINARY_VENUES = {
    "nature",
    "science",
    "proceedings of the national academy of sciences",
    "pnas",
    "nature human behaviour",
}


def normalize_text(value: Any) -> str:
    return html.unescape(re.sub(r"\s+", " ", str(value or "")).strip())


def first_text(value: Any) -> str:
    if isinstance(value, list) and value:
        return normalize_text(value[0])
    return normalize_text(value)


def candidate_key(doi: Any, title: Any) -> str:
    """Stable dedupe key for a candidate/paper: bare DOI if present, else a
    whitespace/punctuation-stripped title."""
    doi = normalize_text(doi).lower()
    if doi:
        return doi
    return re.sub(r"\W+", "", normalize_text(title).lower())


def crossref_year(item: dict[str, Any]) -> str:
    for key in ["published-print", "published-online", "published", "created", "issued"]:
        parts = item.get(key, {}).get("date-parts")
        if parts and parts[0]:
            return str(parts[0][0])
    return ""


def crossref_authors(item: dict[str, Any]) -> list[str]:
    authors = []
    for author in item.get("author", [])[:8]:
        given = normalize_text(author.get("given", ""))
        family = normalize_text(author.get("family", ""))
        name = normalize_text(f"{family}, {given}" if family and given else family or given)
        if name:
            authors.append(name)
    return authors


def project_terms(config: dict[str, Any], query: str) -> list[str]:
    pieces = [query]
    project = config.get("project", {}) if isinstance(config.get("project"), dict) else {}
    pieces.extend([project.get("topic", ""), project.get("main_question", "")])
    scope = config.get("literature_scope", {}) if isinstance(config.get("literature_scope"), dict) else {}
    pieces.extend(scope.get("include", []) or [])
    raw = " ".join(normalize_text(p) for p in pieces).lower()
    terms = []
    stopwords = {
        "about",
        "analysis",
        "central",
        "clarify",
        "credible",
        "design",
        "directly",
        "economics",
        "empirical",
        "field",
        "formal",
        "foundational",
        "generic",
        "highly",
        "inform",
        "journal",
        "mechanism",
        "papers",
        "project",
        "question",
        "related",
        "repeatedly",
        "that",
        "this",
        "unless",
        "with",
        "work",
    }
    for term in re.findall(r"[a-z][a-z\-]{3,}", raw):
        if term not in stopwords:
            terms.append(term)
    return sorted(set(terms))


def venue_score(venue: str, discipline: str) -> tuple[int, list[str]]:
    venue_l = venue.lower()
    why = []
    score = 0
    if venue_l in ECON_TOP_VENUES:
        score += 30
        why.append("top economics journal")
    if any(term in venue_l for term in ECON_FIELD_VENUE_TERMS):
        score += 20
        why.append("leading field journal")
    if venue_l in INTERDISCIPLINARY_VENUES:
        score += 18
        why.append("major interdisciplinary journal")
    if discipline.lower() not in {"economics", "econ"} and venue:
        score += 3
    return score, why


def candidate_score(candidate: dict[str, Any], config: dict[str, Any], terms: list[str]) -> tuple[int, list[str]]:
    project = config.get("project", {}) if isinstance(config.get("project"), dict) else {}
    discipline = normalize_text(project.get("discipline", ""))
    title = candidate.get("title", "")
    abstract = candidate.get("abstract", "")
    venue = candidate.get("venue", "")
    haystack = " ".join([title, abstract, venue]).lower()
    score = 0
    why = []

    matched_terms = [term for term in terms if term in haystack]
    if matched_terms:
        score += min(30, len(matched_terms) * 3)
        why.append("topic terms: " + ", ".join(matched_terms[:6]))

    v_score, v_why = venue_score(venue, discipline)
    score += v_score
    why.extend(v_why)

    citations = candidate.get("is_referenced_by_count") or 0
    if citations >= 1000:
        score += 20
        why.append("highly cited")
    elif citations >= 250:
        score += 12
        why.append("well cited")
    elif citations >= 50:
        score += 6
        why.append("moderately cited")

    title_l = title.lower()
    if any(core in title_l for core in ["trust game", "investment game", "reputation", "social capital"]):
        score += 12
        why.append("title is close to common project mechanisms")
    if candidate.get("doi"):
        score += 2

    return score, why or ["metadata match"]


def crossref_search(query: str, rows: int = 30, mailto: str = "") -> list[dict[str, Any]]:
    params = {
        "query.bibliographic": query,
        "rows": str(rows),
        "select": "DOI,title,author,published-print,published-online,published,issued,container-title,type,URL,is-referenced-by-count,abstract",
    }
    if mailto:
        params["mailto"] = mailto
    url = CROSSREF_API + "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={"User-Agent": "literature-review-agent/0.1"})
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload.get("message", {}).get("items", [])


def candidates_from_crossref(items: list[dict[str, Any]], config: dict[str, Any], query: str) -> list[dict[str, Any]]:
    terms = project_terms(config, query)
    candidates = []
    seen = set()
    for item in items:
        doi = normalize_text(item.get("DOI", "")).lower()
        title = first_text(item.get("title"))
        key = candidate_key(doi, title)
        if not key or key in seen or not title:
            continue
        seen.add(key)
        venue = first_text(item.get("container-title"))
        candidate = {
            "accepted": False,
            "relevance_score": 0,
            "why": [],
            "title": title,
            "authors": crossref_authors(item),
            "year": crossref_year(item),
            "venue": venue,
            "doi": doi,
            "url": f"https://doi.org/{doi}" if doi else normalize_text(item.get("URL", "")),
            "type": normalize_text(item.get("type", "")),
            "is_referenced_by_count": item.get("is-referenced-by-count", 0),
            "abstract": normalize_text(re.sub(r"<[^>]+>", "", item.get("abstract", ""))),
            "source": "Crossref",
        }
        score, why = candidate_score(candidate, config, terms)
        candidate["relevance_score"] = score
        candidate["why"] = why
        candidates.append(candidate)
    candidates.sort(key=lambda c: (c.get("relevance_score", 0), c.get("is_referenced_by_count", 0)), reverse=True)
    return candidates


def candidates_from_openalex(works: list[dict[str, Any]], config: dict[str, Any], query: str) -> list[dict[str, Any]]:
    # Imported lazily: openalex.py imports from discover.py, so a top-level
    # import here would be circular.
    from .openalex import work_to_candidate

    terms = project_terms(config, query)
    candidates = []
    seen = set()
    for work in works:
        candidate = work_to_candidate(work)
        title = candidate.get("title", "")
        key = candidate_key(candidate.get("doi", ""), title)
        if not key or key in seen or not title:
            continue
        seen.add(key)
        score, why = candidate_score(candidate, config, terms)
        candidate["relevance_score"] = score
        candidate["why"] = why
        candidates.append(candidate)
    candidates.sort(key=lambda c: (c.get("relevance_score", 0), c.get("is_referenced_by_count", 0) or 0), reverse=True)
    return candidates


def merge_candidate_lists(*lists: list[dict[str, Any]], exclude_keys: set[str] | None = None) -> list[dict[str, Any]]:
    """Combine candidate lists from different sources, deduping by candidate_key.
    Keeps the highest relevance score, unions the 'why' and 'source' provenance,
    keeps the largest citation count, and backfills empty metadata fields."""
    exclude = exclude_keys or set()
    merged: dict[str, dict[str, Any]] = {}
    for candidates in lists:
        for candidate in candidates:
            key = candidate_key(candidate.get("doi", ""), candidate.get("title", ""))
            if not key or key in exclude:
                continue
            if key not in merged:
                merged[key] = dict(candidate)
                continue
            existing = merged[key]
            if candidate.get("relevance_score", 0) > existing.get("relevance_score", 0):
                existing["relevance_score"] = candidate["relevance_score"]
            existing["why"] = list(dict.fromkeys((existing.get("why") or []) + (candidate.get("why") or [])))
            source_parts: list[str] = []
            for source in [existing.get("source", ""), candidate.get("source", "")]:
                for piece in str(source).split(";"):
                    piece = piece.strip()
                    if piece and piece not in source_parts:
                        source_parts.append(piece)
            existing["source"] = "; ".join(source_parts)
            existing["is_referenced_by_count"] = max(
                existing.get("is_referenced_by_count", 0) or 0,
                candidate.get("is_referenced_by_count", 0) or 0,
            )
            for field in ("abstract", "pdf_url", "venue", "year", "url", "openalex_id", "authors"):
                if not existing.get(field) and candidate.get(field):
                    existing[field] = candidate[field]
    result = list(merged.values())
    result.sort(key=lambda c: (c.get("relevance_score", 0), c.get("is_referenced_by_count", 0) or 0), reverse=True)
    return result


def review_data_keys(data: dict[str, Any]) -> set[str]:
    keys = set()
    for paper in data.get("papers", []):
        key = candidate_key(paper.get("doi", ""), paper.get("title", ""))
        if key:
            keys.add(key)
    return keys


def seed_dois_from_data(data: dict[str, Any]) -> list[str]:
    dois = []
    for paper in data.get("papers", []):
        doi = normalize_text(paper.get("doi", "")).lower()
        if doi:
            dois.append(doi)
    return list(dict.fromkeys(dois))


def candidates_from_citations(
    data: dict[str, Any],
    config: dict[str, Any],
    mailto: str = "",
    direction: str = "both",
    max_per_paper: int = 25,
    query: str = "",
) -> list[dict[str, Any]]:
    """Citation-chasing discovery: from the DOIs already in the review, follow
    OpenAlex references (papers they cite) and/or citations (papers that cite
    them) to surface new candidates, excluding anything already in the review."""
    from . import openalex as oa

    exclude = review_data_keys(data)
    project = config.get("project", {}) if isinstance(config.get("project"), dict) else {}
    query = query or project.get("topic", "") or project.get("title", "")

    referenced: list[str] = []
    citing_works: list[dict[str, Any]] = []
    for doi in seed_dois_from_data(data):
        work = oa.fetch_work_by_doi(doi, mailto=mailto)
        if not work:
            continue
        if direction in ("references", "both"):
            referenced.extend(oa.referenced_ids(work)[:max_per_paper])
        if direction in ("citations", "both"):
            citing_works.extend(
                oa.fetch_citing_works(work.get("id", ""), mailto=mailto, max_results=max_per_paper)
            )

    works: list[dict[str, Any]] = []
    if referenced:
        works.extend(oa.fetch_works_by_ids(referenced, mailto=mailto))
    works.extend(citing_works)

    candidates = candidates_from_openalex(works, config, query)
    for candidate in candidates:
        candidate["why"] = list(dict.fromkeys((candidate.get("why") or []) + ["found via citation chasing"]))
    return merge_candidate_lists(candidates, exclude_keys=exclude)


def candidate_to_review_record(candidate: dict[str, Any], category: str) -> dict[str, Any]:
    doi = normalize_text(candidate.get("doi", "")).lower()
    title = normalize_text(candidate.get("title", ""))
    rec_id = doi.replace("/", "-").replace(".", "-") if doi else re.sub(r"[^a-zA-Z0-9]+", "-", title.lower()).strip("-")
    citation_bits = []
    authors = candidate.get("authors", []) or []
    if authors:
        citation_bits.append(", ".join(authors))
    if candidate.get("year"):
        citation_bits.append(f"({candidate.get('year')}).")
    if title:
        citation_bits.append(title + ".")
    venue = normalize_text(candidate.get("venue", ""))
    if venue:
        citation_bits.append(venue + ".")
    return {
        "id": rec_id or "candidate-paper",
        "type": "other",
        "category": category,
        "citation": " ".join(citation_bits),
        "year": normalize_text(candidate.get("year", "")),
        "title": title,
        "authors": authors,
        "doi": doi,
        "url": candidate.get("url", ""),
        "summary": "",
        "design": [],
        "findings": [],
        "keywords": [],
        "project_note": "; ".join(candidate.get("why", [])),
        "needs_review": True,
        "source": candidate.get("source", "candidate search"),
    }


def load_accepted_candidates(path: str | Path, category: str) -> list[dict[str, Any]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    candidates = payload.get("candidates", payload if isinstance(payload, list) else [])
    return [candidate_to_review_record(candidate, category) for candidate in candidates if candidate.get("accepted") is True]


def write_candidates_json(candidates: list[dict[str, Any]], output: str | Path, query: str) -> Path:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"query": query, "count": len(candidates), "candidates": candidates}
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def write_candidates_csv(candidates: list[dict[str, Any]], output: str | Path) -> Path:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["accepted", "relevance_score", "title", "authors", "year", "venue", "doi", "url", "is_referenced_by_count", "why"]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for candidate in candidates:
            writer.writerow({
                "accepted": candidate.get("accepted", False),
                "relevance_score": candidate.get("relevance_score", 0),
                "title": candidate.get("title", ""),
                "authors": "; ".join(candidate.get("authors", [])),
                "year": candidate.get("year", ""),
                "venue": candidate.get("venue", ""),
                "doi": candidate.get("doi", ""),
                "url": candidate.get("url", ""),
                "is_referenced_by_count": candidate.get("is_referenced_by_count", 0),
                "why": "; ".join(candidate.get("why", [])),
            })
    return path
