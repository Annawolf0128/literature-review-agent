from __future__ import annotations

import datetime as dt
import html
import json
import re
from pathlib import Path
from typing import Any, Optional


REQUIRED_PAPER_FIELDS = [
    "id",
    "type",
    "category",
    "citation",
    "year",
    "title",
    "authors",
    "doi",
    "url",
    "summary",
    "design",
    "findings",
    "keywords",
    "needs_review",
]


def load_json(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    if not path.exists():
        return {"title": "Literature Review", "updated": str(dt.date.today()), "categories": [], "papers": []}
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(data: dict[str, Any], path: str | Path) -> Path:
    data["updated"] = str(dt.date.today())
    data["categories"] = list(dict.fromkeys(p.get("category", "Unsorted / To Review") for p in data.get("papers", [])))
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def paper_key(paper: dict[str, Any]) -> str:
    doi = str(paper.get("doi", "")).lower().strip()
    if doi:
        return "doi:" + doi
    return "title:" + re.sub(r"\W+", "", str(paper.get("title", "")).lower())


def normalize_record(paper: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(paper)
    for field in REQUIRED_PAPER_FIELDS:
        if field not in normalized:
            normalized[field] = [] if field in {"authors", "design", "findings", "keywords"} else ""
    if "project_note" not in normalized:
        normalized["project_note"] = ""
    if "source" not in normalized:
        normalized["source"] = ""
    if not isinstance(normalized.get("authors"), list):
        normalized["authors"] = [str(normalized["authors"])]
    for field in ["design", "findings", "keywords"]:
        if not isinstance(normalized.get(field), list):
            normalized[field] = [str(normalized[field])]
    if not isinstance(normalized.get("needs_review"), bool):
        normalized["needs_review"] = bool(normalized.get("needs_review"))
    return normalized


def merge_records(base: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    base.setdefault("papers", [])
    seen = {paper_key(paper): index for index, paper in enumerate(base.get("papers", []))}
    for paper in incoming.get("papers", []):
        paper = normalize_record(paper)
        key = paper_key(paper)
        if key in seen:
            current = base["papers"][seen[key]]
            for field, value in paper.items():
                if value and not current.get(field):
                    current[field] = value
        else:
            base["papers"].append(paper)
    return base


def build_html(data_path: str | Path, output_path: str | Path, template_path: str | Path, title: Optional[str] = None) -> Path:
    data = load_json(data_path)
    if title:
        data["title"] = title
    if not data.get("title"):
        data["title"] = "Literature Review"
    data["updated"] = data.get("updated") or str(dt.date.today())
    template = Path(template_path).read_text(encoding="utf-8")
    rendered = template.replace("__TITLE__", html.escape(data["title"]))
    rendered = rendered.replace("__UPDATED__", html.escape(str(data["updated"])))
    embedded_json = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    rendered = rendered.replace("__DATA__", embedded_json)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(rendered, encoding="utf-8")
    return output_path
