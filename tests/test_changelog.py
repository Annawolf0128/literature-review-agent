import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from lit_agent import changelog as cl


def paper(doi, title, **extra):
    rec = {"doi": doi, "title": title, "authors": ["Berg, Joyce", "Dickhaut, John"], "year": "1995"}
    rec.update(extra)
    return rec


OLD = {"papers": [
    paper("10.1/a", "Trust and reciprocity", summary="Old summary"),
    paper("10.1/b", "Reputation in markets"),
]}
NEW = {"papers": [
    paper("10.1/a", "Trust and reciprocity", summary="New summary"),  # updated
    paper("10.1/c", "Noisy returns and trust"),                        # added
]}  # 10.1/b removed


class DiffReviews(unittest.TestCase):
    def test_added_removed_updated(self):
        diff = cl.diff_reviews(OLD, NEW)
        self.assertEqual([p["doi"] for p in diff["added"]], ["10.1/c"])
        self.assertEqual([p["doi"] for p in diff["removed"]], ["10.1/b"])
        self.assertEqual(len(diff["updated"]), 1)
        self.assertEqual(diff["updated"][0]["paper"]["doi"], "10.1/a")
        self.assertEqual(diff["updated"][0]["fields"], ["summary"])

    def test_no_changes(self):
        diff = cl.diff_reviews(OLD, OLD)
        self.assertTrue(cl.diff_is_empty(diff))

    def test_cosmetic_whitespace_not_a_change(self):
        old = {"papers": [paper("10.1/a", "Trust", summary="A  b")]}
        new = {"papers": [paper("10.1/a", "Trust", summary="A b")]}
        self.assertTrue(cl.diff_is_empty(cl.diff_reviews(old, new)))

    def test_list_field_change_detected(self):
        old = {"papers": [paper("10.1/a", "Trust", keywords=["trust"])]}
        new = {"papers": [paper("10.1/a", "Trust", keywords=["trust", "reciprocity"])]}
        diff = cl.diff_reviews(old, new)
        self.assertEqual(diff["updated"][0]["fields"], ["keywords"])


class Render(unittest.TestCase):
    def test_section_lists_sections(self):
        diff = cl.diff_reviews(OLD, NEW)
        md = cl.render_changelog_section(diff, date="2026-06-26", action="enrich")
        self.assertIn("## 2026-06-26 — enrich", md)
        self.assertIn("### Added (1)", md)
        self.assertIn("### Removed (1)", md)
        self.assertIn("### Updated (1)", md)
        self.assertIn("summary", md)
        self.assertIn("Berg et al. (1995)", md)

    def test_empty_section(self):
        md = cl.render_changelog_section(cl.diff_reviews(OLD, OLD), date="2026-06-26")
        self.assertIn("_No changes._", md)

    def test_prepend_keeps_history_newest_first(self):
        first = cl.render_changelog_section(cl.diff_reviews(OLD, NEW), date="2026-06-01", action="build")
        doc = cl.prepend_changelog("", first)
        second = cl.render_changelog_section(cl.diff_reviews(NEW, OLD), date="2026-06-26", action="enrich")
        doc = cl.prepend_changelog(doc, second)
        self.assertEqual(doc.count("# Changelog"), 1)  # single title
        self.assertLess(doc.index("2026-06-26"), doc.index("2026-06-01"))  # newest first


if __name__ == "__main__":
    unittest.main()
