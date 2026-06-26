import pathlib
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from lit_agent import pdftext as pt


FULL_TEXT = (
    "Trust, Reciprocity, and Social History. "
    "Abstract. We study trust and reciprocity in an investment game. "
    "Introduction. Trust is central to exchange. "
    "Methods. We recruit 32 participants who each receive a 10 dollar endowment "
    "and decide how much to send to a paired counterpart. "
    "Results. We find that most first movers send positive amounts and that "
    "reciprocity is significant. "
    "Conclusion. Trust and reciprocity sustain exchange."
)


class PureHelpers(unittest.TestCase):
    def test_looks_like_pdf(self):
        self.assertTrue(pt.looks_like_pdf(b"%PDF-1.7 ..."))
        self.assertFalse(pt.looks_like_pdf(b"<html>"))
        self.assertFalse(pt.looks_like_pdf(""))

    def test_clean_dehyphenates_and_drops_page_numbers(self):
        raw = "reci-\nprocity matters\n12\nhere"
        self.assertEqual(pt.clean_pdf_text(raw), "reciprocity matters here")

    def test_split_into_sections(self):
        sections = pt.split_into_sections(FULL_TEXT)
        self.assertIn("abstract", sections)
        self.assertIn("method", sections)
        self.assertIn("results", sections)
        self.assertTrue(sections["method"].lower().startswith("we recruit"))
        self.assertIn("positive amounts", sections["results"])

    def test_pick_relevant_excerpt_matches_terms(self):
        excerpt = pt.pick_relevant_excerpt(FULL_TEXT, ["reciprocity"], max_sentences=1)
        self.assertIn("reciprocity", excerpt.lower())

    def test_pick_relevant_excerpt_fallback(self):
        excerpt = pt.pick_relevant_excerpt("One sentence. Two sentence.", ["zzz"], max_sentences=1)
        self.assertEqual(excerpt, "One sentence.")

    def test_cache_name_stable_and_safe(self):
        a = pt.cache_name_for_url("https://x.org/a.pdf")
        b = pt.cache_name_for_url("https://x.org/a.pdf")
        self.assertEqual(a, b)
        self.assertTrue(a.endswith(".pdf"))
        self.assertNotIn("/", a)


class FetchLayer(unittest.TestCase):
    def test_fetch_url_downloads_and_extracts(self):
        with mock.patch.object(pt, "_download", return_value=b"%PDF-1.7 fake") as dl, \
             mock.patch.object(pt, "extract_text_from_bytes", return_value="extracted text") as ex:
            out = pt.fetch_pdf_text("https://x.org/a.pdf", mailto="a@b.co")
        self.assertEqual(out, "extracted text")
        dl.assert_called_once()
        ex.assert_called_once()

    def test_fetch_url_non_pdf_returns_empty(self):
        with mock.patch.object(pt, "_download", return_value=b"<html>not a pdf"):
            self.assertEqual(pt.fetch_pdf_text("https://x.org/a.pdf"), "")

    def test_fetch_empty_source(self):
        self.assertEqual(pt.fetch_pdf_text(""), "")

    def test_fetch_local_missing_file(self):
        self.assertEqual(pt.fetch_pdf_text("/no/such/file.pdf"), "")

    def test_fetch_uses_cache(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            # First call downloads and writes cache.
            with mock.patch.object(pt, "_download", return_value=b"%PDF-1.7 data") as dl, \
                 mock.patch.object(pt, "extract_text_from_bytes", return_value="text"):
                pt.fetch_pdf_text("https://x.org/a.pdf", cache_dir=tmp)
                self.assertEqual(dl.call_count, 1)
            # Second call reads cache without downloading again.
            with mock.patch.object(pt, "_download", side_effect=AssertionError("should not download")) as dl2, \
                 mock.patch.object(pt, "extract_text_from_bytes", return_value="text"):
                out = pt.fetch_pdf_text("https://x.org/a.pdf", cache_dir=tmp)
        self.assertEqual(out, "text")


if __name__ == "__main__":
    unittest.main()
