from __future__ import annotations

import argparse
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from pubmed_search import add_abstract_filter, add_year_filters, resolve_pubmed_query


class PubmedQueryTests(unittest.TestCase):
    def test_runtime_filters_are_idempotent(self):
        args = argparse.Namespace(from_year="2020", to_year="2025")
        first = add_year_filters(add_abstract_filter("long covid", True), args, {})
        second = add_year_filters(add_abstract_filter(first, True), args, {})
        self.assertEqual(first, second)
        self.assertEqual(first.casefold().count("hasabstract"), 1)
        self.assertEqual(first.casefold().count("[pdat]"), 1)

    def test_query_file_is_read_without_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            query_path = Path(tmp) / "query.txt"
            query_path.write_text("long covid[Title/Abstract]\n", encoding="utf-8")
            query = resolve_pubmed_query(None, str(query_path), {}, None)
            effective = add_abstract_filter(query, True)
            self.assertNotEqual(query, effective)
            self.assertEqual(query_path.read_text(encoding="utf-8"), "long covid[Title/Abstract]\n")


if __name__ == "__main__":
    unittest.main()
