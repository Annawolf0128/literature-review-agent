# Literature Review Agent

Literature Review Agent is a small research workflow tool for turning a project topic and bibliography into a compact, interactive literature review page.

The current `v0.1` focuses on a stable local workflow:

- draft a project-specific `project_config.yaml`
- discover candidate papers from Crossref and/or OpenAlex for human screening
- chase citations (references and citing papers) from an existing review via OpenAlex
- enrich accepted records with Crossref/OpenAlex metadata, abstracts, open-access PDF links, and conservative draft summaries
- optionally extract open-access PDF full text and draft grounded design/findings notes from the paper's own sections
- ingest BibTeX into structured `literature-review-data.json`
- render a static `literature-review.html`
- support local search, category filters, stars, notes, and note import/export in the browser

It is designed for research projects where the review criteria matter. The project config tells the agent what to include, what to exclude, and how to summarize different paper types.

## Quick Start

Install from the repo:

```bash
git clone https://github.com/Annawolf0128/literature-review-agent.git
cd literature-review-agent
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
pip install -e .
```

Create a draft config from a topic:

```bash
lit-agent init-config \
  --topic "trust as reinvestable social capital" \
  --discipline economics
```

This writes:

```text
project_config.yaml
```

Edit the config to refine the inclusion and exclusion rules. Then build a review from BibTeX:

```bash
lit-agent build \
  --config project_config.yaml \
  --bib references.bib \
  --category "Unsorted / To Review"
```

This writes:

```text
literature-review-data.json
literature-review.html
```

Open `literature-review.html` in a browser.

## Inputs and Outputs

Typical inputs:

- `project_config.yaml`: project topic, screening rules, quality filters, and summary focus
- `references.bib`: bibliography metadata
- `literature-review-data.json`: optional existing review data to update

Typical outputs:

- `candidate-papers.json` / `candidate-papers.csv`: search candidates for human screening
- `literature-review-data.json`: structured paper records
- `literature-review.html`: interactive static review page
- `literature-review-notes.json`: optional export of personal stars and notes from the page

The HTML stores stars and notes in browser `localStorage` by default. If you want to share notes with collaborators, use the page's `Export notes` button and send the exported JSON.

## Commands

Generate a project config:

```bash
lit-agent init-config --topic "AI adoption and labor market inequality"
```

Discover candidate papers from Crossref and/or OpenAlex:

```bash
lit-agent discover \
  --config project_config.yaml \
  --source crossref,openalex \
  --max-results 50 \
  --limit 30
```

This writes:

```text
candidate-papers.json
candidate-papers.csv
```

`--source` overrides the backends in the config's `discovery.sources` list. Results from multiple backends are merged and de-duplicated by DOI (or normalized title), keeping the higher relevance score and unioned provenance.

### Citation chasing

Seeded from an existing review, OpenAlex can surface new candidates by following the papers your reviewed papers cite (`references`), the papers that cite them (`citations`), or `both`:

```bash
lit-agent discover \
  --config project_config.yaml \
  --from-data literature-review-data.json \
  --cite-chase both \
  --max-per-paper 25 \
  --limit 40
```

Papers already in `--from-data` are excluded automatically. `--from-data` without `--cite-chase` still excludes already-included papers from a keyword search.

Candidates are not automatically added to the review. Open the CSV/JSON, mark or copy the papers you want, then add accepted papers through BibTeX or a future candidate-approval command.

To add candidates, edit `candidate-papers.json` and set selected records to:

```json
"accepted": true
```

Then run:

```bash
lit-agent accept \
  --config project_config.yaml \
  --candidates candidate-papers.json \
  --category "Unsorted / To Review"
```

The accepted records are added as metadata stubs with `needs_review: true`.

Enrich accepted records with Crossref/OpenAlex metadata and conservative draft notes:

```bash
lit-agent enrich \
  --config project_config.yaml \
  --data literature-review-data.json \
  --source crossref,openalex \
  --limit 20
```

The enrichment step fills missing title, year, authors, venue, DOI URL, abstract, keywords, and draft `summary` / `design` / `findings` fields when possible. OpenAlex broadens abstract coverage (via `abstract_inverted_index`), and adds an open-access `pdf_url` and a `cited_by_count` that Crossref often lacks; OpenAlex concepts above a score threshold are folded into keywords. `--source` overrides the config's `enrichment.sources` (default `crossref, openalex`). Enrichment keeps `needs_review: true`, because metadata and abstracts are not a substitute for reading the paper.

### Full-text enrichment from PDFs

Add `pdf` to the sources to download each record's open-access PDF and draft grounded `summary` / `design` / `findings` from the paper's own sections (abstract, methods, results). This needs the optional `pypdf` extra:

```bash
pip install -e .[pdf]

lit-agent enrich \
  --config project_config.yaml \
  --data literature-review-data.json \
  --source crossref,openalex,pdf \
  --pdf-dir .pdf-cache \
  --limit 10
```

Each drafted line is an excerpt taken from the paper's own text and tagged `[from full text — verify against the paper]`, so nothing is invented — a human still confirms it. PDFs are cached under `--pdf-dir` to avoid re-downloading. When a PDF can't be fetched or read, enrichment falls back to the abstract-based draft. Records still keep `needs_review: true`.

Build from BibTeX:

```bash
lit-agent build --config project_config.yaml --bib references.bib
```

Build from an existing review JSON:

```bash
lit-agent build --config project_config.yaml --data literature-review-data.json
```

Merge two review JSON files:

```bash
lit-agent merge \
  --base literature-review-data.json \
  --incoming new-papers.json \
  --output literature-review-data.json
```

## Repository Structure

```text
literature-review-agent/
├── pyproject.toml
├── setup.cfg
├── setup.py
├── src/lit_agent/
│   ├── cli.py
│   ├── config.py
│   ├── bibtex.py
│   ├── discover.py
│   ├── enrich.py
│   ├── openalex.py
│   ├── pdftext.py
│   ├── review.py
│   └── templates/literature_review.html
├── tests/
│   ├── test_openalex.py
│   ├── test_discover.py
│   ├── test_enrich.py
│   └── test_pdftext.py
├── examples/trust-game/
│   ├── project_config.yaml
│   ├── references.bib
│   ├── literature-review-data.json
│   └── literature-review.html
└── README.md
```

## Paper Schema

Each paper record uses this shape:

```json
{
  "id": "berg1995trust",
  "type": "experiment",
  "category": "Foundations",
  "citation": "Berg, Joyce, Dickhaut, John, McCabe, Kevin (1995). Trust, Reciprocity, and Social History. Games and Economic Behavior, 10(1), 122--142.",
  "year": "1995",
  "title": "Trust, Reciprocity, and Social History",
  "authors": ["Berg, Joyce", "Dickhaut, John", "McCabe, Kevin"],
  "doi": "10.1006/game.1995.1027",
  "url": "https://doi.org/10.1006/game.1995.1027",
  "summary": "Canonical investment-game experiment showing substantial trust and reciprocity.",
  "design": ["A chooses how much of an endowment to send to B."],
  "findings": ["Many first movers send positive amounts."],
  "keywords": ["trust game", "reciprocity"],
  "pdf_url": "https://example.org/berg1995.pdf",
  "cited_by_count": 7421,
  "needs_review": false
}
```

`pdf_url` (open-access link) and `cited_by_count` are populated by OpenAlex enrichment when available.

`v0.1` creates metadata stubs from BibTeX and marks them `needs_review: true`. The `enrich` command can fill a conservative first pass from DOI metadata and abstracts, but a human or a writing agent should still verify `summary`, `design`, and `findings` from the paper text.

## Project Config

The config is the project's screening rulebook. For example:

```yaml
project:
  title: Trust as Reinvestable Social Capital
  discipline: economics
  topic: repeated trust game, reputation, noisy returns, reinvestment

literature_scope:
  include:
    - economics papers directly related to the project question
    - lab, field, or online experiments that inform the design
  exclude:
    - generic psychology papers unless central to measurement or mechanism
    - broad online-platform papers unless directly connected

summary_focus:
  experiment:
    - task/game/protocol
    - treatment variation
    - payment rule and incentives
    - main behavioral results
  theory:
    - state variables
    - information structure
    - equilibrium or Bellman logic
```

## Tests

The test suite uses only the standard library (`unittest`) and runs fully offline — the OpenAlex network layer is isolated behind a single function that tests monkeypatch, so no API calls are made.

```bash
python3 -m unittest discover -s tests
```

## Roadmap

Done:

- OpenAlex enrichment (abstracts, OA PDF links, citation counts, concepts)
- OpenAlex/Crossref multi-source discovery with merge + de-duplication
- citation chasing (references and citing papers) seeded from an existing review
- PDF full-text extraction with grounded design/findings drafting

Planned next steps:

- changelog generation for added/removed/updated papers
- project memory for repeated review updates

## Copyright Note

Do not commit copyrighted PDFs to a public repository. Share metadata, DOI links, and summaries instead.
