import pathlib
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from lit_agent import enrich as en
from lit_agent import openalex as oa
from lit_agent import pdftext as pt


CONFIG = {
    "project": {"discipline": "economics", "topic": "trust and reciprocity"},
    "literature_scope": {"include": ["trust reciprocity experiments"]},
}

OA_WORK = {
    "id": "https://openalex.org/W2741809807",
    "doi": "https://doi.org/10.1006/game.1995.1027",
    "title": "Trust, Reciprocity, and Social History",
    "publication_year": 1995,
    "authorships": [{"author": {"display_name": "Joyce Berg"}}],
    "primary_location": {"source": {"display_name": "Games and Economic Behavior"}},
    "abstract_inverted_index": {"We": [0], "study": [1], "trust.": [2]},
    "cited_by_count": 7421,
    "referenced_works": [],
    "concepts": [{"display_name": "Reciprocity", "score": 0.7}],
    "type": "article",
    "best_oa_location": {"pdf_url": "https://x.org/berg1995.pdf"},
}


class EnrichOpenAlexOnly(unittest.TestCase):
    def test_fills_abstract_pdf_citations_keywords(self):
        paper = {"doi": "10.1006/game.1995.1027", "title": "Trust"}
        with mock.patch.object(oa, "fetch_work_by_doi", return_value=OA_WORK):
            changed = en.enrich_paper(paper, CONFIG, sources=("openalex",))
        self.assertTrue(changed)
        self.assertEqual(paper["abstract"], "We study trust.")
        self.assertEqual(paper["pdf_url"], "https://x.org/berg1995.pdf")
        self.assertEqual(paper["cited_by_count"], 7421)
        self.assertIn("reciprocity", paper["keywords"])
        self.assertIn("OpenAlex", paper["source"])
        self.assertTrue(paper["needs_review"])
        self.assertEqual(paper["type"], "experiment")  # inferred from "trust" via title? -> reciprocity abstract

    def test_no_crossref_call_when_not_in_sources(self):
        paper = {"doi": "10.1/x", "title": "Trust"}
        with mock.patch.object(oa, "fetch_work_by_doi", return_value=OA_WORK), \
             mock.patch.object(en, "crossref_work", side_effect=AssertionError("should not be called")):
            en.enrich_paper(paper, CONFIG, sources=("openalex",))


class EnrichCrossrefOnly(unittest.TestCase):
    def test_uses_crossref_and_skips_openalex(self):
        paper = {"doi": "10.1/x", "title": ""}
        crossref_item = {
            "title": ["Trust and Reciprocity"],
            "DOI": "10.1/X",
            "container-title": ["Games and Economic Behavior"],
            "author": [{"given": "Joyce", "family": "Berg"}],
            "issued": {"date-parts": [[1995]]},
            "abstract": "<p>We study trust.</p>",
        }
        with mock.patch.object(en, "crossref_work", return_value=crossref_item), \
             mock.patch.object(oa, "fetch_work_by_doi", side_effect=AssertionError("should not be called")):
            changed = en.enrich_paper(paper, CONFIG, sources=("crossref",))
        self.assertTrue(changed)
        self.assertEqual(paper["title"], "Trust and Reciprocity")
        self.assertEqual(paper["abstract"], "We study trust.")
        self.assertIn("Crossref", paper["source"])


FULL_TEXT = (
    "Abstract. We study trust in an investment game. "
    "Methods. We recruit 32 participants who each receive a 10 dollar endowment "
    "and decide how much to send. "
    "Results. We find first movers send positive amounts and reciprocity is significant. "
    "Conclusion. Trust sustains exchange."
)


class EnrichPdfSource(unittest.TestCase):
    def test_full_text_drafts_design_and_findings(self):
        paper = {"doi": "10.1/x", "title": "Trust", "pdf_url": "https://x.org/p.pdf"}
        with mock.patch.object(oa, "fetch_work_by_doi", return_value=OA_WORK), \
             mock.patch.object(pt, "fetch_pdf_text", return_value=FULL_TEXT) as fetch:
            changed = en.enrich_paper(paper, CONFIG, sources=("openalex", "pdf"), cache_dir="/tmp/cache")
        self.assertTrue(changed)
        fetch.assert_called_once()
        self.assertIn("Full text (PDF)", paper["source"])
        # Design/findings are grounded excerpts tagged for verification.
        self.assertTrue(any("from full text" in d for d in paper["design"]))
        self.assertTrue(any("reciprocity" in f.lower() or "positive amounts" in f.lower() for f in paper["findings"]))

    def test_pdf_source_without_text_falls_back(self):
        paper = {"doi": "10.1/x", "title": "Trust", "pdf_url": "https://x.org/p.pdf"}
        with mock.patch.object(oa, "fetch_work_by_doi", return_value=OA_WORK), \
             mock.patch.object(pt, "fetch_pdf_text", return_value=""):
            en.enrich_paper(paper, CONFIG, sources=("openalex", "pdf"))
        self.assertNotIn("Full text (PDF)", paper.get("source", ""))
        self.assertTrue(paper["design"])  # still has conservative placeholder


class EnrichReviewData(unittest.TestCase):
    def test_respects_needs_review_and_limit(self):
        data = {"papers": [
            {"doi": "10.1/a", "title": "A", "needs_review": False},
            {"doi": "10.1/b", "title": "B"},
            {"doi": "10.1/c", "title": "C"},
        ]}
        with mock.patch.object(oa, "fetch_work_by_doi", return_value=OA_WORK):
            _, changed = en.enrich_review_data(data, CONFIG, only_needs_review=True, limit=1, sources=("openalex",))
        self.assertEqual(changed, 1)


if __name__ == "__main__":
    unittest.main()
