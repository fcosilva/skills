#!/usr/bin/env python3
"""Search SciELO and export normalized results for PRISMA-style workflows."""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Any
from urllib import error, parse, request

from metadata_config import DEFAULT_METADATA_CONFIG_PATH, load_metadata_config
from openalex_search import (
    compute_quality_snapshot,
    ensure_dir,
    headers_for_columns,
    load_env_config,
    render_count_lines,
    render_warning_lines,
    resolve_bool_flag,
    resolve_choice,
    resolve_float,
    resolve_int,
    resolve_query,
    resolve_str,
    resolve_workspace_path,
    write_csv,
    write_json,
    write_query_file,
    write_screening_matrix,
    write_screening_matrix_csv,
)
from run_outputs import refresh_run_outputs


SEARCH_URL = "https://search.scielo.org/"
DEFAULT_COUNT = 20
MAX_COUNT = 200
DEFAULT_MAX_RESULTS = 100
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_DELAY = 2.0
DEFAULT_MAX_RETRY_WAIT = 60.0
DEFAULT_RESULTS_THRESHOLD = 500
RESULTS_PER_REQUEST_HARD_CAP = 200
TEXT_LANG_LABELS = {
    "es": "Es",
    "en": "En",
    "pt": "Pt",
}
GENERIC_LINK_TEXTS = {
    "facebook",
    "twitter",
    "linkedin",
    "reddit",
    "mendeley",
    "google+",
    "citeulike",
    "stambleupon",
    "metrics",
    "dimensions",
    "plumx",
    "altmetric",
    "scielo analytics",
    "sobre o periódico",
    "sobre el periódico",
    "about the journal",
    "other social networks",
    "otras redes sociales",
    "outras redes sociais",
    "journal metrics",
    "métricas do periódico",
    "métricas del periódico",
}


@dataclass
class SearchConfig:
    query: str
    html_file: Path | None
    interface_lang: str
    collection: str | None
    document_type: str | None
    from_year: str | None
    to_year: str | None
    require_abstract: bool
    count: int
    max_results: int
    sampling_threshold: int
    quiet_progress: bool
    max_retries: int
    retry_delay: float
    max_retry_wait: float
    out_dir: Path
    query_output_name: str
    config_file: Path | None
    metadata_config_file: Path


def parse_args() -> SearchConfig:
    parser = argparse.ArgumentParser(
        description=(
            "Run a SciELO literature search and export normalized results for "
            "screening and traceability."
        )
    )
    parser.add_argument(
        "query",
        nargs="?",
        help="Text query for the search. Optional when --query-file is used.",
    )
    parser.add_argument(
        "--query-file",
        help="Path to a text file containing the search query.",
    )
    parser.add_argument(
        "--html-file",
        help=(
            "Path to an HTML file saved manually from a SciELO search results page. "
            "Useful when the live site is protected by a browser challenge."
        ),
    )
    parser.add_argument(
        "--config-file",
        help=(
            "Path to an env-style configuration file. Supported keys: "
            "SCIELO_QUERY_FILE, SCIELO_HTML_FILE, SCIELO_INTERFACE_LANG, SCIELO_COLLECTION, "
            "SCIELO_DOCUMENT_TYPE, SCIELO_FROM_YEAR, SCIELO_TO_YEAR, "
            "SCIELO_REQUIRE_ABSTRACT, SCIELO_COUNT, SCIELO_MAX_RESULTS, "
            "PRISMA_MAX_RESULTS_THRESHOLD, SCIELO_MAX_RETRIES, "
            "SCIELO_RETRY_DELAY, SCIELO_MAX_RETRY_WAIT, SCIELO_OUT_DIR, "
            "SCIELO_QUERY_OUTPUT_NAME, SCIELO_METADATA_CONFIG."
        ),
    )
    parser.add_argument(
        "--interface-lang",
        choices=("es", "en", "pt"),
        default=None,
        help="SciELO search interface language. Default: es.",
    )
    parser.add_argument(
        "--collection",
        help=(
            "SciELO collection code, for example scl, col, mex. "
            "Maps to the `in:` search index."
        ),
    )
    parser.add_argument(
        "--document-type",
        help="Document type to append as `type:...` in the SciELO query.",
    )
    parser.add_argument(
        "--from-year",
        help="Lower publication year bound in YYYY format.",
    )
    parser.add_argument(
        "--to-year",
        help="Upper publication year bound in YYYY format.",
    )
    parser.add_argument(
        "--require-abstract",
        action="store_true",
        help=(
            "Keep only results that expose abstract availability. Default: true "
            "unless SCIELO_REQUIRE_ABSTRACT=false in the config file."
        ),
    )
    parser.add_argument(
        "--count",
        type=int,
        default=None,
        help=(
            f"Results per SciELO request. Default: {DEFAULT_COUNT}. "
            f"Hard cap used by this script: {RESULTS_PER_REQUEST_HARD_CAP}."
        ),
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=None,
        help=f"Maximum number of results to export. Default: {DEFAULT_MAX_RESULTS}.",
    )
    parser.add_argument(
        "--sampling-threshold",
        type=int,
        default=None,
        help=(
            "Recommended upper bound for max_results before warning about latency. "
            f"Default: {DEFAULT_RESULTS_THRESHOLD}. Can also be set as "
            "PRISMA_MAX_RESULTS_THRESHOLD in the config file."
        ),
    )
    parser.add_argument(
        "--quiet-progress",
        action="store_true",
        help="Hide per-page progress messages during download.",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=None,
        help=(
            f"Maximum retries for transient HTTP/network failures. Default: {DEFAULT_MAX_RETRIES}."
        ),
    )
    parser.add_argument(
        "--retry-delay",
        type=float,
        default=None,
        help=f"Initial retry delay in seconds. Default: {DEFAULT_RETRY_DELAY}.",
    )
    parser.add_argument(
        "--max-retry-wait",
        type=float,
        default=None,
        help=f"Maximum retry wait in seconds. Default: {DEFAULT_MAX_RETRY_WAIT}.",
    )
    parser.add_argument(
        "--out-dir",
        default=None,
        help=(
            "Run directory for exported files. Search artifacts are written under "
            "`search/scielo/` and screening artifacts under `screening/`."
        ),
    )
    parser.add_argument(
        "--query-output-name",
        default=None,
        help="Filename used to persist the effective query. Default: query.txt.",
    )
    parser.add_argument(
        "--metadata-config",
        default=None,
        help=(
            "Path to the YAML file that defines screening/extraction metadata columns. "
            f"Default: {DEFAULT_METADATA_CONFIG_PATH}."
        ),
    )

    args = parser.parse_args()
    config_file = Path(args.config_file).expanduser().resolve() if args.config_file else None
    env_config = load_env_config(config_file)
    query = resolve_scielo_query(args.query, args.query_file, args.html_file, env_config, config_file)
    html_file = resolve_html_file(args.html_file, env_config, config_file)

    interface_lang = resolve_choice(
        args.interface_lang,
        env_config.get("SCIELO_INTERFACE_LANG"),
        "es",
        {"es", "en", "pt"},
        "SciELO interface language",
    )
    collection = resolve_str(args.collection, env_config.get("SCIELO_COLLECTION"))
    document_type = resolve_str(args.document_type, env_config.get("SCIELO_DOCUMENT_TYPE"))
    from_year = resolve_str(args.from_year, env_config.get("SCIELO_FROM_YEAR"))
    to_year = resolve_str(args.to_year, env_config.get("SCIELO_TO_YEAR"))
    require_abstract = resolve_bool_flag(
        args.require_abstract,
        env_config.get("SCIELO_REQUIRE_ABSTRACT"),
        True,
    )
    count = min(
        max(resolve_int(args.count, env_config.get("SCIELO_COUNT"), DEFAULT_COUNT), 1),
        RESULTS_PER_REQUEST_HARD_CAP,
    )
    max_results = max(
        resolve_int(args.max_results, env_config.get("SCIELO_MAX_RESULTS"), DEFAULT_MAX_RESULTS),
        1,
    )
    sampling_threshold = max(
        resolve_int(
            args.sampling_threshold,
            env_config.get("PRISMA_MAX_RESULTS_THRESHOLD"),
            DEFAULT_RESULTS_THRESHOLD,
        ),
        1,
    )
    max_retries = max(
        resolve_int(args.max_retries, env_config.get("SCIELO_MAX_RETRIES"), DEFAULT_MAX_RETRIES),
        0,
    )
    retry_delay = max(
        resolve_float(
            args.retry_delay,
            env_config.get("SCIELO_RETRY_DELAY"),
            DEFAULT_RETRY_DELAY,
        ),
        0.1,
    )
    max_retry_wait = max(
        resolve_float(
            args.max_retry_wait,
            env_config.get("SCIELO_MAX_RETRY_WAIT"),
            DEFAULT_MAX_RETRY_WAIT,
        ),
        0.1,
    )
    out_dir = resolve_workspace_path(
        resolve_str(args.out_dir, env_config.get("SCIELO_OUT_DIR"), "outputs/scielo-search"),
        config_file,
        env_config,
    )
    query_output_name = resolve_str(
        args.query_output_name,
        env_config.get("SCIELO_QUERY_OUTPUT_NAME"),
        "query.txt",
    )
    metadata_config_raw = resolve_str(args.metadata_config, env_config.get("SCIELO_METADATA_CONFIG"))
    metadata_config_file = (
        resolve_workspace_path(metadata_config_raw, config_file, env_config)
        if metadata_config_raw
        else DEFAULT_METADATA_CONFIG_PATH
    )

    return SearchConfig(
        query=query,
        html_file=html_file,
        interface_lang=interface_lang,
        collection=collection,
        document_type=document_type,
        from_year=from_year,
        to_year=to_year,
        require_abstract=require_abstract,
        count=count,
        max_results=max_results,
        sampling_threshold=sampling_threshold,
        quiet_progress=args.quiet_progress,
        max_retries=max_retries,
        retry_delay=retry_delay,
        max_retry_wait=max_retry_wait,
        out_dir=out_dir,
        query_output_name=query_output_name,
        config_file=config_file,
        metadata_config_file=metadata_config_file,
    )


def resolve_scielo_query(
    cli_query: str | None,
    query_file: str | None,
    html_file: str | None,
    env_config: dict[str, str],
    config_file: Path | None,
) -> str:
    config_query_file = env_config.get("SCIELO_QUERY_FILE", "").strip() or None
    effective_query_file = query_file or config_query_file
    html_mode = bool(html_file or env_config.get("SCIELO_HTML_FILE", "").strip())

    if cli_query and query_file:
        raise ValueError("Use either a positional query or --query-file, not both.")
    if cli_query and config_query_file:
        raise ValueError(
            "Use either a positional query or SCIELO_QUERY_FILE/--query-file, not both."
        )
    if effective_query_file:
        query_path = (
            Path(effective_query_file).expanduser().resolve()
            if query_file
            else resolve_workspace_path(effective_query_file, config_file, env_config)
        )
        return query_path.read_text(encoding="utf-8").strip()
    if cli_query:
        return cli_query.strip()
    if html_mode:
        return "Consulta no embebida; ver HTML manual de SciELO."
    raise ValueError(
        "A query is required. Provide it directly or with --query-file/SCIELO_QUERY_FILE, "
        "or use --html-file/SCIELO_HTML_FILE with a saved SciELO results page."
    )


def resolve_html_file(
    cli_value: str | None,
    env_config: dict[str, str],
    config_file: Path | None,
) -> Path | None:
    raw = resolve_str(cli_value, env_config.get("SCIELO_HTML_FILE"))
    if not raw:
        return None
    if cli_value:
        return Path(cli_value).expanduser().resolve()
    return resolve_workspace_path(raw, config_file, env_config)


def validate_year(value: str | None) -> None:
    if value is None:
        return
    if not re.fullmatch(r"\d{4}", value):
        raise ValueError(f"Invalid year: {value!r}. Expected YYYY.")


def search_output_dir(run_dir: Path) -> Path:
    return run_dir / "search" / "scielo"


def screening_output_dir(run_dir: Path) -> Path:
    return run_dir / "screening"


def build_query(config: SearchConfig) -> str:
    query = config.query.strip()
    extra_terms: list[str] = []
    if config.collection:
        extra_terms.append(f"in:{config.collection}")
    if config.document_type:
        extra_terms.append(f"type:{config.document_type}")
    year_clause = build_year_clause(config.from_year, config.to_year)
    if year_clause:
        extra_terms.append(year_clause)
    if extra_terms:
        query = f"({query}) and " + " and ".join(extra_terms)
    return query


def build_year_clause(from_year: str | None, to_year: str | None) -> str | None:
    if not from_year and not to_year:
        return None
    if from_year and to_year and from_year == to_year:
        return f"publication_year:{from_year}"

    try:
        start = int(from_year) if from_year else None
        end = int(to_year) if to_year else None
    except ValueError:
        return None

    if start is None and end is not None:
        return f"publication_year:{end}"
    if end is None and start is not None:
        return f"publication_year:{start}"
    if start is None or end is None:
        return None
    if end < start:
        start, end = end, start

    years = [str(year) for year in range(start, end + 1)]
    if len(years) == 1:
        return f"publication_year:{years[0]}"
    if len(years) <= 10:
        return "(" + " or ".join(f"publication_year:{year}" for year in years) + ")"
    return None


def build_params(config: SearchConfig, effective_query: str, offset: int) -> dict[str, str]:
    return {
        "output": "site",
        "lang": config.interface_lang,
        "format": "summary",
        "count": str(config.count),
        "from": str(offset),
        "page": "1",
        "q": effective_query,
    }


def fetch_results(config: SearchConfig) -> tuple[list[dict[str, Any]], dict[str, Any], str]:
    if config.html_file is not None:
        html_text = config.html_file.read_text(encoding="utf-8", errors="ignore")
        results = parse_search_results(html_text)[: config.max_results]
        meta = {
            "count": parse_total_results(html_text),
            "pages_fetched": 1,
            "effective_query": config.query,
            "request_count": 0,
            "input_mode": "html_snapshot",
            "html_file": str(config.html_file),
        }
        return results, meta, config.query

    effective_query = build_query(config)
    results: list[dict[str, Any]] = []
    total_reported: int | None = None
    offset = 0
    page_number = 0
    fetched_html_pages = 0

    while len(results) < config.max_results:
        url = f"{SEARCH_URL}?{parse.urlencode(build_params(config, effective_query, offset))}"
        html_text = fetch_text_with_retries(url, config)
        fetched_html_pages += 1
        page_number += 1
        if total_reported is None:
            total_reported = parse_total_results(html_text)

        page_results = parse_search_results(html_text, start_index=len(results))
        if not page_results:
            break

        remaining = config.max_results - len(results)
        results.extend(page_results[:remaining])

        if not config.quiet_progress:
            total_hint = total_reported if total_reported is not None else "No reportado"
            print(
                f"[SciELO] page {page_number} fetched, accumulated {len(results)} "
                f"records (SciELO reports about {total_hint}).",
                flush=True,
            )

        if len(page_results) < config.count:
            break
        offset += config.count

    meta = {
        "count": total_reported,
        "pages_fetched": fetched_html_pages,
        "effective_query": effective_query,
        "request_count": config.count,
        "input_mode": "live_http",
    }
    return results, meta, effective_query


def fetch_text_with_retries(url: str, config: SearchConfig) -> str:
    attempt = 0
    delay = config.retry_delay

    while True:
        request_headers = {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            ),
            "Accept-Language": f"{config.interface_lang},en;q=0.8",
        }
        req = request.Request(url, headers=request_headers)
        try:
            with request.urlopen(req) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                return response.read().decode(charset, errors="ignore")
        except error.HTTPError as exc:
            if exc.code not in (403, 429, 500, 502, 503, 504) or attempt >= config.max_retries:
                raise
            sleep_seconds = min(delay, config.max_retry_wait)
            print(
                f"[SciELO] transient HTTP {exc.code}; retrying in {sleep_seconds:.1f}s "
                f"(attempt {attempt + 1} of {config.max_retries}).",
                flush=True,
            )
            time.sleep(sleep_seconds)
            attempt += 1
            delay *= 2
        except error.URLError:
            if attempt >= config.max_retries:
                raise
            print(
                f"[SciELO] transient network error; retrying in {delay:.1f}s "
                f"(attempt {attempt + 1} of {config.max_retries}).",
                flush=True,
            )
            time.sleep(delay)
            attempt += 1
            delay *= 2


def parse_total_results(html_text: str) -> int | None:
    text = collapse_whitespace(strip_tags(html_text))
    patterns = [
        r"P[aá]gina\s+\d+\s+de\s+(\d+)",
        r"Page\s+\d+\s+of\s+(\d+)",
        r"P[aá]gina\s+\d+\s+de\s+aproximadamente\s+(\d+)",
        r"All references \(max\.\s*(\d+)\)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                return None
    return None


def parse_search_results(html_text: str, start_index: int = 0) -> list[dict[str, Any]]:
    anchors = extract_anchors(html_text)
    title_anchors = [anchor for anchor in anchors if is_article_title_anchor(anchor)]
    if not title_anchors:
        return []

    normalized: list[dict[str, Any]] = []
    for index, anchor in enumerate(title_anchors):
        start = anchor["start"]
        end = (
            title_anchors[index + 1]["start"]
            if index + 1 < len(title_anchors)
            else len(html_text)
        )
        block_html = html_text[start:end]
        parsed = parse_result_block(block_html, anchor, start_index + index + 1)
        if parsed:
            normalized.append(parsed)
    return normalized


def extract_anchors(html_text: str) -> list[dict[str, Any]]:
    anchors: list[dict[str, Any]] = []
    pattern = re.compile(
        r"<a\b(?P<attrs>[^>]*)href=(?P<quote>['\"])(?P<href>.*?)(?P=quote)(?P<rest>[^>]*)>"
        r"(?P<text>.*?)</a>",
        flags=re.IGNORECASE | re.DOTALL,
    )
    for match in pattern.finditer(html_text):
        text = collapse_whitespace(strip_tags(match.group("text")))
        if not text:
            continue
        href = normalize_href(match.group("href"))
        anchors.append(
            {
                "href": href,
                "text": text,
                "start": match.start(),
                "end": match.end(),
            }
        )
    return anchors


def normalize_href(href: str) -> str:
    href = unescape(href).strip()
    if href.startswith("//"):
        return "https:" + href
    if href.startswith("/"):
        return parse.urljoin(SEARCH_URL, href)
    return href


def is_article_title_anchor(anchor: dict[str, Any]) -> bool:
    href = anchor["href"].lower()
    text = anchor["text"].strip()
    normalized_text = text.lower()
    if len(text) < 15:
        return False
    if normalized_text in GENERIC_LINK_TEXTS:
        return False
    if normalized_text.startswith(("abstract", "resumen", "resumo", "text", "texto", "pdf")):
        return False
    if any(token in normalized_text for token in ("scielo analytics", "metrics", "altmetric")):
        return False
    if not any(
        token in href
        for token in ("/article/", "/j/", "sci_arttext", "pid=", "/a/")
    ):
        return False
    return True


def parse_result_block(
    block_html: str,
    anchor: dict[str, Any],
    position: int,
) -> dict[str, Any] | None:
    block_anchors = extract_anchors(block_html)
    title = anchor["text"].strip()
    title_href = anchor["href"]
    clean_text = collapse_whitespace(strip_tags(block_html))
    lines = text_lines(block_html)

    abstract_links = [
        item["href"]
        for item in block_anchors
        if item["text"].lower().startswith(("abstract", "resumen", "resumo"))
    ]
    text_links = [
        item["href"]
        for item in block_anchors
        if item["text"].lower().startswith(("text", "texto"))
    ]
    pdf_links = [item["href"] for item in block_anchors if item["text"].lower() == "pdf"]

    authors_line, journal_line = infer_authors_and_journal(lines, title)
    year = infer_year(clean_text)
    language = infer_language(block_html, abstract_links, text_links, pdf_links)
    primary_url = next((url for url in text_links + pdf_links + abstract_links if url), title_href)

    return {
        "code": f"SC{position:03d}",
        "source": "SciELO",
        "source_id": title_href,
        "title": title,
        "authors": authors_line,
        "year": year,
        "first_affiliation": "",
        "country_code": "",
        "country": "",
        "publication_date": "",
        "doi": infer_doi(clean_text, block_anchors),
        "abstract": "",
        "abstract_url": abstract_links[0] if abstract_links else "",
        "journal": journal_line,
        "journal_type": "",
        "language": language,
        "document_type": "article",
        "is_oa": bool(text_links or pdf_links or abstract_links or title_href),
        "oa_status": "gold" if (text_links or pdf_links) else "unknown",
        "source_is_in_doaj": None,
        "cited_by_count": 0,
        "primary_url": primary_url,
        "pdf_url": pdf_links[0] if pdf_links else "",
        "openalex_url": "",
        "scielo_url": title_href,
        "text_url": text_links[0] if text_links else "",
        "fulltext_accessible": "Por verificar" if (text_links or pdf_links or abstract_links) else "No",
        "abstract_available": bool(abstract_links),
    }


def infer_authors_and_journal(lines: list[str], title: str) -> tuple[str, str]:
    filtered = [line for line in lines if line and line != title]
    authors = ""
    journal = ""
    for line in filtered:
        lower = line.lower()
        if not authors and (" ; " in line or "; " in line or re.search(r"[A-Za-zÁÉÍÓÚáéíóúÑñ]+,\s", line)):
            if "abstract:" in lower or "resumen:" in lower or "resumo:" in lower:
                continue
            authors = line.rstrip(" .")
            continue
        if authors and not journal:
            if lower.startswith(("abstract:", "resumen:", "resumo:", "text:", "texto:", "pdf:")):
                continue
            if any(token in lower for token in ("scielo analytics", "metrics", "altmetric", "dimensions")):
                continue
            if re.search(r"\b(19|20)\d{2}\b", line):
                journal = line.split("20")[0].strip(" ,.;")
                if journal:
                    break
            if len(line) > 3:
                journal = line.rstrip(" .")
                break
    return authors, journal


def infer_year(text: str) -> str:
    match = re.search(r"\b(19|20)\d{2}\b", text)
    return match.group(0) if match else ""


def infer_doi(text: str, anchors: list[dict[str, Any]]) -> str:
    match = re.search(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", text, flags=re.IGNORECASE)
    if match:
        return match.group(0)
    for anchor in anchors:
        href = anchor["href"]
        doi_match = re.search(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", href, flags=re.IGNORECASE)
        if doi_match:
            return doi_match.group(0)
    return ""


def infer_language(
    block_html: str,
    abstract_links: list[str],
    text_links: list[str],
    pdf_links: list[str],
) -> str:
    found = extract_badge_languages(block_html)
    if found:
        return ",".join(found)
    if abstract_links or text_links or pdf_links:
        return ""
    return ""


def extract_badge_languages(block_html: str) -> list[str]:
    tokens: list[str] = []
    for token in re.findall(r"\b(Es|En|Pt)\b", collapse_whitespace(strip_tags(block_html))):
        if token not in tokens:
            tokens.append(token)
    return tokens


def strip_tags(html_text: str) -> str:
    return re.sub(r"<[^>]+>", " ", html_text)


def collapse_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", unescape(text)).strip()


def text_lines(html_text: str) -> list[str]:
    lines: list[str] = []
    for raw_line in re.split(r"</?(?:br|p|div|li|tr|h\d)[^>]*>", html_text, flags=re.IGNORECASE):
        clean = collapse_whitespace(strip_tags(raw_line))
        if clean:
            lines.append(clean)
    if not lines:
        merged = collapse_whitespace(strip_tags(html_text))
        if merged:
            lines.append(merged)
    return dedupe_preserve_order(lines)


def dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def filter_raw_results(raw_results: list[dict[str, Any]], config: SearchConfig) -> list[dict[str, Any]]:
    filtered = raw_results
    if config.require_abstract:
        filtered = [item for item in filtered if item.get("abstract_available")]
    return filtered


def post_search_filter_descriptions(config: SearchConfig) -> list[str]:
    descriptions: list[str] = []
    if config.require_abstract:
        descriptions.append(
            "Se excluyen localmente los registros sin indicador visible de resumen en SciELO."
        )
    return descriptions


def compute_sampling_warnings(config: SearchConfig, meta: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    if config.max_results > config.sampling_threshold:
        warnings.append(
            "max_results supera el umbral operativo configurado y puede introducir "
            "latencia o un subconjunto demasiado grande para cribado inicial."
        )

    count = meta.get("count")
    if not isinstance(count, int):
        return warnings

    if count > 1000:
        warnings.append(
            "SciELO reporta más de 1000 resultados estimados. Corresponde refinar "
            "la query antes del cribado inicial."
        )
    elif count > config.max_results:
        warnings.append(
            "SciELO reporta más resultados que max_results. Si el usuario no aprueba "
            "trabajar con una muestra acotada, corresponde refinar la query."
        )

    return warnings


def build_search_log_text(
    config: SearchConfig,
    meta: dict[str, Any],
    result_count: int,
    snapshot: dict[str, Any],
    metadata_columns: dict[str, list[str]],
    warnings: list[str],
    filtered_out_count: int,
) -> str:
    run_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    filters = {
        "interface_lang": config.interface_lang,
        "collection": config.collection,
        "document_type": config.document_type,
        "from_year": config.from_year,
        "to_year": config.to_year,
        "input_mode": meta.get("input_mode", "live_http"),
        "html_file": meta.get("html_file"),
        "require_abstract": config.require_abstract,
        "sampling_threshold": config.sampling_threshold,
        "max_retries": config.max_retries,
        "retry_delay": config.retry_delay,
        "max_retry_wait": config.max_retry_wait,
        "config_file": str(config.config_file) if config.config_file else None,
        "metadata_config_file": str(config.metadata_config_file),
        "screening_columns": metadata_columns.get("screening_columns", []),
    }
    local_post_filters = post_search_filter_descriptions(config)

    lines = [
        "# Bitacora de busqueda SciELO",
        "",
        f"- Fecha de ejecucion: `{run_at}`",
        f"- Fuente: `SciELO Search`",
        f"- Consulta visible: `{config.query}`",
        f"- Consulta efectiva enviada: `{meta.get('effective_query', config.query)}`",
        f"- Idioma de interfaz: `{config.interface_lang}`",
        f"- Resultados por solicitud: `{config.count}`",
        f"- Requerir abstract: `{config.require_abstract}`",
        f"- Umbral operativo de muestra: `{config.sampling_threshold}`",
        f"- Filtros: `{json.dumps(filters, ensure_ascii=True)}`",
        f"- Resultados estimados por SciELO: `{meta.get('count', 'No reportado')}`",
        f"- Paginas HTML recuperadas: `{meta.get('pages_fetched', 'No reportado')}`",
        f"- Registros recuperados por esta ejecucion antes de filtros locales: `{result_count + filtered_out_count}`",
        f"- Registros excluidos por reglas locales posteriores a la descarga: `{filtered_out_count}`",
        f"- Resultados exportados en esta ejecucion: `{result_count}`",
        "",
        "## Trazabilidad del filtrado local",
        "",
        "",
        "## Alertas de muestreo y volumen",
        "",
        render_warning_lines(warnings),
        "",
        "## Resumen rapido de calidad del conjunto",
        "",
        f"- Registros con DOI: `{snapshot['with_doi']}` de `{snapshot['total_results']}`",
        f"- Registros con abstract disponible en el resultado: `{snapshot['with_abstract']}` de `{snapshot['total_results']}`",
        f"- Registros con revista o fuente identificada: `{snapshot['with_journal']}` de `{snapshot['total_results']}`",
        f"- Registros tipo article: `{snapshot['articles']}` de `{snapshot['total_results']}`",
        f"- Registros open access: `{snapshot['open_access_items']}` de `{snapshot['total_results']}`",
        "",
        "### Idiomas detectados",
        "",
        render_count_lines(snapshot["languages"]),
        "",
        "### Tipos documentales detectados",
        "",
        render_count_lines(snapshot["work_types"]),
        "",
        "## Nota metodologica",
        "",
        "Esta bitacora documenta una recuperacion automatizada inicial desde el buscador web de SciELO.",
        "Cuando la fuente activa un challenge JavaScript, el script puede trabajar en modo `html_snapshot`",
        "a partir de una pagina de resultados guardada manualmente por el estudiante.",
        "La inclusion final de estudios debe realizarse mediante cribado humano con criterios explicitos.",
        "Si SciELO reporta mas resultados que `max_results`, el recorte se interpreta como una",
        "muestra operativa priorizada por el orden del buscador, no como una seleccion metodologica final.",
        "El parser actual se apoya en la estructura HTML visible de SciELO Search; conviene validar una",
        "muestra de resultados cuando la fuente cambie su interfaz.",
        "",
    ]
    insert_at = lines.index("## Alertas de muestreo y volumen") - 1
    if local_post_filters:
        lines[insert_at:insert_at] = [f"- {item}" for item in local_post_filters]
    else:
        lines[insert_at:insert_at] = ["- `No se aplicaron filtros locales posteriores a la descarga.`"]
    return "\n".join(lines)


def write_search_log(
    path: Path,
    config: SearchConfig,
    meta: dict[str, Any],
    result_count: int,
    snapshot: dict[str, Any],
    metadata_columns: dict[str, list[str]],
    warnings: list[str],
    filtered_out_count: int,
) -> str:
    text = build_search_log_text(
        config,
        meta,
        result_count,
        snapshot,
        metadata_columns,
        warnings,
        filtered_out_count,
    )
    path.write_text(text, encoding="utf-8")
    return text


def main() -> int:
    try:
        config = parse_args()
        validate_year(config.from_year)
        validate_year(config.to_year)
    except ValueError as exc:
        print(f"Invalid configuration: {exc}", file=sys.stderr)
        return 2

    ensure_dir(config.out_dir)
    search_dir = search_output_dir(config.out_dir)
    screening_dir = screening_output_dir(config.out_dir)
    ensure_dir(search_dir)
    ensure_dir(screening_dir)

    try:
        metadata_columns = load_metadata_config(config.metadata_config_file)
    except Exception as exc:  # noqa: BLE001
        print(f"Metadata config failed: {exc}", file=sys.stderr)
        return 2

    try:
        raw_results, meta, effective_query = fetch_results(config)
    except Exception as exc:  # noqa: BLE001
        print(f"SciELO request failed: {exc}", file=sys.stderr)
        return 1

    filtered_raw_results = filter_raw_results(raw_results, config)
    filtered_out_count = len(raw_results) - len(filtered_raw_results)
    snapshot = compute_quality_snapshot(filtered_raw_results)
    sampling_warnings = compute_sampling_warnings(config, meta)

    summary = {
        "source": "SciELO",
        "query": config.query,
        "effective_query": effective_query,
        "config_file": str(config.config_file) if config.config_file else None,
        "interface_lang": config.interface_lang,
        "collection": config.collection,
        "document_type": config.document_type,
        "from_year": config.from_year,
        "to_year": config.to_year,
        "count": config.count,
        "max_results": config.max_results,
        "sampling_threshold": config.sampling_threshold,
        "input_mode": meta.get("input_mode", "live_http"),
        "html_file": str(config.html_file) if config.html_file else None,
        "require_abstract": config.require_abstract,
        "fetched_results_before_post_filters": len(raw_results),
        "exported_results": len(filtered_raw_results),
        "filtered_out_after_fetch": filtered_out_count,
        "scielo_meta_count": meta.get("count"),
        "pages_fetched": meta.get("pages_fetched"),
        "sampling_warnings": sampling_warnings,
        "snapshot": snapshot,
        "metadata_config_file": str(config.metadata_config_file),
        "screening_columns": metadata_columns.get("screening_columns", []),
        "extraction_columns": metadata_columns.get("extraction_columns", []),
    }

    write_query_file(search_dir / config.query_output_name, effective_query)
    write_json(search_dir / "raw_results.json", raw_results)
    write_json(search_dir / "normalized_results.json", filtered_raw_results)
    write_json(search_dir / "summary.json", summary)
    write_csv(search_dir / "normalized_results.csv", filtered_raw_results)
    write_screening_matrix(
        screening_dir / "screening_matrix.md",
        filtered_raw_results,
        metadata_columns.get("screening_columns", []),
    )
    write_screening_matrix_csv(
        screening_dir / "screening_matrix.csv",
        filtered_raw_results,
        metadata_columns.get("screening_columns", []),
    )
    search_log_text = write_search_log(
        search_dir / "search_log.md",
        config,
        meta,
        len(filtered_raw_results),
        snapshot,
        metadata_columns,
        sampling_warnings,
        filtered_out_count,
    )

    print(search_log_text)
    refresh_run_outputs(config.out_dir)
    print(f"Archivos exportados en: {config.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
