#!/usr/bin/env python3
"""Shared content inspection helpers for legitimate full-text recovery."""

from __future__ import annotations

import html
import re
import unicodedata
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

PDF_MAGIC = b"%PDF-"
MIN_HTML_FULLTEXT_WORDS = 1000


@dataclass
class HtmlInspection:
    visible_text: str
    word_count: int
    title: str = ""
    meta: dict[str, str] = field(default_factory=dict)
    links: list[str] = field(default_factory=list)
    headings: list[str] = field(default_factory=list)
    section_score: int = 0
    has_article_body_marker: bool = False
    blocked: bool = False
    full_article: bool = False


class ScholarlyHTMLParser(HTMLParser):
    SKIP_TAGS = {"script", "style", "noscript", "svg", "template"}

    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.skip_depth = 0
        self.in_title = False
        self.title_chunks: list[str] = []
        self.text_chunks: list[str] = []
        self.meta: dict[str, str] = {}
        self.links: list[str] = []
        self.headings: list[str] = []
        self.heading_depth = 0
        self.heading_chunks: list[str] = []
        self.has_semantic_article = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        values = {key.lower(): value or "" for key, value in attrs}
        if tag in self.SKIP_TAGS:
            self.skip_depth += 1
        if tag == "title":
            self.in_title = True
        if tag in {"h1", "h2", "h3", "h4"}:
            self.heading_depth += 1
            self.heading_chunks = []
        marker = " ".join((values.get("class", ""), values.get("id", ""), values.get("role", ""))).casefold()
        if tag in {"article", "main"} or any(
            value in marker for value in ("article-body", "article__body", "main-article-body", "fulltext")
        ):
            self.has_semantic_article = True
        if tag == "meta":
            key = (values.get("name") or values.get("property") or values.get("http-equiv") or "").lower()
            content = values.get("content", "").strip()
            if key and content:
                self.meta[key] = content
        if tag in {"a", "link"}:
            href = values.get("href", "").strip()
            if href:
                self.links.append(urljoin(self.base_url, html.unescape(href)))

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "title":
            self.in_title = False
        if tag in {"h1", "h2", "h3", "h4"} and self.heading_depth:
            heading = " ".join(self.heading_chunks).strip()
            if heading:
                self.headings.append(heading)
            self.heading_depth -= 1
            self.heading_chunks = []
        if tag in self.SKIP_TAGS and self.skip_depth:
            self.skip_depth -= 1

    def handle_data(self, data: str) -> None:
        text = " ".join(data.split())
        if not text:
            return
        if self.in_title:
            self.title_chunks.append(text)
        if self.heading_depth:
            self.heading_chunks.append(text)
        if not self.skip_depth:
            self.text_chunks.append(text)


def is_pdf_payload(payload: bytes) -> bool:
    return payload.lstrip().startswith(PDF_MAGIC)


def looks_like_html(payload: bytes, content_type: str = "") -> bool:
    if "html" in content_type.lower() or "xhtml" in content_type.lower():
        return True
    prefix = payload[:1024].lstrip().lower()
    return prefix.startswith((b"<!doctype html", b"<html", b"<?xml")) or b"<html" in prefix


def inspect_html(payload: bytes, base_url: str = "") -> HtmlInspection:
    source = payload.decode("utf-8", errors="ignore")
    parser = ScholarlyHTMLParser(base_url)
    parser.feed(source)
    visible = "\n".join(parser.text_chunks).strip()
    folded = visible.casefold()
    raw_folded = source.casefold()
    title = " ".join(parser.title_chunks).strip()
    word_count = len(re.findall(r"\b\w+\b", visible, flags=re.UNICODE))

    exact_challenges = (
        "making sure you're not a bot",
        "making sure you’re not a bot",
        "preparing to download",
        "checking your browser before accessing",
        "verify you are human",
        "complete the security check",
        "attention required! | cloudflare",
    )
    challenge_signal = any(marker in folded[:6000] for marker in exact_challenges)
    challenge_signal = challenge_signal or "cf-chl-" in raw_folded or "captcha" in title.casefold()
    empty_or_script_only = word_count < 20 and len(source) > 500
    blocked = (challenge_signal and word_count < 1000) or empty_or_script_only

    section_groups = (
        ("abstract", "summary"),
        ("introduction", "background"),
        ("methods", "methodology", "materials and methods", "study design"),
        ("results", "findings"),
        ("discussion", "conclusion", "conclusions"),
        ("references", "bibliography"),
    )
    heading_text = "\n".join(parser.headings).casefold()
    section_score = sum(any(term in heading_text for term in group) for group in section_groups)
    body_markers = (
        "main-article-body",
        "article-body",
        "article__body",
        "fulltext-view",
        "full-article",
        "jats-body",
        'property="articlebody"',
    )
    has_body = parser.has_semantic_article or any(marker in raw_folded for marker in body_markers)
    citation_title = parser.meta.get("citation_title") or parser.meta.get("dc.title")
    full_article = (
        not blocked
        and (
            (has_body and bool(citation_title) and word_count >= MIN_HTML_FULLTEXT_WORDS and section_score >= 4)
            or (
                bool(citation_title)
                and (
                    (word_count >= 1500 and section_score >= 4)
                    or (word_count >= 1000 and section_score >= 5)
                )
            )
            or (word_count >= 4000 and section_score >= 5)
        )
    )
    return HtmlInspection(
        visible_text=visible,
        word_count=word_count,
        title=title,
        meta=parser.meta,
        links=deduplicate(parser.links),
        headings=parser.headings,
        section_score=section_score,
        has_article_body_marker=has_body,
        blocked=blocked,
        full_article=full_article,
    )


def classify_payload(final_url: str, content_type: str, payload: bytes) -> tuple[str, str, str]:
    """Return status, access kind, and evidence without trusting URL extension."""
    if is_pdf_payload(payload):
        return "downloaded_pdf", "pdf_fulltext", "PDF magic signature verified."
    if looks_like_html(payload, content_type):
        inspection = inspect_html(payload, final_url)
        if inspection.blocked:
            return (
                "downloaded_blocked_page",
                "blocked_or_error",
                f"Human-verification or access challenge; visible_words={inspection.word_count}.",
            )
        if inspection.full_article and not is_known_abstract_landing(final_url, inspection):
            return (
                "downloaded_fulltext_html",
                "html_fulltext",
                f"Scholarly HTML body verified; visible_words={inspection.word_count}; sections={inspection.section_score}.",
            )
        return (
            "downloaded_landing_page",
            "landing_metadata_only",
            f"No complete scholarly body verified; visible_words={inspection.word_count}; sections={inspection.section_score}.",
        )
    return "downloaded_binary", "binary", "Unsupported binary payload."


def is_known_abstract_landing(final_url: str, inspection: HtmlInspection) -> bool:
    """Keep known abstract/index pages from being promoted by their large navigation text."""
    parsed = urlparse(final_url)
    host = parsed.netloc.casefold()
    path = parsed.path.casefold()
    if host == "pubmed.ncbi.nlm.nih.gov":
        return True
    if any(marker in path for marker in ("/article-abstract/", "/abstract/", "/abs/")):
        return not (inspection.has_article_body_marker and inspection.section_score >= 4)
    return False


def candidate_document_links(payload: bytes, base_url: str) -> list[str]:
    if not looks_like_html(payload, "text/html"):
        return []
    inspection = inspect_html(payload, base_url)
    candidates: list[str] = []
    for key in ("citation_pdf_url", "eprints.document_url", "dc.identifier"):
        value = inspection.meta.get(key, "").strip()
        if value:
            candidates.append(urljoin(base_url, value))
    for link in inspection.links:
        folded = link.casefold()
        if folded.endswith(".pdf") or any(
            marker in folded for marker in ("/pdf", "pdf=render", "/download", "download=1", "viewcontent.cgi")
        ):
            candidates.append(link)
    return deduplicate(candidates)


def deduplicate(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        clean = value.strip()
        if clean and clean not in seen:
            seen.add(clean)
            output.append(clean)
    return output


def normalize_doi(value: str) -> str:
    clean = value.strip()
    clean = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", clean, flags=re.I)
    clean = re.sub(r"^doi:\s*", "", clean, flags=re.I)
    return clean.strip()


def normalize_bibliographic_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    ascii_text = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", ascii_text.casefold()).strip()


def bibliographic_identity(
    expected_title: str,
    expected_doi: str,
    expected_author_year: str,
    observed_text: str,
    observed_title: str = "",
) -> tuple[str, str]:
    """Compare independent identity signals before admitting recovered content.

    Return ``confirmed``, ``mismatch`` or ``insufficient`` plus an auditable
    signal summary. Confirmation requires two positive signals among title,
    DOI, first-author surname and year.
    """
    haystack = normalize_bibliographic_text(" ".join((observed_title, observed_text[:12000])))
    positives: list[str] = []
    negatives: list[str] = []

    expected_title_norm = normalize_bibliographic_text(expected_title)
    title_tokens = {token for token in expected_title_norm.split() if len(token) > 2}
    if title_tokens:
        overlap = sum(token in set(haystack.split()) for token in title_tokens) / len(title_tokens)
        (positives if overlap >= 0.65 else negatives).append(f"title={overlap:.2f}")

    doi = normalize_doi(expected_doi).casefold()
    if doi:
        observed_raw = " ".join((observed_title, observed_text[:20000])).casefold()
        (positives if doi in observed_raw else negatives).append("doi")

    author_year = normalize_bibliographic_text(expected_author_year)
    author_tokens = [token for token in author_year.split() if len(token) > 2 and not token.isdigit()]
    if author_tokens:
        surname = author_tokens[0]
        (positives if re.search(rf"\b{re.escape(surname)}\b", haystack) else negatives).append("author")

    year_match = re.search(r"\b(?:18|19|20)\d{2}\b", expected_author_year)
    if year_match:
        year = year_match.group(0)
        (positives if year in observed_text[:12000] or year in observed_title else negatives).append("year")

    evidence = f"positive={','.join(positives) or 'none'}; negative={','.join(negatives) or 'none'}"
    if len(positives) >= 2:
        return "confirmed", evidence
    if len(positives) < 2 and len(negatives) >= 2:
        return "mismatch", evidence
    return "insufficient", evidence
