from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Iterable

from .discover import normalize_text


OPENALEX_API = "https://api.openalex.org/works"
USER_AGENT = "literature-review-agent/0.1"

# Fields requested from OpenAlex. Keeping this explicit keeps payloads small and
# makes the network behaviour easy to reason about.
WORK_SELECT = ",".join(
    [
        "id",
        "doi",
        "title",
        "display_name",
        "publication_year",
        "authorships",
        "primary_location",
        "abstract_inverted_index",
        "cited_by_count",
        "referenced_works",
        "concepts",
        "type",
        "best_oa_location",
    ]
)


# --------------------------------------------------------------------------- #
# Pure helpers (no network) -- these are the unit-tested core.
# --------------------------------------------------------------------------- #
def reconstruct_abstract(inverted_index: dict[str, list[int]] | None) -> str:
    """Rebuild plain abstract text from OpenAlex's abstract_inverted_index.

    OpenAlex stores abstracts as {word: [positions]}. We invert that back into
    ordered text. Returns "" when the index is missing or malformed.
    """
    if not isinstance(inverted_index, dict) or not inverted_index:
        return ""
    positions: list[tuple[int, str]] = []
    for word, idxs in inverted_index.items():
        if not isinstance(idxs, list):
            continue
        for idx in idxs:
            if isinstance(idx, int):
                positions.append((idx, word))
    if not positions:
        return ""
    positions.sort(key=lambda pair: pair[0])
    return normalize_text(" ".join(word for _, word in positions))


def short_id(openalex_id: Any) -> str:
    """Turn a full OpenAlex id URL (https://openalex.org/W123) into 'W123'."""
    text = normalize_text(openalex_id)
    if not text:
        return ""
    return text.rstrip("/").rsplit("/", 1)[-1]


def bare_doi(doi: Any) -> str:
    """Strip a DOI URL down to the bare '10.xxxx/...' form, lowercased."""
    text = normalize_text(doi).lower()
    if not text:
        return ""
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if text.startswith(prefix):
            text = text[len(prefix):]
            break
    return text


def author_name(display_name: str) -> str:
    """Convert an OpenAlex 'Given Middle Family' display name to 'Family, Given'."""
    clean = normalize_text(display_name)
    if not clean or "," in clean:
        return clean
    parts = clean.split(" ")
    if len(parts) < 2:
        return clean
    family = parts[-1]
    given = " ".join(parts[:-1])
    return f"{family}, {given}"


def openalex_authors(work: dict[str, Any], limit: int = 8) -> list[str]:
    authors = []
    for authorship in work.get("authorships", [])[:limit]:
        author = authorship.get("author", {}) if isinstance(authorship, dict) else {}
        name = author_name(author.get("display_name", ""))
        if name:
            authors.append(name)
    return authors


def openalex_year(work: dict[str, Any]) -> str:
    year = work.get("publication_year")
    return str(year) if year else ""


def openalex_venue(work: dict[str, Any]) -> str:
    location = work.get("primary_location") or {}
    source = location.get("source") or {} if isinstance(location, dict) else {}
    return normalize_text(source.get("display_name", ""))


def openalex_title(work: dict[str, Any]) -> str:
    return normalize_text(work.get("title") or work.get("display_name") or "")


def openalex_type(work: dict[str, Any]) -> str:
    return normalize_text(work.get("type", ""))


def openalex_cited_by_count(work: dict[str, Any]) -> int:
    value = work.get("cited_by_count")
    return value if isinstance(value, int) else 0


def openalex_doi(work: dict[str, Any]) -> str:
    return bare_doi(work.get("doi", ""))


def openalex_concepts(work: dict[str, Any], min_score: float = 0.3, limit: int = 8) -> list[str]:
    concepts = []
    for concept in work.get("concepts", []):
        if not isinstance(concept, dict):
            continue
        score = concept.get("score")
        if isinstance(score, (int, float)) and score < min_score:
            continue
        name = normalize_text(concept.get("display_name", "")).lower()
        if name and name not in concepts:
            concepts.append(name)
        if len(concepts) >= limit:
            break
    return concepts


def openalex_oa_pdf_url(work: dict[str, Any]) -> str:
    location = work.get("best_oa_location")
    if not isinstance(location, dict):
        return ""
    return normalize_text(location.get("pdf_url") or location.get("landing_page_url") or "")


def referenced_ids(work: dict[str, Any]) -> list[str]:
    ids = []
    for ref in work.get("referenced_works", []):
        sid = short_id(ref)
        if sid:
            ids.append(sid)
    return ids


def work_to_candidate(work: dict[str, Any]) -> dict[str, Any]:
    """Shape an OpenAlex work like a discover.py candidate so the existing
    candidate_score() can rank OpenAlex and Crossref results identically."""
    doi = openalex_doi(work)
    title = openalex_title(work)
    return {
        "accepted": False,
        "relevance_score": 0,
        "why": [],
        "title": title,
        "authors": openalex_authors(work),
        "year": openalex_year(work),
        "venue": openalex_venue(work),
        "doi": doi,
        "url": f"https://doi.org/{doi}" if doi else normalize_text(work.get("id", "")),
        "type": openalex_type(work),
        "is_referenced_by_count": openalex_cited_by_count(work),
        "abstract": reconstruct_abstract(work.get("abstract_inverted_index")),
        "pdf_url": openalex_oa_pdf_url(work),
        "openalex_id": short_id(work.get("id", "")),
        "source": "OpenAlex",
    }


# --------------------------------------------------------------------------- #
# Network layer -- isolated behind one function so tests can monkeypatch it.
# --------------------------------------------------------------------------- #
def _http_get_json(url: str, mailto: str = "", timeout: int = 30) -> dict[str, Any]:
    if mailto:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}mailto={urllib.parse.quote(mailto)}"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return {}


def fetch_work_by_doi(doi: str, mailto: str = "") -> dict[str, Any]:
    doi = bare_doi(doi)
    if not doi:
        return {}
    doi_url = f"https://doi.org/{doi}"
    params = urllib.parse.urlencode({"filter": f"doi:{doi_url}", "select": WORK_SELECT})
    payload = _http_get_json(f"{OPENALEX_API}?{params}", mailto=mailto)
    results = payload.get("results", []) if isinstance(payload, dict) else []
    return results[0] if results else {}


def fetch_works_by_ids(ids: Iterable[str], mailto: str = "", chunk: int = 50) -> list[dict[str, Any]]:
    unique = [sid for sid in dict.fromkeys(short_id(i) for i in ids) if sid]
    works: list[dict[str, Any]] = []
    for start in range(0, len(unique), chunk):
        batch = unique[start:start + chunk]
        params = urllib.parse.urlencode(
            {
                "filter": "openalex_id:" + "|".join(batch),
                "select": WORK_SELECT,
                "per-page": str(len(batch)),
            }
        )
        payload = _http_get_json(f"{OPENALEX_API}?{params}", mailto=mailto)
        works.extend(payload.get("results", []) if isinstance(payload, dict) else [])
    return works


def fetch_citing_works(work_short_id: str, mailto: str = "", max_results: int = 25) -> list[dict[str, Any]]:
    sid = short_id(work_short_id)
    if not sid or max_results <= 0:
        return []
    per_page = min(200, max_results)
    params = urllib.parse.urlencode(
        {
            "filter": f"cites:{sid}",
            "select": WORK_SELECT,
            "per-page": str(per_page),
            "sort": "cited_by_count:desc",
        }
    )
    payload = _http_get_json(f"{OPENALEX_API}?{params}", mailto=mailto)
    results = payload.get("results", []) if isinstance(payload, dict) else []
    return results[:max_results]


def search_works(query: str, rows: int = 30, mailto: str = "") -> list[dict[str, Any]]:
    query = normalize_text(query)
    if not query:
        return []
    params = urllib.parse.urlencode(
        {
            "search": query,
            "select": WORK_SELECT,
            "per-page": str(min(200, max(1, rows))),
            "sort": "relevance_score:desc",
        }
    )
    payload = _http_get_json(f"{OPENALEX_API}?{params}", mailto=mailto)
    return payload.get("results", []) if isinstance(payload, dict) else []
