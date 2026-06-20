from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .discover import CROSSREF_API, crossref_authors, crossref_year, first_text, normalize_text, project_terms


def strip_markup(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value or "")
    return normalize_text(value)


def sentence_split(text: str) -> list[str]:
    clean = normalize_text(text)
    if not clean:
        return []
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", clean) if part.strip()]


def crossref_work(doi: str, mailto: str = "") -> dict[str, Any]:
    doi = normalize_text(doi).lower()
    if not doi:
        return {}
    params = {"mailto": mailto} if mailto else {}
    url = f"{CROSSREF_API}/{urllib.parse.quote(doi, safe='')}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={"User-Agent": "literature-review-agent/0.1"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return {}
    return payload.get("message", {}) if isinstance(payload, dict) else {}


def infer_paper_type(paper: dict[str, Any], abstract: str = "") -> str:
    existing = normalize_text(paper.get("type", "")).lower()
    if existing and existing != "other":
        return existing
    text = " ".join([paper.get("title", ""), paper.get("venue", ""), abstract]).lower()
    if any(term in text for term in ["experiment", "experimental", "laboratory", "lab experiment", "field experiment", "trust game", "investment game"]):
        return "experiment"
    if any(term in text for term in ["model", "equilibrium", "repeated game", "bellman", "dynamic", "theory"]):
        return "theory"
    if any(term in text for term in ["survey", "scale", "measure", "validity", "elicitation"]):
        return "measurement"
    if any(term in text for term in ["data", "panel", "regression", "identification", "estimate"]):
        return "empirical"
    if any(term in text for term in ["review", "meta-analysis", "literature"]):
        return "review"
    if any(term in text for term in ["algorithm", "machine learning", "neural", "large language model", "classification"]):
        return "ai_ml"
    return existing or "other"


def compose_citation(paper: dict[str, Any]) -> str:
    authors = paper.get("authors", []) or []
    parts = []
    if authors:
        parts.append(", ".join(authors))
    if paper.get("year"):
        parts.append(f"({paper.get('year')}).")
    if paper.get("title"):
        parts.append(f"{paper.get('title')}.")
    if paper.get("venue"):
        parts.append(f"{paper.get('venue')}.")
    return " ".join(parts)


def update_metadata_from_crossref(paper: dict[str, Any], item: dict[str, Any], overwrite: bool = False) -> bool:
    changed = False
    fields = {
        "title": first_text(item.get("title")),
        "year": crossref_year(item),
        "authors": crossref_authors(item),
        "doi": normalize_text(item.get("DOI", "")).lower(),
        "url": f"https://doi.org/{normalize_text(item.get('DOI', '')).lower()}" if item.get("DOI") else normalize_text(item.get("URL", "")),
        "venue": first_text(item.get("container-title")),
    }
    for field, value in fields.items():
        if not value:
            continue
        if overwrite or not paper.get(field):
            paper[field] = value
            changed = True
    if (overwrite or not paper.get("citation")) and compose_citation(paper):
        paper["citation"] = compose_citation(paper)
        changed = True
    return changed


def extract_keywords(paper: dict[str, Any], abstract: str, config: dict[str, Any]) -> list[str]:
    title = normalize_text(paper.get("title", "")).lower()
    text = " ".join([title, abstract.lower()])
    candidates = project_terms(config, title)
    manual_terms = [
        "trust game",
        "investment game",
        "reputation",
        "repeated interaction",
        "social capital",
        "noise",
        "attribution",
        "risk preference",
        "belief updating",
        "reciprocity",
        "reinvestment",
    ]
    keywords = [term for term in manual_terms if term in text]
    for term in candidates:
        if term in text and term not in keywords:
            keywords.append(term)
    return keywords[:8]


def draft_summary(paper: dict[str, Any], abstract: str) -> str:
    title = normalize_text(paper.get("title", "this paper"))
    venue = normalize_text(paper.get("venue", ""))
    sentences = sentence_split(abstract)
    if sentences:
        return " ".join(sentences[:2])[:700]
    if venue:
        return f"Metadata record for {title} in {venue}. Full-text review is still needed before using this as substantive evidence."
    return f"Metadata record for {title}. Full-text review is still needed before using this as substantive evidence."


def draft_design_and_findings(paper_type: str, abstract: str) -> tuple[list[str], list[str]]:
    has_abstract = bool(abstract)
    if paper_type == "experiment":
        design = ["Review the full text for subject pool, task/game protocol, treatment variation, and payment incentives."]
        findings = ["Review the full text for the main behavioral effects and treatment comparisons."]
    elif paper_type == "theory":
        design = ["Review the full text for state variables, information structure, equilibrium logic, and comparative statics."]
        findings = ["Review the full text for testable predictions and parameter restrictions."]
    elif paper_type == "empirical":
        design = ["Review the full text for data source, sample construction, identification strategy, and outcome variables."]
        findings = ["Review the full text for main estimates, robustness checks, and limitations."]
    elif paper_type == "measurement":
        design = ["Review the full text for construct definition, elicitation task or survey items, and validation design."]
        findings = ["Review the full text for reliability, validity, and links to behavioral outcomes."]
    elif paper_type == "ai_ml":
        design = ["Review the full text for algorithm, training data, baselines, and evaluation metrics."]
        findings = ["Review the full text for performance results and failure modes."]
    else:
        design = ["Review the full text for design, data, model, or method."]
        findings = ["Review the full text for the main claims and evidence."]
    if has_abstract:
        findings.insert(0, "Abstract metadata was found; verify the details against the full text before citing.")
    return design, findings


def enrich_paper(paper: dict[str, Any], config: dict[str, Any], mailto: str = "", overwrite: bool = False) -> bool:
    changed = False
    item = crossref_work(paper.get("doi", ""), mailto=mailto) if paper.get("doi") else {}
    if item:
        changed = update_metadata_from_crossref(paper, item, overwrite=overwrite) or changed
    abstract = strip_markup(item.get("abstract", "")) if item else ""

    paper_type = infer_paper_type(paper, abstract)
    if overwrite or not paper.get("type") or paper.get("type") == "other":
        paper["type"] = paper_type
        changed = True

    if abstract and (overwrite or not paper.get("abstract")):
        paper["abstract"] = abstract
        changed = True

    if overwrite or not paper.get("summary"):
        paper["summary"] = draft_summary(paper, abstract)
        changed = True

    design, findings = draft_design_and_findings(paper_type, abstract)
    if overwrite or not paper.get("design"):
        paper["design"] = design
        changed = True
    if overwrite or not paper.get("findings"):
        paper["findings"] = findings
        changed = True

    keywords = extract_keywords(paper, abstract, config)
    if keywords and (overwrite or not paper.get("keywords")):
        paper["keywords"] = keywords
        changed = True

    enrichment_source = "Crossref metadata and abstract" if abstract else "Crossref metadata" if item else "metadata-only enrichment"
    source_bits = [bit for bit in [paper.get("source", ""), enrichment_source] if bit]
    if source_bits:
        paper["source"] = "; ".join(dict.fromkeys(source_bits))
        changed = True

    paper["needs_review"] = True
    return changed


def enrich_review_data(
    data: dict[str, Any],
    config: dict[str, Any],
    mailto: str = "",
    only_needs_review: bool = True,
    limit: int = 0,
    overwrite: bool = False,
) -> tuple[dict[str, Any], int]:
    count = 0
    for paper in data.get("papers", []):
        if only_needs_review and paper.get("needs_review") is False:
            continue
        if limit and count >= limit:
            break
        if enrich_paper(paper, config, mailto=mailto, overwrite=overwrite):
            count += 1
    return data, count
