# Literature Review Agent

Literature Review Agent is a small research workflow tool for turning a project topic and bibliography into a compact, interactive literature review page.

The current `v0.1` focuses on a stable local workflow:

- draft a project-specific `project_config.yaml`
- discover candidate papers from Crossref for human screening
- enrich accepted records with DOI metadata and conservative draft summaries
- ingest BibTeX into structured `literature-review-data.json`
- render a static `literature-review.html`
- support local search, category filters, stars, notes, and note import/export in the browser

It is designed for research projects where the review criteria matter. The project config tells the agent what to include, what to exclude, and how to summarize different paper types.

## Quick Start

Install from the repo:

```bash
git clone https://github.com/YOURNAME/literature-review-agent.git
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

Discover candidate papers from Crossref:

```bash
lit-agent discover \
  --config project_config.yaml \
  --max-results 50 \
  --limit 30
```

This writes:

```text
candidate-papers.json
candidate-papers.csv
```

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

Enrich accepted records with Crossref metadata and conservative draft notes:

```bash
lit-agent enrich \
  --config project_config.yaml \
  --data literature-review-data.json \
  --limit 20
```

The enrichment step fills missing title, year, authors, venue, DOI URL, abstract, keywords, and draft `summary` / `design` / `findings` fields when possible. It keeps `needs_review: true`, because metadata and abstracts are not a substitute for reading the paper.

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
│   ├── review.py
│   └── templates/literature_review.html
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
  "needs_review": false
}
```

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

## Roadmap

Planned next steps:

- OpenAlex enrichment
- PDF text extraction and summary support
- changelog generation for added/removed/updated papers
- project memory for repeated review updates

## Copyright Note

Do not commit copyrighted PDFs to a public repository. Share metadata, DOI links, and summaries instead.
