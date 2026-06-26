from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from . import openalex
from . import pdftext
from .discover import CROSSREF_API, crossref_authors, crossref_year, first_text, normalize_text, project_terms


DEFAULT_ENRICH_SOURCES = ("crossref", "openalex")

# Term cues used to pull design/findings sentences out of full text.
DESIGN_CUES = [
    "experiment", "treatment", "subjects", "participants", "sample", "design",
    "protocol", "we run", "we conduct", "data", "regression", "identification",
    "model", "equilibrium", "estimate", "survey", "elicit",
]
FINDINGS_CUES = [
    "we find", "we show", "results", "findings", "significant", "effect",
    "increase", "decrease", "higher", "lower", "evidence", "conclude", "suggests",
]


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


def update_metadata_from_openalex(paper: dict[str, Any], work: dict[str, Any], overwrite: bool = False) -> bool:
    changed = False
    doi = openalex.openalex_doi(work)
    fields = {
        "title": openalex.openalex_title(work),
        "year": openalex.openalex_year(work),
        "authors": openalex.openalex_authors(work),
        "doi": doi,
        "url": f"https://doi.org/{doi}" if doi else "",
        "venue": openalex.openalex_venue(work),
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


def drafts_from_full_text(
    paper: dict[str, Any], full_text: str, config: dict[str, Any]
) -> tuple[str, list[str], list[str]]:
    """Build grounded summary/design/findings from extracted PDF full text.

    Following PaperQA2-style discipline, every drafted line is an excerpt taken
    verbatim-ish from the paper's own text (abstract/method/results sections when
    detectable), tagged so a human knows it still needs verification. Returns
    ("", [], []) when no usable text is found."""
    clean = normalize_text(full_text)
    if not clean:
        return "", [], []
    sections = pdftext.split_into_sections(clean)
    title = normalize_text(paper.get("title", "")).lower()
    terms = project_terms(config, title)

    summary_src = sections.get("abstract") or clean
    summary = " ".join(pdftext.split_sentences(summary_src)[:3])[:700]

    method_src = sections.get("method") or clean
    design_excerpt = pdftext.pick_relevant_excerpt(method_src, DESIGN_CUES + terms)
    results_src = sections.get("results") or sections.get("conclusion") or clean
    findings_excerpt = pdftext.pick_relevant_excerpt(results_src, FINDINGS_CUES + terms)

    note = "[from full text — verify against the paper]"
    design = [f"{design_excerpt} {note}"] if design_excerpt else []
    findings = [f"{findings_excerpt} {note}"] if findings_excerpt else []
    return summary, design, findings


def enrich_paper(
    paper: dict[str, Any],
    config: dict[str, Any],
    mailto: str = "",
    overwrite: bool = False,
    sources: tuple[str, ...] = DEFAULT_ENRICH_SOURCES,
    cache_dir: str = "",
) -> bool:
    changed = False
    used_sources: list[str] = []

    item = crossref_work(paper.get("doi", ""), mailto=mailto) if ("crossref" in sources and paper.get("doi")) else {}
    if item:
        changed = update_metadata_from_crossref(paper, item, overwrite=overwrite) or changed
        used_sources.append("Crossref")
    abstract = strip_markup(item.get("abstract", "")) if item else ""

    # OpenAlex covers abstracts (via abstract_inverted_index) far more broadly
    # than Crossref, and adds an open-access PDF link and citation count.
    oa_work = openalex.fetch_work_by_doi(paper.get("doi", ""), mailto=mailto) if ("openalex" in sources and paper.get("doi")) else {}
    oa_concepts: list[str] = []
    if oa_work:
        used_sources.append("OpenAlex")
        changed = update_metadata_from_openalex(paper, oa_work, overwrite=overwrite) or changed
        oa_abstract = openalex.reconstruct_abstract(oa_work.get("abstract_inverted_index"))
        if oa_abstract and (overwrite or not abstract):
            abstract = oa_abstract
        pdf_url = openalex.openalex_oa_pdf_url(oa_work)
        if pdf_url and (overwrite or not paper.get("pdf_url")):
            paper["pdf_url"] = pdf_url
            changed = True
        cited = openalex.openalex_cited_by_count(oa_work)
        if cited and (overwrite or not paper.get("cited_by_count")):
            paper["cited_by_count"] = cited
            changed = True
        oa_concepts = openalex.openalex_concepts(oa_work)

    # Optional full-text pass: download/extract the PDF and draft grounded
    # summary/design/findings from the paper's own text. Opt-in because it
    # downloads files and needs the optional pypdf dependency.
    full_text = ""
    if "pdf" in sources:
        pdf_source = paper.get("pdf_url") or paper.get("pdf_path") or ""
        full_text = pdftext.fetch_pdf_text(pdf_source, mailto=mailto, cache_dir=cache_dir or None)
        if full_text:
            used_sources.append("Full text (PDF)")

    paper_type = infer_paper_type(paper, abstract or full_text[:4000])
    if overwrite or not paper.get("type") or paper.get("type") == "other":
        paper["type"] = paper_type
        changed = True

    if abstract and (overwrite or not paper.get("abstract")):
        paper["abstract"] = abstract
        changed = True

    ft_summary, ft_design, ft_findings = drafts_from_full_text(paper, full_text, config) if full_text else ("", [], [])

    if overwrite or not paper.get("summary"):
        paper["summary"] = ft_summary or draft_summary(paper, abstract)
        changed = True

    design, findings = draft_design_and_findings(paper_type, abstract)
    design = ft_design or design
    findings = ft_findings or findings
    if overwrite or not paper.get("design"):
        paper["design"] = design
        changed = True
    if overwrite or not paper.get("findings"):
        paper["findings"] = findings
        changed = True

    keywords = extract_keywords(paper, abstract, config)
    for concept in oa_concepts:
        if concept not in keywords:
            keywords.append(concept)
    keywords = keywords[:8]
    if keywords and (overwrite or not paper.get("keywords")):
        paper["keywords"] = keywords
        changed = True

    if used_sources:
        detail = "metadata and abstract" if abstract else "metadata"
        enrichment_source = f"{' + '.join(used_sources)} {detail}"
    else:
        enrichment_source = "metadata-only enrichment"
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
    sources: tuple[str, ...] = DEFAULT_ENRICH_SOURCES,
    cache_dir: str = "",
) -> tuple[dict[str, Any], int]:
    count = 0
    for paper in data.get("papers", []):
        if only_needs_review and paper.get("needs_review") is False:
            continue
        if limit and count >= limit:
            break
        if enrich_paper(paper, config, mailto=mailto, overwrite=overwrite, sources=sources, cache_dir=cache_dir):
            count += 1
    return data, count
