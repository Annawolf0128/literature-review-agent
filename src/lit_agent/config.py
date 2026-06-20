from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional

import yaml


def title_from_topic(topic: str) -> str:
    clean = re.sub(r"\s+", " ", topic).strip()
    if not clean:
        return "Literature Review"
    return clean[:1].upper() + clean[1:]


def default_config(topic: str, discipline: str = "economics", title: Optional[str] = None) -> dict[str, Any]:
    title = title or title_from_topic(topic)
    config: dict[str, Any] = {
        "project": {
            "title": title,
            "discipline": discipline,
            "topic": topic,
            "main_question": "Replace this with the project's core research question.",
        },
        "literature_scope": {
            "include": [
                "papers directly related to the project question",
                "foundational theory or measurement papers",
                "empirical or experimental papers that inform research design",
                "highly cited or field-defining contributions",
            ],
            "exclude": [
                "weakly related papers that only share keywords",
                "purely descriptive or non-scholarly sources",
                "papers outside the target discipline unless central",
            ],
        },
        "quality_filter": {
            "prefer": [
                "top general-interest journals in the field",
                "leading field journals",
                "major interdisciplinary journals when central",
                "highly cited working papers or books when foundational",
                "papers unusually close to the project design or mechanism",
            ],
            "needs_human_review": [
                "papers classified using metadata only",
                "borderline papers outside the main discipline",
                "papers whose design or findings are unavailable",
            ],
        },
        "categories": [
            "Foundations",
            "Theory and Mechanisms",
            "Experimental Evidence",
            "Empirical Evidence",
            "Methods and Measurement",
        ],
        "summary_focus": {
            "experiment": [
                "sample or subject pool",
                "task/game/protocol",
                "treatment variation",
                "payment rule and incentives",
                "main behavioral results",
            ],
            "theory": [
                "state variables",
                "information structure",
                "equilibrium or Bellman logic",
                "mechanism",
                "comparative statics or testable predictions",
            ],
            "empirical": [
                "data source and sample",
                "identification strategy",
                "outcome variables",
                "main estimates",
                "robustness and limitations",
            ],
            "ai_ml": [
                "model or algorithm",
                "data and training setup",
                "baselines",
                "evaluation metrics",
                "main results",
            ],
            "review": [
                "scope",
                "inclusion criteria",
                "synthesis method",
                "headline patterns",
                "limitations",
            ],
            "measurement": [
                "construct definition",
                "items/tasks/measures",
                "validation design",
                "reliability and validity",
                "predictive or convergent validity",
            ],
        },
        "outputs": {
            "data": "literature-review-data.json",
            "html": "literature-review.html",
            "candidates_json": "candidate-papers.json",
            "candidates_csv": "candidate-papers.csv",
            "changelog": "changelog.md",
        },
    }
    if discipline.lower() in {"economics", "econ"}:
        config["literature_scope"]["include"] = [
            "economics papers directly related to the project question",
            "formal theory papers that clarify the mechanism",
            "lab, field, or online experiments that inform the design",
            "empirical papers with credible identification",
            "foundational papers repeatedly cited by top-journal work",
        ]
        config["literature_scope"]["exclude"] = [
            "generic psychology papers unless central to measurement or mechanism",
            "broad management or online-platform papers unless directly connected",
            "papers that only share keywords but not the economic mechanism",
            "non-scholarly sources",
        ]
        config["quality_filter"]["prefer"] = [
            "AER, Econometrica, QJE, JPE, Review of Economic Studies",
            "Review of Economics and Statistics, JEL, JEP",
            "leading field journals such as GEB, Experimental Economics, JEBO, JET, JPubE, JDE, JF, JFE, RFS, Management Science",
            "major interdisciplinary journals such as Nature, Science, PNAS, Nature Human Behaviour when central",
            "highly cited or unusually close working papers",
        ]
    return config


def write_config(config: dict[str, Any], output: str | Path) -> Path:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(config, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return path


def load_config(path: str | Path) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Config must be a mapping: {path}")
    return data
