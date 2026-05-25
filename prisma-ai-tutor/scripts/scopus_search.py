#!/usr/bin/env python3
"""Search Scopus and export normalized results for PRISMA-style workflows."""

from __future__ import annotations

import argparse
import json
import sys
import time
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


API_URL = "https://api.elsevier.com/content/search/scopus"
DEFAULT_COUNT = 25
DEFAULT_MAX_RESULTS = 100
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_DELAY = 2.0
DEFAULT_MAX_RETRY_WAIT = 60.0
DEFAULT_RESULTS_THRESHOLD = 500
MAX_COUNT = 200


@dataclass
class SearchConfig:
    query: str
    from_year: str | None
    to_year: str | None
    view: str
    require_abstract: bool
    count: int
    max_results: int
    sampling_threshold: int
    quiet_progress: bool
    max_retries: int
    retry_delay: float
    max_retry_wait: float
    api_key: str
    out_dir: Path
    query_output_name: str
    config_file: Path | None
    metadata_config_file: Path


def parse_args() -> SearchConfig:
    parser = argparse.ArgumentParser(
        description="Run a Scopus Search API query and export normalized screening results."
    )
    parser.add_argument("query", nargs="?", help="Scopus query. Optional when --query-file is used.")
    parser.add_argument("--query-file", help="Path to a text file containing the Scopus query.")
    parser.add_argument(
        "--config-file",
        help=(
            "Path to an env-style configuration file. Supported keys: SCOPUS_API_KEY, "
            "SCOPUS_QUERY_FILE, SCOPUS_FROM_YEAR, SCOPUS_TO_YEAR, SCOPUS_VIEW, "
            "SCOPUS_REQUIRE_ABSTRACT, SCOPUS_COUNT, SCOPUS_MAX_RESULTS, "
            "PRISMA_MAX_RESULTS_THRESHOLD, SCOPUS_MAX_RETRIES, SCOPUS_RETRY_DELAY, "
            "SCOPUS_MAX_RETRY_WAIT, SCOPUS_OUT_DIR, SCOPUS_QUERY_OUTPUT_NAME, "
            "SCOPUS_METADATA_CONFIG."
        ),
    )
    parser.add_argument("--api-key", help="Elsevier/Scopus API key.")
    parser.add_argument("--from-year", help="Lower publication year bound in YYYY format.")
    parser.add_argument("--to-year", help="Upper publication year bound in YYYY format.")
    parser.add_argument(
        "--view",
        default=None,
        help="Scopus Search API view. Default: STANDARD. COMPLETE may require extra entitlements.",
    )
    parser.add_argument(
        "--require-abstract",
        action="store_true",
        help=(
            "Keep only records with an abstract in the Search API response. "
            "Default: false unless SCOPUS_REQUIRE_ABSTRACT=true."
        ),
    )
    parser.add_argument("--count", type=int, default=None, help=f"Results per API page. Max: {MAX_COUNT}.")
    parser.add_argument("--max-results", type=int, default=None, help="Maximum results to export.")
    parser.add_argument("--sampling-threshold", type=int, default=None)
    parser.add_argument("--quiet-progress", action="store_true")
    parser.add_argument("--max-retries", type=int, default=None)
    parser.add_argument("--retry-delay", type=float, default=None)
    parser.add_argument("--max-retry-wait", type=float, default=None)
    parser.add_argument("--out-dir", default=None)
    parser.add_argument("--query-output-name", default=None)
    parser.add_argument("--metadata-config", default=None)

    args = parser.parse_args()
    config_file = Path(args.config_file).expanduser().resolve() if args.config_file else None
    env_config = load_env_config(config_file)
    query = add_year_filters(resolve_scopus_query(args.query, args.query_file, env_config, config_file), args, env_config)
    api_key = resolve_str(args.api_key, env_config.get("SCOPUS_API_KEY"))
    if not api_key:
        raise ValueError("Scopus API key missing. Provide --api-key or SCOPUS_API_KEY.")
    count = min(max(resolve_int(args.count, env_config.get("SCOPUS_COUNT"), DEFAULT_COUNT), 1), MAX_COUNT)
    max_results = max(resolve_int(args.max_results, env_config.get("SCOPUS_MAX_RESULTS"), DEFAULT_MAX_RESULTS), 1)
    sampling_threshold = max(
        resolve_int(args.sampling_threshold, env_config.get("PRISMA_MAX_RESULTS_THRESHOLD"), DEFAULT_RESULTS_THRESHOLD),
        1,
    )
    max_retries = max(resolve_int(args.max_retries, env_config.get("SCOPUS_MAX_RETRIES"), DEFAULT_MAX_RETRIES), 0)
    retry_delay = max(resolve_float(args.retry_delay, env_config.get("SCOPUS_RETRY_DELAY"), DEFAULT_RETRY_DELAY), 0.1)
    max_retry_wait = max(
        resolve_float(args.max_retry_wait, env_config.get("SCOPUS_MAX_RETRY_WAIT"), DEFAULT_MAX_RETRY_WAIT),
        0.1,
    )
    require_abstract = resolve_bool_flag(args.require_abstract, env_config.get("SCOPUS_REQUIRE_ABSTRACT"), False)
    out_dir = resolve_workspace_path(
        resolve_str(args.out_dir, env_config.get("SCOPUS_OUT_DIR"), "outputs/scopus-search"),
        config_file,
        env_config,
    )
    metadata_config_raw = resolve_str(args.metadata_config, env_config.get("SCOPUS_METADATA_CONFIG"))
    metadata_config_file = (
        resolve_workspace_path(metadata_config_raw, config_file, env_config)
        if metadata_config_raw
        else DEFAULT_METADATA_CONFIG_PATH
    )
    return SearchConfig(
        query=query,
        from_year=resolve_str(args.from_year, env_config.get("SCOPUS_FROM_YEAR")),
        to_year=resolve_str(args.to_year, env_config.get("SCOPUS_TO_YEAR")),
        view=resolve_str(args.view, env_config.get("SCOPUS_VIEW"), "STANDARD").upper(),
        require_abstract=require_abstract,
        count=count,
        max_results=max_results,
        sampling_threshold=sampling_threshold,
        quiet_progress=args.quiet_progress,
        max_retries=max_retries,
        retry_delay=retry_delay,
        max_retry_wait=max_retry_wait,
        api_key=api_key,
        out_dir=out_dir,
        query_output_name=resolve_str(args.query_output_name, env_config.get("SCOPUS_QUERY_OUTPUT_NAME"), "query.txt"),
        config_file=config_file,
        metadata_config_file=metadata_config_file,
    )


def resolve_scopus_query(
    cli_query: str | None,
    query_file: str | None,
    env_config: dict[str, str],
    config_file: Path | None,
) -> str:
    config_query_file = env_config.get("SCOPUS_QUERY_FILE", "").strip() or None
    effective_query_file = query_file or config_query_file
    if cli_query and effective_query_file:
        raise ValueError("Use either a positional query or SCOPUS_QUERY_FILE/--query-file, not both.")
    if effective_query_file:
        query_path = (
            Path(effective_query_file).expanduser().resolve()
            if query_file
            else resolve_workspace_path(effective_query_file, config_file, env_config)
        )
        return query_path.read_text(encoding="utf-8").strip()
    if cli_query:
        return cli_query.strip()
    raise ValueError("A Scopus query is required.")


def add_year_filters(query: str, args: argparse.Namespace, env_config: dict[str, str]) -> str:
    from_year = resolve_str(args.from_year, env_config.get("SCOPUS_FROM_YEAR"))
    to_year = resolve_str(args.to_year, env_config.get("SCOPUS_TO_YEAR"))
    filters: list[str] = []
    if from_year:
        filters.append(f"PUBYEAR > {int(from_year) - 1}")
    if to_year:
        filters.append(f"PUBYEAR < {int(to_year) + 1}")
    if not filters:
        return query
    return f"({query}) AND " + " AND ".join(filters)


def search_output_dir(run_dir: Path) -> Path:
    return run_dir / "search" / "scopus"


def screening_output_dir(run_dir: Path) -> Path:
    return run_dir / "screening"


def fetch_results(config: SearchConfig) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    results: list[dict[str, Any]] = []
    start = 0
    total_results: int | None = None
    while len(results) < config.max_results:
        page = fetch_page(config, start)
        search_results = page.get("search-results", {})
        if total_results is None:
            total_results = parse_int(search_results.get("opensearch:totalResults"))
        entries = search_results.get("entry") or []
        if not entries:
            break
        results.extend(entries[: max(config.max_results - len(results), 0)])
        if not config.quiet_progress:
            print(f"[Scopus] start {start}, received {len(entries)}, accumulated {len(results)}.", flush=True)
        start += len(entries)
        if len(entries) < config.count:
            break
        if total_results is not None and start >= total_results:
            break
    return results[: config.max_results], {"total_results": total_results, "exported_before_filters": len(results)}


def fetch_page(config: SearchConfig, start: int) -> dict[str, Any]:
    params = parse.urlencode(
        {
            "query": config.query,
            "count": str(config.count),
            "start": str(start),
            "view": config.view,
            "httpAccept": "application/json",
        }
    )
    req = request.Request(
        f"{API_URL}?{params}",
        headers={
            "X-ELS-APIKey": config.api_key,
            "Accept": "application/json",
            "User-Agent": "PRISMA-AI-Tutor/1.0",
        },
    )
    return fetch_json_with_retries(req, config)


def fetch_json_with_retries(req: request.Request, config: SearchConfig) -> dict[str, Any]:
    attempt = 0
    delay = config.retry_delay
    while True:
        try:
            with request.urlopen(req, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt >= config.max_retries:
                raise
            sleep_seconds = min(delay, config.max_retry_wait)
            print(f"[Scopus] transient HTTP {exc.code}; retrying in {sleep_seconds:.1f}s.", flush=True)
            time.sleep(sleep_seconds)
            attempt += 1
            delay *= 2
        except error.URLError:
            if attempt >= config.max_retries:
                raise
            time.sleep(delay)
            attempt += 1
            delay *= 2


def normalize_work(work: dict[str, Any], position: int) -> dict[str, Any]:
    title = clean_text(work.get("dc:title"))
    doi = clean_text(work.get("prism:doi"))
    url = clean_text(work.get("prism:url"))
    abstract = clean_text(work.get("dc:description"))
    affiliation = first_affiliation(work.get("affiliation"))
    return {
        "code": f"S{position:03d}",
        "source": "Scopus",
        "source_id": clean_text(work.get("eid")),
        "title": title,
        "authors": clean_text(work.get("dc:creator")),
        "year": clean_text(work.get("prism:coverDate"))[:4],
        "first_affiliation": affiliation.get("name", ""),
        "country_code": "",
        "country": affiliation.get("country", ""),
        "publication_date": clean_text(work.get("prism:coverDate")),
        "doi": doi,
        "abstract": abstract,
        "journal": clean_text(work.get("prism:publicationName")),
        "journal_type": clean_text(work.get("srctype")),
        "language": "",
        "document_type": normalize_document_type(clean_text(work.get("subtypeDescription") or work.get("subtype"))),
        "is_oa": parse_openaccess(work),
        "oa_status": clean_text(work.get("openaccess")),
        "source_is_in_doaj": False,
        "cited_by_count": parse_int(work.get("citedby-count")),
        "primary_url": url,
        "pdf_url": "",
        "openalex_url": "",
        "fulltext_accessible": "Por verificar" if url or doi else "No",
        "abstract_available": bool(abstract),
    }


def first_affiliation(value: Any) -> dict[str, str]:
    if isinstance(value, list) and value:
        item = value[0] if isinstance(value[0], dict) else {}
    elif isinstance(value, dict):
        item = value
    else:
        item = {}
    return {
        "name": clean_text(item.get("affilname")),
        "country": clean_text(item.get("affiliation-country")),
    }


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "; ".join(clean_text(item) for item in value if clean_text(item))
    if isinstance(value, dict):
        return "; ".join(clean_text(item) for item in value.values() if clean_text(item))
    return " ".join(str(value).split())


def normalize_document_type(value: str) -> str:
    item = value.casefold()
    if "article" in item:
        return "article"
    if "review" in item:
        return "review"
    return value


def parse_openaccess(work: dict[str, Any]) -> bool:
    return str(work.get("openaccessFlag", "")).casefold() == "true" or str(work.get("openaccess", "")) == "1"


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
        warnings.append("max_results supera el umbral operativo configurado.")
    if config.view == "STANDARD":
        warnings.append(
            "Scopus Search API en vista STANDARD no entrega resumen en la respuesta; "
            "la query puede buscar en TITLE-ABS-KEY, pero el cribado automatizado recibe metadata sin abstract."
        )
    if config.require_abstract and exported_count == 0:
        warnings.append(
            "SCOPUS_REQUIRE_ABSTRACT=true dejo la exportacion vacia porque la respuesta no incluyo abstracts. "
            "Se requiere entitlement adicional o exportacion manual con abstracts."
        )
    total = meta.get("total_results")
    if isinstance(total, int) and total > config.max_results:
        warnings.append("Scopus reporta más resultados que los exportados; la muestra queda acotada por max_results.")
    return warnings


def build_search_log_text(
    config: SearchConfig,
    meta: dict[str, Any],
    result_count: int,
    snapshot: dict[str, Any],
    metadata_columns: dict[str, list[str]],
    warnings: list[str],
) -> str:
    run_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    lines = [
        "# Bitacora de busqueda Scopus",
        "",
        f"- Fecha de ejecucion: `{run_at}`",
        "- Fuente: `Scopus Search API`",
        f"- Vista: `{config.view}`",
        f"- Consulta: `{config.query}`",
        f"- Requerir abstract: `{config.require_abstract}`",
        f"- Total reportado por Scopus: `{meta.get('total_results', 'No reportado')}`",
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
        print(f"Invalid configuration: {exc}", file=sys.stderr)
        return 2
    ensure_dir(config.out_dir)
    search_dir = search_output_dir(config.out_dir)
    screening_dir = screening_output_dir(config.out_dir)
    ensure_dir(search_dir)
    ensure_dir(screening_dir)
    write_query_file(search_dir / config.query_output_name, config.query)
    try:
        metadata_columns = load_metadata_config(config.metadata_config_file)
        raw_results, meta = fetch_results(config)
    except Exception as exc:  # noqa: BLE001
        print(f"Scopus request failed: {exc}", file=sys.stderr)
        return 1
    normalized = [normalize_work(work, index + 1) for index, work in enumerate(raw_results)]
    filtered = filter_normalized_results(normalized, config)
    snapshot = compute_quality_snapshot(filtered)
    warnings = sampling_warnings(config, meta, len(filtered))
    summary = {
        "source": "Scopus",
        "query": config.query,
        "view": config.view,
        "config_file": str(config.config_file) if config.config_file else None,
        "max_results": config.max_results,
        "count": meta.get("total_results"),
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
