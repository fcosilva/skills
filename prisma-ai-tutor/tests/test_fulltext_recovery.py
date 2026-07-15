from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from download_fulltext import cached_fulltext_is_valid, discover_openalex, recover_one
from fulltext_utils import bibliographic_identity, classify_payload, inspect_html
from prepare_fulltext_review_text import extract_pdf_text, prepare_one, synchronize_matrix
import validate_fulltext_access


def full_article_html() -> bytes:
    body = " ".join(["patient symptom monitoring outcome"] * 320)
    return f"""
    <html><head><title>Study</title><meta name="citation_title" content="Study"></head>
    <body><article class="main-article-body">
    <h2>Abstract</h2><p>{body}</p><h2>Introduction</h2><p>{body}</p>
    <h2>Methods</h2><p>{body}</p><h2>Results</h2><p>{body}</p>
    <h2>Discussion</h2><p>{body}</p><h2>References</h2><p>Reference one.</p>
    </article><script>cloudflare captcha login error</script></body></html>
    """.encode()


class FakeResponse:
    def __init__(self, url: str, payload: bytes, content_type: str) -> None:
        self.url = url
        self.payload = payload
        self.headers = {"Content-Type": content_type}
        self.status = 200

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, *args):
        return self.payload

    def geturl(self):
        return self.url


class FakeOpener:
    def __init__(self, responses):
        self.responses = responses

    def open(self, req, timeout=None):
        payload, content_type = self.responses[req.full_url]
        return FakeResponse(req.full_url, payload, content_type)


class FulltextRecoveryTests(unittest.TestCase):
    def test_pdf_extension_with_challenge_html_is_not_pdf(self):
        payload = b"<html><title>Preparing to download ...</title><body>Verify you are human</body></html>"
        status, kind, _ = classify_payload("https://example.org/file.pdf", "text/html", payload)
        self.assertEqual((status, kind), ("downloaded_blocked_page", "blocked_or_error"))

    def test_full_article_ignores_cloudflare_words_inside_script(self):
        inspection = inspect_html(full_article_html(), "https://example.org/article")
        self.assertTrue(inspection.full_article)
        self.assertFalse(inspection.blocked)

    def test_abstract_only_page_is_landing(self):
        payload = b"<html><head><meta name='citation_title' content='Study'></head><body><h2>Abstract</h2><p>Short abstract only.</p></body></html>"
        status, kind, _ = classify_payload("https://example.org/article", "text/html", payload)
        self.assertEqual((status, kind), ("downloaded_landing_page", "landing_metadata_only"))

    def test_pubmed_page_is_landing_even_when_navigation_looks_like_article(self):
        status, kind, _ = classify_payload(
            "https://pubmed.ncbi.nlm.nih.gov/12345/", "text/html", full_article_html()
        )
        self.assertEqual((status, kind), ("downloaded_landing_page", "landing_metadata_only"))

    def test_long_repository_abstract_with_body_marker_is_still_landing(self):
        filler = " ".join(["symptom outcome cohort"] * 700)
        payload = (
            "<html><head><meta name='citation_title' content='Study'></head>"
            f"<body><div class='article-body'><h2>Abstract</h2><p>{filler}</p>"
            "<h2>References</h2><p>Index references only.</p></div></body></html>"
        ).encode()
        status, kind, _ = classify_payload("https://repository.example/item/1", "text/html", payload)
        self.assertEqual((status, kind), ("downloaded_landing_page", "landing_metadata_only"))

    def test_incomplete_meta_tag_does_not_crash(self):
        payload = b"<html><head><meta charset='utf-8'></head><body>Metadata only</body></html>"
        status, kind, _ = classify_payload("https://example.org/article", "text/html", payload)
        self.assertEqual((status, kind), ("downloaded_landing_page", "landing_metadata_only"))

    def test_declared_pdf_link_is_followed(self):
        landing = b"<html><head><meta name='citation_pdf_url' content='/paper.pdf'></head><body>Metadata</body></html>"
        pdf = b"%PDF-1.4\nsynthetic test"
        opener = FakeOpener({
            "https://example.org/landing": (landing, "text/html"),
            "https://example.org/paper.pdf": (pdf, "text/html"),
        })
        with tempfile.TemporaryDirectory() as tmp:
            result, attempts = recover_one(
                "T001", "Study", [("matrix_access", "https://example.org/landing")],
                Path(tmp), opener, None, 1.0, 3, 0.0,
            )
            self.assertEqual(result["access_kind"], "pdf_fulltext")
            self.assertEqual(result["route"], "matrix_access:html_link")
            self.assertEqual(len(attempts), 2)

    def test_prepare_rejects_html_disguised_as_pdf(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "challenge.pdf"
            destination = Path(tmp) / "challenge.txt"
            source.write_bytes(b"<html><body>Preparing to download</body></html>")
            status, message, words = extract_pdf_text(source, destination, 10)
            self.assertEqual(status, "error")
            self.assertIn("magic signature", message)
            self.assertEqual(words, 0)

    def test_cached_fulltext_is_reinspected_before_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "false-positive.pdf"
            source.write_bytes(b"<html><body>Verify you are human</body></html>")
            self.assertFalse(cached_fulltext_is_valid({
                "local_path": str(source),
                "final_url": "https://example.org/file.pdf",
                "content_type": "application/pdf",
            }))

    def test_openalex_discovery_uses_only_oa_locations_and_prefers_pdf(self):
        payload = b'''{"best_oa_location":{"pdf_url":"https://oa.example/a.pdf","landing_page_url":"https://oa.example/a"},"primary_location":{"pdf_url":"https://closed.example/a.pdf","landing_page_url":"https://closed.example/a"},"locations":[{"is_oa":false,"pdf_url":"https://closed.example/b.pdf"},{"is_oa":true,"pdf_url":"https://repo.example/a.pdf","landing_page_url":"https://repo.example/a"}]}'''
        opener = FakeOpener({
            "https://api.openalex.org/works/https://doi.org/10.1/test": (payload, "application/json")
        })
        urls = discover_openalex("10.1/test", opener, None, 1.0)
        self.assertEqual(urls[:2], ["https://oa.example/a.pdf", "https://repo.example/a.pdf"])
        self.assertFalse(any("closed.example" in url for url in urls))

    def test_bibliographic_identity_requires_two_signals(self):
        status, evidence = bibliographic_identity(
            "Development of a symptom questionnaire for long COVID",
            "10.1234/example",
            "Smith et al. (2022)",
            "Development of a symptom questionnaire for long COVID. Smith and colleagues. 2022.",
        )
        self.assertEqual(status, "confirmed")
        self.assertIn("title=", evidence)

    def test_bibliographic_mismatch_is_quarantined(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "M001_wrong.html"
            source.write_bytes(full_article_html())
            result = prepare_one(
                source,
                root / "text",
                {"code": "M001", "access_kind": "html_fulltext"},
                10,
                expected={
                    "Titulo": "A completely unrelated entomology paper",
                    "DOI": "10.9999/wrong",
                    "Autor/ano": "Garcia (1998)",
                },
                quarantine_dir=root / "quarantine",
            )
            self.assertEqual(result["status"], "identity_mismatch")
            self.assertTrue(Path(result["quarantine_path"]).exists())
            self.assertFalse(Path(result["output_path"]).exists())

    def test_matrix_sync_uses_prepared_codes(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "screening_matrix.csv"
            md_path = Path(tmp) / "screening_matrix.md"
            csv_path.write_text(
                "Codigo,Titulo,Texto completo accesible\nA,One,Por verificar\nB,Two,Si\n",
                encoding="utf-8",
            )
            changed = synchronize_matrix(csv_path, {"A", "B"}, {"A"})
            self.assertEqual(changed, 2)
            text = csv_path.read_text(encoding="utf-8")
            self.assertIn("A,One,Si", text)
            self.assertIn("B,Two,No confirmado", text)
            self.assertTrue(md_path.exists())

    def test_remote_validation_never_sets_final_yes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            matrix = root / "screening_matrix.csv"
            decisions = root / "decisions.csv"
            log = root / "validation.csv"
            matrix.write_text(
                "Codigo,URL de acceso,Texto completo accesible\nA,https://example.org/a,No confirmado\n",
                encoding="utf-8",
            )
            decisions.write_text("code,decision\nA,Incluir\n", encoding="utf-8")
            argv = [
                "validate_fulltext_access.py", "--matrix", str(matrix),
                "--decisions", str(decisions), "--log", str(log),
            ]
            with mock.patch.object(sys, "argv", argv), mock.patch.object(
                validate_fulltext_access,
                "validate_fulltext_url",
                return_value=(True, "pdf_fulltext", "verified", "https://example.org/a.pdf"),
            ), mock.patch.object(validate_fulltext_access, "refresh_run_outputs"):
                self.assertEqual(validate_fulltext_access.main(), 0)
            updated = matrix.read_text(encoding="utf-8")
            self.assertIn("Por verificar", updated)
            self.assertNotIn(",Si", updated)


if __name__ == "__main__":
    unittest.main()
