from __future__ import annotations

import json
import unittest
from pathlib import Path

from labs.navigation.navigation import (
    combine_evidence,
    compare_navigation,
    document_tree,
    find_sections,
    read_range,
    parse_markdown,
)


TEXT = """# Manual
## Install
Install the client.
Use version 3.
## Appendix
### Limits
Version 3 is not supported in the free plan.
"""


class FixtureEmbedding:
    """Fixed vectors test integration math, not neural model quality."""

    def embed(self, texts):
        for text in texts:
            lowered = text.lower()
            yield [float("linux" in lowered), float("free" in lowered),
                   float("maintenance" in lowered), 0.01]


class NavigationTests(unittest.TestCase):
    def test_tree_preserves_parent_and_order(self):
        sections = document_tree(TEXT)
        self.assertEqual(parse_markdown(TEXT)[1].title, "Install")
        self.assertEqual([section.title for section in sections], ["Manual", "Install", "Appendix", "Limits"])
        self.assertEqual(sections[0].children, ["s2", "s3"])
        self.assertEqual(sections[1].end_line, 4)
        self.assertEqual(sections[2].end_line, 7)

    def test_no_heading_and_preamble_are_not_lost(self):
        sections = document_tree("plain text\nsecond line\n")
        self.assertEqual(len(sections), 1)
        self.assertEqual(sections[0].title, "Document")
        self.assertEqual(read_range("plain text\nsecond line\n", sections[0]).quote,
                         "plain text\nsecond line\n")
        self.assertEqual(document_tree("") , [])
        self.assertEqual(document_tree("preamble\n# Heading\n")[0].id, "preamble")

    def test_fenced_examples_indentation_and_duplicate_titles(self):
        text = "# Root\n```md\n# fake\n```\n~~~\n## also fake\n~~~~\n    # code\n## C#\n## Same\n## Same\n"
        sections = document_tree(text)
        self.assertEqual([section.title for section in sections], ["Root", "C#", "Same", "Same"])
        self.assertNotEqual(sections[-1].id, sections[-2].id)
        self.assertEqual([section.start_line for section in sections], [1, 9, 10, 11])

    def test_find_section_returns_appendix_condition(self):
        sections = document_tree(TEXT)
        self.assertEqual(find_sections(sections, "free plan")[0].title, "Limits")
        self.assertEqual(find_sections(sections, "unmentioned"), [])
        self.assertEqual(find_sections(sections, ""), [])
        self.assertNotIn("Install the client", sections[0].text)

    def test_range_reports_actual_truncated_offsets(self):
        section = document_tree(TEXT)[0]
        result = read_range(TEXT, section, max_lines=2)
        quote, truncated = result
        self.assertEqual((quote, truncated), (result.quote, result.truncated))
        self.assertTrue(result.truncated)
        self.assertEqual(result.end_line, 2)
        self.assertEqual(result.quote, "# Manual\n## Install\n")
        self.assertEqual(result.quote, TEXT[result.start_offset:result.end_offset])

    def test_range_expansion_crosses_section_boundary_exactly(self):
        text = "# 手册\r\n## Install\r\nAllowed.\r\n## Limit\r\nExcept free plans.\r\n"
        section = document_tree(text, source_id="manual", source_version="v1")[1]
        result = read_range(text, section, after=2)
        self.assertEqual((result.start_line, result.end_line), (2, 5))
        self.assertEqual(result.source_id, "manual")
        self.assertIn("Except free plans.\r\n", result.quote)
        self.assertEqual(result.quote, text[result.start_offset:result.end_offset])

    def test_stale_and_invalid_ranges_rejected(self):
        section = document_tree(TEXT)[0]
        with self.assertRaises(ValueError):
            read_range(TEXT, section, max_lines=0)
        with self.assertRaises(ValueError):
            read_range(TEXT + "changed", section)
        with self.assertRaises(ValueError):
            read_range(TEXT, section, before=-1)

    def test_combine_keeps_conflicts_and_source_versions(self):
        documents = {("manual", "v1"): TEXT, ("release", "v1"): "# Release\n## Sunset\nVersion 3 retired.\n"}
        evidence = combine_evidence(documents, ["install", "free plan", "retired"])
        self.assertEqual([(item.source_id, item.section_id) for item in evidence],
                         [("manual", "s2"), ("manual", "s4"), ("release", "s2")])
        self.assertIn("Use version 3", evidence[0].quote)
        self.assertIn("not supported", evidence[1].quote)
        for item in evidence:
            source = documents[(item.source_id, item.source_version)]
            self.assertEqual(item.quote, source[item.start_offset:item.end_offset])

    def test_combine_deduplicates_and_keeps_truncation_visible(self):
        documents = {("manual", "v1"): TEXT}
        evidence = combine_evidence(documents, ["install", "install"], max_lines=1)
        self.assertEqual(len(evidence), 1)
        self.assertTrue(evidence[0].truncated)
        self.assertEqual(evidence[0].start_line, evidence[0].end_line)

    def test_hybrid_requires_model_and_comparison_splits_question_categories(self):
        fixture = Path("fixtures/navigation")
        documents = {("manual", "v1"): (fixture / "manual-v1.md").read_text(),
                     ("release", "v1"): (fixture / "release-v1.md").read_text()}
        cases = json.loads((fixture / "questions.json").read_text())
        with self.assertRaises(ValueError):
            combine_evidence(documents, ["install"], strategy="hybrid")
        report = compare_navigation(documents, cases, embedding=FixtureEmbedding())
        for strategy in ("tree", "hybrid"):
            self.assertEqual(report[strategy]["single_document"]["questions"], 1)
            self.assertEqual(report[strategy]["multi_document"]["questions"], 1)
            self.assertEqual(report[strategy]["single_document"]["mean_recall"], 1.0)
            self.assertEqual(report[strategy]["multi_document"]["mean_recall"], 1.0)

if __name__ == "__main__":
    unittest.main()
