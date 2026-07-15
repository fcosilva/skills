#!/usr/bin/env python3
"""Search PubMed through NCBI E-utilities and export normalized PRISMA results."""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import error, parse, request

from metadata_config import DEFAULT_METADATA_CONFIG_PATH, load_metadata_config
from openalex_search import (
    compute_quality_snapshot,
    ensure_dir,
    load_env_config,
    render_count_lines,
    render_warning_lines,
    resolve_bool_flag,
    resolve_float,
    resolve_int,
    resolve_str,
    resolve_workspace_path,
    write_csv,
    write_json,
    write_query_file,
    write_screening_matrix,
    write_screening_matrix_csv,
)
from run_outputs import refresh_run_outputs


EUTILS_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
DEFAULT_RETMAX = 100
DEFAULT_MAX_RESULTS = 100
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_DELAY = 1.0
DEFAULT_MAX_RETRY_WAIT = 30.0
DEFAULT_RESULTS_THRESHOLD = 500


@dataclass
class SearchConfig:
    conceptual_query: str
    query: str
    from_year: str | None
    to_year: str | None
    require_abstract: bool
    retmax: int
    max_results: int
    sampling_threshold: int
    quiet_progress: bool
    max_retries: int
    retry_delay: float
    max_retry_wait: float
    api_key: str | None
    email: str | None
    out_dir: Path
    query_output_name: str
    config_file: Path | None
    metadata_config_file: Path


def parse_args() -> SearchConfig:
    parser = argparse.ArgumentParser(description="Run a PubMed search and export normalized results.")
    parser.add_argument("query", nargs="?", help="PubMed query. Optional when --query-file is used.")
    parser.add_argument("--query-file", help="Path to a text file containing the PubMed query.")
    parser.add_argument(
        "--config-file",
        help=(
            "Path to env-style config. Supported keys: PUBMED_API_KEY, PUBMED_EMAIL, "
            "PUBMED_QUERY_FILE, PUBMED_FROM_YEAR, PUBMED_TO_YEAR, PUBMED_REQUIRE_ABSTRACT, "
            "PUBMED_RETMAX, PUBMED_MAX_RESULTS, PRISMA_MAX_RESULTS_THRESHOLD, "
            "PUBMED_MAX_RETRIES, PUBMED_RETRY_DELAY, PUBMED_MAX_RETRY_WAIT, "
            "PUBMED_OUT_DIR, PUBMED_QUERY_OUTPUT_NAME, PUBMED_METADATA_CONFIG."
        ),
    )
    parser.add_argument("--api-key", help="NCBI API key. Optional.")
    parser.add_argument("--email", help="Contact email for NCBI E-utilities. Recommended.")
    parser.add_argument("--from-year", help="Lower publication year bound in YYYY format.")
    parser.add_argument("--to-year", help="Upper publication year bound in YYYY format.")
    parser.add_argument("--require-abstract", action="store_true")
    parser.add_argument("--retmax", type=int)
    parser.add_argument("--max-results", type=int)
    parser.add_argument("--sampling-threshold", type=int)
    parser.add_argument("--quiet-progress", action="store_true")
    parser.add_argument("--max-retries", type=int)
    parser.add_argument("--retry-delay", type=float)
    parser.add_argument("--max-retry-wait", type=float)
    parser.add_argument("--out-dir")
    parser.add_argument("--query-output-name")
    parser.add_argument("--metadata-config")
    args = parser.parse_args()

    config_file = Path(args.config_file).expanduser().resolve() if args.config_file else None
    env_config = load_env_config(config_file)
    require_abstract = resolve_bool_flag(args.require_abstract, env_config.get("PUBMED_REQUIRE_ABSTRACT"), True)
    conceptual_query = resolve_pubmed_query(args.query, args.query_file, env_config, config_file)
    query = add_year_filters(add_abstract_filter(conceptual_query, require_abstract), args, env_config)
    retmax = max(resolve_int(args.retmax, env_config.get("PUBMED_RETMAX"), DEFAULT_RETMAX), 1)
    max_results = max(resolve_int(args.max_results, env_config.get("PUBMED_MAX_RESULTS"), DEFAULT_MAX_RESULTS), 1)
    sampling_threshold = max(
        resolve_int(args.sampling_threshold, env_config.get("PRISMA_MAX_RESULTS_THRESHOLD"), DEFAULT_RESULTS_THRESHOLD),
        1,
    )
    max_retries = max(resolve_int(args.max_retries, env_config.get("PUBMED_MAX_RETRIES"), DEFAULT_MAX_RETRIES), 0)
    retry_delay = max(resolve_float(args.retry_delay, env_config.get("PUBMED_RETRY_DELAY"), DEFAULT_RETRY_DELAY), 0.1)
    max_retry_wait = max(
        resolve_float(args.max_retry_wait, env_config.get("PUBMED_MAX_RETRY_WAIT"), DEFAULT_MAX_RETRY_WAIT),
        0.1,
    )
    out_dir = resolve_workspace_path(
        resolve_str(args.out_dir, env_config.get("PUBMED_OUT_DIR"), "outputs/pubmed-search"),
        config_file,
        env_config,
    )
    metadata_config_raw = resolve_str(args.metadata_config, env_config.get("PUBMED_METADATA_CONFIG"))
    metadata_config_file = (
        resolve_workspace_path(metadata_config_raw, config_file, env_config)
        if metadata_config_raw
        else DEFAULT_METADATA_CONFIG_PATH
    )
    return SearchConfig(
        conceptual_query=conceptual_query,
        query=query,
        from_year=resolve_str(args.from_year, env_config.get("PUBMED_FROM_YEAR")),
        to_year=resolve_str(args.to_year, env_config.get("PUBMED_TO_YEAR")),
        require_abstract=require_abstract,
        retmax=retmax,
        max_results=max_results,
        sampling_threshold=sampling_threshold,
        quiet_progress=args.quiet_progress,
        max_retries=max_retries,
        retry_delay=retry_delay,
        max_retry_wait=max_retry_wait,
        api_key=resolve_str(args.api_key, env_config.get("PUBMED_API_KEY")),
        email=resolve_str(args.email, env_config.get("PUBMED_EMAIL")),
        out_dir=out_dir,
        query_output_name=resolve_str(args.query_output_name, env_config.get("PUBMED_QUERY_OUTPUT_NAME"), "query.txt"),
        config_file=config_file,
        metadata_config_file=metadata_config_file,
    )


def resolve_pubmed_query(
    cli_query: str | None,
    query_file: str | None,
    env_config: dict[str, str],
    config_file: Path | None,
) -> str:
    config_query_file = env_config.get("PUBMED_QUERY_FILE", "").strip() or None
    effective_query_file = query_file or config_query_file
    if cli_query and effective_query_file:
        raise ValueError("Use either a positional query or PUBMED_QUERY_FILE/--query-file, not both.")
    if effective_query_file:
        query_path = (
            Path(effective_query_file).expanduser().resolve()
            if query_file
            else resolve_workspace_path(effective_query_file, config_file, env_config)
        )
        return query_path.read_text(encoding="utf-8").strip()
    if cli_query:
        return cli_query.strip()
    raise ValueError("A PubMed query is required.")


def add_year_filters(query: str, args: argparse.Namespace, env_config: dict[str, str]) -> str:
    from_year = resolve_str(args.from_year, env_config.get("PUBMED_FROM_YEAR"))
    to_year = resolve_str(args.to_year, env_config.get("PUBMED_TO_YEAR"))
    if not from_year and not to_year:
        return query
    if re.search(r"\b\d{4}\s*:\s*\d{4}\s*\[pdat\]", query, flags=re.I):
        return query
    start = from_year or "1800"
    end = to_year or "3000"
    return f"({query}) AND ({start}:{end}[pdat])"


def add_abstract_filter(query: str, require_abstract: bool) -> str:
    if not require_abstract:
        return query
    if "hasabstract" in query.casefold() or '"has abstract"[filter]' in query.casefold():
        return query
    return f"({query}) AND hasabstract"


def search_output_dir(run_dir: Path) -> Path:
    return run_dir / "search" / "pubmed"


def screening_output_dir(run_dir: Path) -> Path:
    return run_dir / "screening"


def eutils_params(config: SearchConfig, extra: dict[str, str]) -> str:
    params = dict(extra)
    params["tool"] = "prisma-ai-tutor"
    if config.email:
        params["email"] = config.email
    if config.api_key:
        params["api_key"] = config.api_key
    return parse.urlencode(params)


def fetch_results(config: SearchConfig) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    ids, count = esearch(config)
    rows: list[dict[str, Any]] = []
    for start in range(0, len(ids), config.retmax):
        chunk = ids[start : start + config.retmax]
        if not chunk:
            continue
        rows.extend(efetch(config, chunk))
        if not config.quiet_progress:
            print(f"[PubMed] fetched {len(rows)} records from {len(ids)} PMIDs.", flush=True)
    return rows, {"count": count, "ids": ids}


def esearch(config: SearchConfig) -> tuple[list[str], int]:
    params = eutils_params(
        config,
        {
            "db": "pubmed",
            "term": config.query,
            "retmode": "json",
            "retmax": str(config.max_results),
            "sort": "relevance",
        },
    )
    data = fetch_json_with_retries(f"{EUTILS_URL}/esearch.fcgi?{params}", config)
    result = data.get("esearchresult", {})
    return result.get("idlist", [])[: config.max_results], parse_int(result.get("count"))


def efetch(config: SearchConfig, ids: list[str]) -> list[dict[str, Any]]:
    params = eutils_params(
        config,
        {
            "db": "pubmed",
            "id": ",".join(ids),
            "retmode": "xml",
        },
    )
    xml_bytes = fetch_bytes_with_retries(f"{EUTILS_URL}/efetch.fcgi?{params}", config)
    root = ET.fromstring(xml_bytes)
    return [normalize_article(article, index + 1) for index, article in enumerate(root.findall(".//PubmedArticle"))]


def fetch_json_with_retries(url: str, config: SearchConfig) -> dict[str, Any]:
    return json.loads(fetch_bytes_with_retries(url, config).decode("utf-8"))


def fetch_bytes_with_retries(url: str, config: SearchConfig) -> bytes:
    attempt = 0
    delay = config.retry_delay
    while True:
        try:
            with request.urlopen(request.Request(url, headers={"User-Agent": "PRISMA-AI-Tutor/1.0"}), timeout=30) as resp:
                return resp.read()
        except error.HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt >= config.max_retries:
                raise
            time.sleep(min(delay, config.max_retry_wait))
            attempt += 1
            delay *= 2
        except error.URLError:
            if attempt >= config.max_retries:
                raise
            time.sleep(min(delay, config.max_retry_wait))
            attempt += 1
            delay *= 2


def normalize_article(article: ET.Element, position: int) -> dict[str, Any]:
    pmid = text(article.find(".//PMID"))
    title = iter_text(article.find(".//ArticleTitle"))
    abstract = " ".join(iter_text(node) for node in article.findall(".//Abstract/AbstractText") if iter_text(node))
    journal = iter_text(article.find(".//Journal/Title"))
    year = text(article.find(".//PubDate/Year")) or text(article.find(".//ArticleDate/Year"))
    doi = ""
    for node in article.findall(".//ArticleId"):
        if node.attrib.get("IdType") == "doi":
            doi = text(node)
            break
    publication_types = [iter_text(node) for node in article.findall(".//PublicationTypeList/PublicationType")]
    authors = "; ".join(format_author(node) for node in article.findall(".//AuthorList/Author") if format_author(node))
    country = iter_text(article.find(".//MedlineJournalInfo/Country"))
    return {
        "code": f"P{position:03d}",
        "source": "PubMed",
        "source_id": pmid,
        "title": title,
        "authors": authors,
        "year": year,
        "first_affiliation": first_affiliation(article),
        "country_code": "",
        "country": country,
        "publication_date": year,
        "doi": doi,
        "abstract": abstract,
        "journal": journal,
        "journal_type": "",
        "language": text(article.find(".//Language")),
        "document_type": normalize_document_type(publication_types),
        "is_oa": False,
        "oa_status": "",
        "source_is_in_doaj": False,
        "cited_by_count": 0,
        "primary_url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else "",
        "pdf_url": "",
        "openalex_url": "",
        "fulltext_accessible": "Por verificar" if pmid else "No",
        "abstract_available": bool(abstract),
    }


def text(node: ET.Element | None) -> str:
    return (node.text or "").strip() if node is not None else ""


def iter_text(node: ET.Element | None) -> str:
    return " ".join("".join(node.itertext()).split()) if node is not None else ""


def format_author(node: ET.Element) -> str:
    collective = text(node.find("CollectiveName"))
    if collective:
        return collective
    last = text(node.find("LastName"))
    initials = text(node.find("Initials"))
    return f"{last} {initials}".strip()


def first_affiliation(article: ET.Element) -> str:
    return iter_text(article.find(".//AuthorList/Author/AffiliationInfo/Affiliation"))


def normalize_document_type(types: list[str]) -> str:
    joined = "; ".join(types)
    lower = joined.casefold()
    if "journal article" in lower:
        return "article"
    if "review" in lower:
        return "review"
    if "editorial" in lower:
        return "editorial"
    return joined


def parse_int(value: Any) -> int:
    try:
        return int(str(value))
    except Exception:  # noqa: BLE001
        return 0


def filter_normalized_results(rows: list[dict[str, Any]], config: SearchConfig) -> list[dict[str, Any]]:
    if config.require_abstract:
        return [row for row in rows if row.get("abstract")]
    return rows


def sampling_warnings(config: SearchConfig, meta: dict[str, Any], exported_count: int) -> list[str]:
    warnings: list[str] = []
    if config.max_results > config.sampling_threshold:
        warnings.append("PUBMED_MAX_RESULTS supera el umbral operativo configurado.")
    if meta.get("count", 0) > config.max_results:
        warnings.append("PubMed reporta más resultados que los exportados; la muestra queda acotada por max_results.")
    if config.require_abstract and exported_count == 0:
        warnings.append("PUBMED_REQUIRE_ABSTRACT=true dejó la exportación vacía porque ningún registro recuperado traía abstract.")
    return warnings


def build_search_log_text(
    config: SearchConfig,
    meta: dict[str, Any],
    result_count: int,
    snapshot: dict[str, Any],
    metadata_columns: dict[str, list[str]],
    warnings: list[str],
) -> str:
    lines = [
        "# Bitacora de busqueda PubMed",
        "",
        f"- Fecha de ejecucion: `{datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')}`",
        "- Fuente: `PubMed / NCBI E-utilities`",
        f"- Consulta conceptual: `{config.conceptual_query}`",
        f"- Consulta efectiva ejecutada: `{config.query}`",
        f"- Requerir abstract: `{config.require_abstract}`",
        f"- Total reportado por PubMed: `{meta.get('count', 'No reportado')}`",
        f"- Resultados exportados: `{result_count}`",
        f"- Columnas de cribado: `{json.dumps(metadata_columns.get('screening_columns', []), ensure_ascii=True)}`",
        "",
        "## Alertas metodologicas",
        "",
        render_warning_lines(warnings),
        "",
        "## Resumen rapido de calidad del conjunto",
        "",
        f"- Registros con DOI: `{snapshot['with_doi']}` de `{snapshot['total_results']}`",
        f"- Registros con abstract: `{snapshot['with_abstract']}` de `{snapshot['total_results']}`",
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
    ]
    return "\n".join(lines)


def main() -> int:
    try:
        config = parse_args()
    except Exception as exc:  # noqa: BLE001
        print(f"Invalid PubMed configuration: {exc}", file=sys.stderr)
        return 2
    ensure_dir(config.out_dir)
    search_dir = search_output_dir(config.out_dir)
    screening_dir = screening_output_dir(config.out_dir)
    ensure_dir(search_dir)
    ensure_dir(screening_dir)
    # query.txt is a human-approved input artifact. Never replace it with
    # runtime filters, otherwise each rerun nests hasabstract/date clauses.
    write_query_file(search_dir / config.query_output_name, config.conceptual_query)
    write_query_file(search_dir / "effective_query.txt", config.query)
    try:
        metadata_columns = load_metadata_config(config.metadata_config_file)
        raw_results, meta = fetch_results(config)
    except Exception as exc:  # noqa: BLE001
        print(f"PubMed request failed: {exc}", file=sys.stderr)
        return 1
    filtered = filter_normalized_results(raw_results, config)
    snapshot = compute_quality_snapshot(filtered)
    warnings = sampling_warnings(config, meta, len(filtered))
    summary = {
        "source": "PubMed",
        "query": config.conceptual_query,
        "effective_query": config.query,
        "config_file": str(config.config_file) if config.config_file else None,
        "max_results": config.max_results,
        "count": meta.get("count"),
        "exported_results": len(filtered),
        "require_abstract": config.require_abstract,
        "sampling_warnings": warnings,
        "snapshot": snapshot,
        "metadata_config_file": str(config.metadata_config_file),
        "screening_columns": metadata_columns.get("screening_columns", []),
        "extraction_columns": metadata_columns.get("extraction_columns", []),
    }
    write_json(search_dir / "raw_results.json", raw_results)
    write_json(search_dir / "normalized_results.json", filtered)
    write_json(search_dir / "summary.json", summary)
    write_csv(search_dir / "normalized_results.csv", filtered)
    write_screening_matrix(screening_dir / "screening_matrix.md", filtered, metadata_columns.get("screening_columns", []))
    write_screening_matrix_csv(screening_dir / "screening_matrix.csv", filtered, metadata_columns.get("screening_columns", []))
    log_text = build_search_log_text(config, meta, len(filtered), snapshot, metadata_columns, warnings)
    (search_dir / "search_log.md").write_text(log_text, encoding="utf-8")
    print(log_text)
    refresh_run_outputs(config.out_dir)
    print(f"Archivos exportados en: {config.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
