from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from prepare_zotero_import import find_normalized_results, load_raw_bibliographic_enrichment, validate_manifest_uniqueness
from audit_synthesis_links import audit as audit_synthesis_links
from run_outputs import count_no_fulltext_exclusions, human_gate_status
from sync_zotero_mcp import exclusive_collection_lock
from validate_human_review_gate import evaluate_gate
from write_zotero_notes import group_rows_by_study


class PostselectionWorkflowTests(unittest.TestCase):
    def test_zotero_prefers_merged_normalized_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            screening = root / "screening"
            search = root / "search"
            screening.mkdir()
            search.mkdir()
            matrix = screening / "screening_matrix.csv"
            matrix.touch()
            (search / "normalized_results.json").write_text("[]", encoding="utf-8")
            merged = search / "merged_normalized_results.json"
            merged.write_text("[]", encoding="utf-8")
            self.assertEqual(find_normalized_results(matrix), merged)

    def test_zotero_manifest_rejects_duplicate_identity(self):
        with self.assertRaises(ValueError):
            validate_manifest_uniqueness([
                {"code": "A", "doi": "10.1/test", "title": "One"},
                {"code": "B", "doi": "https://doi.org/10.1/test", "title": "Two"},
            ])

    def test_zotero_enriches_volume_issue_pages_from_raw_scopus(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "scopus"
            source.mkdir()
            (source / "raw_results.json").write_text(
                '[{"DOI":"10.1/test","Publisher":"Pub","Volume":"7","Issue":"2",'
                '"Page start":"10","Page end":"19","Source title":"Journal"}]',
                encoding="utf-8",
            )
            enriched = load_raw_bibliographic_enrichment(Path(tmp))
            self.assertEqual(enriched["10.1/test"]["pages"], "10-19")
            self.assertEqual(enriched["10.1/test"]["volume"], "7")

    def test_collection_lock_blocks_concurrent_sync(self):
        with exclusive_collection_lock("user", "A/B"):
            with self.assertRaises(RuntimeError):
                with exclusive_collection_lock("user", "A/B"):
                    pass

    def test_relational_rows_are_grouped_without_loss(self):
        grouped = group_rows_by_study([
            {"Codigo estudio": "M1", "Mecanismo": "Diario", "Estado de revision": "Validado"},
            {"Codigo estudio": "M1", "Mecanismo": "PROM", "Estado de revision": "Validado"},
        ])
        self.assertIn("Instancia 1 · Mecanismo", grouped["M1"])
        self.assertIn("Instancia 2 · Mecanismo", grouped["M1"])

    def test_human_gate_distinguishes_proposal_from_validated(self):
        with tempfile.TemporaryDirectory() as tmp:
            matrix = Path(tmp) / "extraction.csv"
            matrix.write_text(
                "Codigo estudio,Hallazgo,Estado de revision\nM1,Uno,Pendiente\nM1,Dos,Validado\n",
                encoding="utf-8",
            )
            pending = evaluate_gate(matrix, "extraction")
            self.assertFalse(pending["human_validation_complete"])
            matrix.write_text(
                "Codigo estudio,Hallazgo,Estado de revision\nM1,Uno,Validado\nM1,Dos,Validado\n",
                encoding="utf-8",
            )
            complete = evaluate_gate(matrix, "extraction")
            self.assertTrue(complete["human_validation_complete"])
            self.assertEqual(complete["unique_studies"], 1)

    def test_run_phase_needs_human_gate_or_completion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            extraction = root / "extraction"
            extraction.mkdir()
            matrix = extraction / "extraction_matrix.md"
            matrix.write_text("# Matrix\n\n| Codigo | Estado de revision |\n|---|---|\n| M1 | Pendiente |\n", encoding="utf-8")
            self.assertIn("propuesta", human_gate_status(root, "extraction", matrix))
            (extraction / "phase9_completion.md").write_text("El usuario validó explícitamente la extracción.", encoding="utf-8")
            self.assertEqual(human_gate_status(root, "extraction", matrix), "cerrada")

    def test_fx0_count_accepts_code_and_basis(self):
        rows = [
            {"code": "A", "criterion": "FX0", "final_basis": ""},
            {"code": "B", "criterion": "Otro", "final_basis": "Sin texto completo accesible"},
            {"code": "C", "criterion": "Otro", "final_basis": "Texto completo"},
        ]
        self.assertEqual(count_no_fulltext_exclusions(rows), 2)

    def test_synthesis_audit_validates_source_evidence_pair(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            synthesis = root / "synthesis"
            fulltext = root / "fulltext"
            review = fulltext / "review_text"
            synthesis.mkdir()
            review.mkdir(parents=True)
            (fulltext / "M001_study.html").write_text("<article>full</article>", encoding="utf-8")
            (review / "M001_study.txt").write_text("one\ntwo\nthree\n", encoding="utf-8")
            narrative = synthesis / "narrative.md"
            narrative.write_text(
                "Evidence [`M001`](../fulltext/M001_study.html) "
                "[`L002`](../fulltext/review_text/M001_study.txt).\n",
                encoding="utf-8",
            )
            result = audit_synthesis_links(narrative)
            self.assertTrue(result["valid"])


if __name__ == "__main__":
    unittest.main()
