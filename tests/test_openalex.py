import pathlib
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from lit_agent import openalex as oa


SAMPLE_WORK = {
    "id": "https://openalex.org/W2741809807",
    "doi": "https://doi.org/10.1006/GAME.1995.1027",
    "title": "Trust, Reciprocity, and Social History",
    "publication_year": 1995,
    "authorships": [
        {"author": {"display_name": "Joyce Berg"}},
        {"author": {"display_name": "John Dickhaut"}},
    ],
    "primary_location": {"source": {"display_name": "Games and Economic Behavior"}},
    "abstract_inverted_index": {"We": [0], "study": [1], "trust": [2], "and": [3], "reciprocity.": [4]},
    "cited_by_count": 7421,
    "referenced_works": ["https://openalex.org/W1", "https://openalex.org/W2"],
    "concepts": [
        {"display_name": "Reciprocity", "score": 0.72},
        {"display_name": "Microeconomics", "score": 0.15},
    ],
    "type": "article",
    "best_oa_location": {"pdf_url": "https://example.org/berg1995.pdf"},
}


class PureHelpers(unittest.TestCase):
    def test_reconstruct_abstract_orders_words(self):
        self.assertEqual(
            oa.reconstruct_abstract({"b": [1], "a": [0], "c": [2]}),
            "a b c",
        )

    def test_reconstruct_abstract_handles_missing(self):
        self.assertEqual(oa.reconstruct_abstract(None), "")
        self.assertEqual(oa.reconstruct_abstract({}), "")
        self.assertEqual(oa.reconstruct_abstract({"x": "bad"}), "")

    def test_short_id(self):
        self.assertEqual(oa.short_id("https://openalex.org/W123"), "W123")
        self.assertEqual(oa.short_id("W123"), "W123")
        self.assertEqual(oa.short_id(""), "")

    def test_bare_doi_strips_prefixes(self):
        self.assertEqual(oa.bare_doi("https://doi.org/10.1/X"), "10.1/x")
        self.assertEqual(oa.bare_doi("doi:10.2/y"), "10.2/y")
        self.assertEqual(oa.bare_doi("10.3/Z"), "10.3/z")

    def test_author_name_reorders(self):
        self.assertEqual(oa.author_name("Joyce Berg"), "Berg, Joyce")
        self.assertEqual(oa.author_name("Berg, Joyce"), "Berg, Joyce")
        self.assertEqual(oa.author_name("Plato"), "Plato")


class FieldHelpers(unittest.TestCase):
    def test_basic_fields(self):
        self.assertEqual(oa.openalex_year(SAMPLE_WORK), "1995")
        self.assertEqual(oa.openalex_venue(SAMPLE_WORK), "Games and Economic Behavior")
        self.assertEqual(oa.openalex_cited_by_count(SAMPLE_WORK), 7421)
        self.assertEqual(oa.openalex_doi(SAMPLE_WORK), "10.1006/game.1995.1027")
        self.assertEqual(oa.openalex_oa_pdf_url(SAMPLE_WORK), "https://example.org/berg1995.pdf")
        self.assertEqual(oa.referenced_ids(SAMPLE_WORK), ["W1", "W2"])

    def test_authors_reordered_and_capped(self):
        self.assertEqual(oa.openalex_authors(SAMPLE_WORK), ["Berg, Joyce", "Dickhaut, John"])

    def test_concepts_score_filtered(self):
        # Microeconomics at 0.15 is below the 0.3 threshold and dropped.
        self.assertEqual(oa.openalex_concepts(SAMPLE_WORK), ["reciprocity"])

    def test_work_to_candidate(self):
        cand = oa.work_to_candidate(SAMPLE_WORK)
        self.assertEqual(cand["doi"], "10.1006/game.1995.1027")
        self.assertEqual(cand["abstract"], "We study trust and reciprocity.")
        self.assertEqual(cand["pdf_url"], "https://example.org/berg1995.pdf")
        self.assertEqual(cand["is_referenced_by_count"], 7421)
        self.assertEqual(cand["source"], "OpenAlex")
        self.assertEqual(cand["url"], "https://doi.org/10.1006/game.1995.1027")


class NetworkLayer(unittest.TestCase):
    def test_fetch_work_by_doi_unwraps_results(self):
        with mock.patch.object(oa, "_http_get_json", return_value={"results": [SAMPLE_WORK]}) as patched:
            work = oa.fetch_work_by_doi("10.1006/game.1995.1027", mailto="a@b.co")
        self.assertEqual(work["id"], SAMPLE_WORK["id"])
        called_url = patched.call_args.args[0]
        self.assertIn("filter=doi", called_url)

    def test_fetch_work_by_doi_empty(self):
        self.assertEqual(oa.fetch_work_by_doi(""), {})

    def test_fetch_works_by_ids_chunks(self):
        seen_batches = []

        def fake_get(url, mailto="", timeout=30):
            # Record how many ids were requested in this call (URL is percent-encoded).
            import urllib.parse as _up
            url = _up.unquote(url)
            filt = url.split("filter=openalex_id:")[1].split("&")[0]
            seen_batches.append(filt.split("|"))
            return {"results": [{"id": f"https://openalex.org/{i}"} for i in filt.split("|")]}

        ids = [f"W{i}" for i in range(120)]
        with mock.patch.object(oa, "_http_get_json", side_effect=fake_get):
            works = oa.fetch_works_by_ids(ids, chunk=50)
        self.assertEqual(len(works), 120)
        self.assertEqual([len(b) for b in seen_batches], [50, 50, 20])

    def test_fetch_citing_works_caps_results(self):
        works = [{"id": f"https://openalex.org/W{i}"} for i in range(40)]
        with mock.patch.object(oa, "_http_get_json", return_value={"results": works}):
            out = oa.fetch_citing_works("W999", max_results=10)
        self.assertEqual(len(out), 10)


if __name__ == "__main__":
    unittest.main()
