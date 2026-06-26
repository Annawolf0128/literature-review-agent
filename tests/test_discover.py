import pathlib
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from lit_agent import discover as dc
from lit_agent import openalex as oa


CONFIG = {
    "project": {"discipline": "economics", "topic": "trust and reciprocity", "title": "Trust"},
    "literature_scope": {"include": ["trust reciprocity experiments"]},
}


def make_work(wid, title, doi="", cited=0, year=1995, refs=None, venue="Games and Economic Behavior"):
    return {
        "id": f"https://openalex.org/{wid}",
        "doi": f"https://doi.org/{doi}" if doi else None,
        "title": title,
        "publication_year": year,
        "authorships": [{"author": {"display_name": "Joyce Berg"}}],
        "primary_location": {"source": {"display_name": venue}},
        "abstract_inverted_index": {"trust": [0], "matters": [1]},
        "cited_by_count": cited,
        "referenced_works": refs or [],
        "concepts": [],
        "type": "article",
        "best_oa_location": {"pdf_url": f"https://x.org/{wid}.pdf"},
    }


class CandidateKey(unittest.TestCase):
    def test_doi_wins_and_lowercases(self):
        self.assertEqual(dc.candidate_key("https://doi.org/10.1/A", "Some Title"), "https://doi.org/10.1/a")

    def test_falls_back_to_stripped_title(self):
        self.assertEqual(dc.candidate_key("", "Trust, Reciprocity!"), "trustreciprocity")

    def test_empty(self):
        self.assertEqual(dc.candidate_key("", ""), "")


class FromOpenAlex(unittest.TestCase):
    def test_scores_and_dedupes(self):
        works = [
            make_work("W1", "Trust game and reciprocity", doi="10.1/a", cited=5000),
            make_work("W1dup", "Trust game and reciprocity", doi="10.1/a", cited=5000),
            make_work("W2", "Unrelated chemistry paper", doi="10.2/b", cited=0, venue="J Chem"),
        ]
        cands = dc.candidates_from_openalex(works, CONFIG, "trust reciprocity")
        self.assertEqual(len(cands), 2)  # dup dropped
        # Highly cited trust paper ranks first.
        self.assertEqual(cands[0]["doi"], "10.1/a")
        self.assertGreater(cands[0]["relevance_score"], cands[1]["relevance_score"])
        self.assertEqual(cands[0]["source"], "OpenAlex")


class MergeLists(unittest.TestCase):
    def test_union_provenance_and_backfill(self):
        crossref = [{
            "title": "Trust, Reciprocity, and Social History", "doi": "10.1/a",
            "relevance_score": 40, "why": ["top economics journal"], "source": "Crossref",
            "is_referenced_by_count": 100, "abstract": "", "venue": "GEB", "year": "1995",
        }]
        openalex = [{
            "title": "Trust, Reciprocity, and Social History", "doi": "10.1/a",
            "relevance_score": 56, "why": ["highly cited"], "source": "OpenAlex",
            "is_referenced_by_count": 7421, "abstract": "We study trust.", "pdf_url": "p.pdf",
            "openalex_id": "W1",
        }]
        merged = dc.merge_candidate_lists(crossref, openalex)
        self.assertEqual(len(merged), 1)
        m = merged[0]
        self.assertEqual(m["relevance_score"], 56)  # max
        self.assertEqual(m["is_referenced_by_count"], 7421)  # max
        self.assertIn("Crossref", m["source"])
        self.assertIn("OpenAlex", m["source"])
        self.assertEqual(m["abstract"], "We study trust.")  # backfilled
        self.assertEqual(m["pdf_url"], "p.pdf")
        self.assertIn("top economics journal", m["why"])
        self.assertIn("highly cited", m["why"])

    def test_exclude_keys(self):
        cands = [{"title": "Trust", "doi": "10.1/a", "relevance_score": 10}]
        merged = dc.merge_candidate_lists(cands, exclude_keys={"10.1/a"})
        self.assertEqual(merged, [])


class ReviewKeys(unittest.TestCase):
    def test_keys_and_seed_dois(self):
        data = {"papers": [
            {"doi": "10.1/A", "title": "X"},
            {"doi": "", "title": "Title Only"},
        ]}
        self.assertEqual(dc.review_data_keys(data), {"10.1/a", "titleonly"})
        self.assertEqual(dc.seed_dois_from_data(data), ["10.1/a"])


class CitationChasing(unittest.TestCase):
    def test_references_and_citations_excludes_seed(self):
        seed = make_work("W100", "Seed paper", doi="10.1/seed", refs=["https://openalex.org/W1", "https://openalex.org/W2"])
        ref1 = make_work("W1", "Referenced one", doi="10.1/r1", cited=300)
        ref2 = make_work("W2", "Referenced two", doi="10.1/r2", cited=10)
        citer = make_work("W9", "Citing paper", doi="10.1/c9", cited=80)

        data = {"papers": [{"doi": "10.1/seed", "title": "Seed paper"}]}

        with mock.patch.object(oa, "fetch_work_by_doi", return_value=seed), \
             mock.patch.object(oa, "fetch_works_by_ids", return_value=[ref1, ref2]), \
             mock.patch.object(oa, "fetch_citing_works", return_value=[citer]):
            cands = dc.candidates_from_citations(data, CONFIG, direction="both", max_per_paper=25)

        dois = {c["doi"] for c in cands}
        self.assertEqual(dois, {"10.1/r1", "10.1/r2", "10.1/c9"})  # seed excluded
        self.assertTrue(all("found via citation chasing" in c["why"] for c in cands))


if __name__ == "__main__":
    unittest.main()
