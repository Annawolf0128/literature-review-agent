from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path
from typing import Optional

from .bibtex import parse_bibtex, record_from_bib
from .config import default_config, load_config, write_config
from .discover import (
    candidates_from_citations,
    candidates_from_crossref,
    candidates_from_openalex,
    crossref_search,
    load_accepted_candidates,
    merge_candidate_lists,
    review_data_keys,
    write_candidates_csv,
    write_candidates_json,
)
from .enrich import DEFAULT_ENRICH_SOURCES, enrich_review_data
from .openalex import search_works
from .review import build_html, load_json, merge_records, save_json


PACKAGE_ROOT = Path(__file__).resolve().parent
DEFAULT_TEMPLATE = PACKAGE_ROOT / "templates" / "literature_review.html"

VALID_SOURCES = {"crossref", "openalex"}


def config_output(config: dict, key: str, fallback: str) -> str:
    outputs = config.get("outputs") if isinstance(config.get("outputs"), dict) else {}
    return str(outputs.get(key) or fallback)


def resolve_sources(cli_value: str, config: dict, section_key: str, default: tuple[str, ...]) -> tuple[str, ...]:
    """Resolve which backends to use: explicit CLI --source wins, else the
    config section's `sources` list, else the built-in default."""
    if cli_value:
        chosen = [piece.strip().lower() for piece in cli_value.split(",")]
    else:
        section = config.get(section_key) if isinstance(config.get(section_key), dict) else {}
        chosen = [str(piece).strip().lower() for piece in (section.get("sources") or [])]
    chosen = [piece for piece in chosen if piece in VALID_SOURCES]
    return tuple(dict.fromkeys(chosen)) or default


def cmd_init_config(args: argparse.Namespace) -> None:
    config = default_config(args.topic, discipline=args.discipline, title=args.title or None)
    output = write_config(config, args.output)
    print(f"Wrote draft project config: {output}")


def cmd_build(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    title = args.title or config.get("project", {}).get("title") or "Literature Review"
    data_path = Path(args.data or config_output(config, "data", "literature-review-data.json"))
    html_path = Path(args.output or config_output(config, "html", "literature-review.html"))
    template_path = Path(args.template or DEFAULT_TEMPLATE)

    base = load_json(data_path)
    base["title"] = title

    if args.bib:
        category = args.category or "Unsorted / To Review"
        entries = parse_bibtex(Path(args.bib).read_text(encoding="utf-8"))
        incoming = {
            "title": title,
            "updated": str(dt.date.today()),
            "categories": [category],
            "papers": [record_from_bib(entry, category) for entry in entries],
        }
        base = incoming if args.replace else merge_records(base, incoming)
        save_json(base, data_path)
    elif not data_path.exists():
        save_json(base, data_path)

    build_html(data_path, html_path, template_path, title=title)
    print(f"Wrote review data: {data_path}")
    print(f"Wrote review HTML: {html_path}")


def cmd_merge(args: argparse.Namespace) -> None:
    base = load_json(args.base)
    incoming = load_json(args.incoming)
    output = save_json(merge_records(base, incoming), args.output)
    print(f"Wrote merged review data: {output}")


def cmd_discover(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    project = config.get("project", {}) if isinstance(config.get("project"), dict) else {}
    query = args.query or project.get("topic") or project.get("title")
    sources = resolve_sources(args.source, config, "discovery", ("crossref",))
    cite_chase = args.cite_chase

    json_path = Path(args.output or config_output(config, "candidates_json", "candidate-papers.json"))
    csv_path = Path(args.csv or config_output(config, "candidates_csv", "candidate-papers.csv"))

    # Keyword search across the selected backends.
    keyword_lists: list[list[dict]] = []
    if query:
        if "crossref" in sources:
            items = crossref_search(query, rows=args.max_results, mailto=args.mailto)
            keyword_lists.append(candidates_from_crossref(items, config, query))
        if "openalex" in sources:
            works = search_works(query, rows=args.max_results, mailto=args.mailto)
            keyword_lists.append(candidates_from_openalex(works, config, query))
    elif cite_chase == "none":
        raise SystemExit("No query provided. Use --query, set project.topic, or run --cite-chase with --from-data.")

    # Optional citation chasing seeded from an existing review, plus de-duplication
    # against papers already in that review.
    citation_list: list[dict] = []
    exclude_keys: set[str] = set()
    if cite_chase != "none":
        if not args.from_data:
            raise SystemExit("--cite-chase requires --from-data pointing to an existing review JSON.")
        data = load_json(args.from_data)
        exclude_keys = review_data_keys(data)
        citation_list = candidates_from_citations(
            data, config, mailto=args.mailto, direction=cite_chase,
            max_per_paper=args.max_per_paper, query=query or "",
        )
    elif args.from_data:
        exclude_keys = review_data_keys(load_json(args.from_data))

    candidates = merge_candidate_lists(*keyword_lists, citation_list, exclude_keys=exclude_keys)
    if args.min_score:
        candidates = [candidate for candidate in candidates if candidate.get("relevance_score", 0) >= args.min_score]
    if args.limit:
        candidates = candidates[:args.limit]
    write_candidates_json(candidates, json_path, query or "(citation chasing)")
    write_candidates_csv(candidates, csv_path)
    print(f"Sources: {', '.join(sources)}" + (f" + citation chasing ({cite_chase})" if cite_chase != "none" else ""))
    print(f"Wrote candidate JSON: {json_path}")
    print(f"Wrote candidate CSV: {csv_path}")
    print(f"Candidates: {len(candidates)}")


def cmd_accept(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    title = args.title or config.get("project", {}).get("title") or "Literature Review"
    data_path = Path(args.data or config_output(config, "data", "literature-review-data.json"))
    category = args.category or "Unsorted / To Review"
    records = load_accepted_candidates(args.candidates, category)
    base = load_json(data_path)
    base["title"] = title
    incoming = {
        "title": title,
        "updated": str(dt.date.today()),
        "categories": [category],
        "papers": records,
    }
    save_json(merge_records(base, incoming), data_path)
    print(f"Accepted candidates: {len(records)}")
    print(f"Wrote review data: {data_path}")


def cmd_enrich(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    data_path = Path(args.data or config_output(config, "data", "literature-review-data.json"))
    output_path = Path(args.output or data_path)
    sources = resolve_sources(args.source, config, "enrichment", DEFAULT_ENRICH_SOURCES)
    data = load_json(data_path)
    data, changed = enrich_review_data(
        data,
        config,
        mailto=args.mailto,
        only_needs_review=not args.all,
        limit=args.limit,
        overwrite=args.overwrite,
        sources=sources,
    )
    save_json(data, output_path)
    print(f"Sources: {', '.join(sources)}")
    print(f"Enriched records: {changed}")
    print(f"Wrote review data: {output_path}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lit-agent",
        description="Generate project-specific literature review configs and interactive HTML review pages.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init-config", help="Generate a draft project_config.yaml from a topic.")
    p.add_argument("--topic", required=True, help="Project topic or short research description.")
    p.add_argument("--discipline", default="economics", help="Primary discipline used for screening defaults.")
    p.add_argument("--title", default="", help="Optional display title.")
    p.add_argument("--output", default="project_config.yaml", help="Path for the generated YAML config.")
    p.set_defaults(func=cmd_init_config)

    p = sub.add_parser("build", help="Build literature-review-data.json and literature-review.html.")
    p.add_argument("--config", default="project_config.yaml", help="Project config YAML.")
    p.add_argument("--bib", default="", help="Optional BibTeX file to ingest before rendering.")
    p.add_argument("--data", default="", help="Review data JSON path. Defaults to config outputs.data.")
    p.add_argument("--output", default="", help="HTML output path. Defaults to config outputs.html.")
    p.add_argument("--template", default="", help="HTML template path.")
    p.add_argument("--title", default="", help="Override review title.")
    p.add_argument("--category", default="", help="Category for newly ingested BibTeX records.")
    p.add_argument("--replace", action="store_true", help="Replace existing data when ingesting BibTeX.")
    p.set_defaults(func=cmd_build)

    p = sub.add_parser("merge", help="Merge one literature-review-data JSON into another.")
    p.add_argument("--base", required=True)
    p.add_argument("--incoming", required=True)
    p.add_argument("--output", required=True)
    p.set_defaults(func=cmd_merge)

    p = sub.add_parser("discover", help="Search Crossref/OpenAlex for candidate papers and write reviewable candidate files.")
    p.add_argument("--config", default="project_config.yaml", help="Project config YAML.")
    p.add_argument("--query", default="", help="Search query. Defaults to project.topic in the config.")
    p.add_argument("--source", default="", help="Comma-separated backends: crossref, openalex. Defaults to config discovery.sources.")
    p.add_argument("--from-data", default="", help="Existing review JSON. Used to seed citation chasing and to exclude already-included papers.")
    p.add_argument(
        "--cite-chase",
        default="none",
        choices=["none", "references", "citations", "both"],
        help="Citation chasing via OpenAlex, seeded from --from-data: follow references, citations, or both.",
    )
    p.add_argument("--max-per-paper", type=int, default=25, help="Max referenced/citing papers to pull per seed paper during citation chasing.")
    p.add_argument("--max-results", type=int, default=40, help="Number of keyword-search results to request per backend.")
    p.add_argument("--limit", type=int, default=30, help="Maximum candidates to write after scoring.")
    p.add_argument("--min-score", type=int, default=0, help="Drop candidates below this relevance score.")
    p.add_argument("--output", default="", help="Candidate JSON output path.")
    p.add_argument("--csv", default="", help="Candidate CSV output path.")
    p.add_argument("--mailto", default="", help="Optional email for polite Crossref/OpenAlex API usage.")
    p.set_defaults(func=cmd_discover)

    p = sub.add_parser("accept", help="Add candidates marked accepted=true to literature-review-data.json.")
    p.add_argument("--config", default="project_config.yaml", help="Project config YAML.")
    p.add_argument("--candidates", default="candidate-papers.json", help="Candidate JSON path.")
    p.add_argument("--data", default="", help="Review data JSON path. Defaults to config outputs.data.")
    p.add_argument("--category", default="", help="Category for accepted candidate records.")
    p.add_argument("--title", default="", help="Override review title.")
    p.set_defaults(func=cmd_accept)

    p = sub.add_parser("enrich", help="Fill metadata and conservative draft summaries for review records.")
    p.add_argument("--config", default="project_config.yaml", help="Project config YAML.")
    p.add_argument("--data", default="", help="Review data JSON path. Defaults to config outputs.data.")
    p.add_argument("--output", default="", help="Output JSON path. Defaults to overwriting --data.")
    p.add_argument("--limit", type=int, default=0, help="Maximum records to enrich.")
    p.add_argument("--all", action="store_true", help="Also enrich records where needs_review is false.")
    p.add_argument("--overwrite", action="store_true", help="Overwrite existing summary/design/findings/metadata fields.")
    p.add_argument("--source", default="", help="Comma-separated backends: crossref, openalex. Defaults to config enrichment.sources.")
    p.add_argument("--mailto", default="", help="Optional email for polite Crossref/OpenAlex API usage.")
    p.set_defaults(func=cmd_enrich)

    return parser


def main(argv: Optional[list[str]] = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
