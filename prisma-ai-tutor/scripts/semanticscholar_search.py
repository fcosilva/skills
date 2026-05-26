#!/usr/bin/env python3
"""Search Semantic Scholar and export normalized PRISMA results."""

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


API_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
DEFAULT_LIMIT = 50
MAX_LIMIT = 100
DEFAULT_MAX_RESULTS = 100
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_DELAY = 2.0
DEFAULT_MAX_RETRY_WAIT = 60.0
DEFAULT_RESULTS_THRESHOLD = 500
DEFAULT_FIELDS = ",".join(
    [
        "paperId",
        "externalIds",
        "url",
        "title",
        "abstract",
        "year",
        "authors",
        "venue",
        "publicationVenue",
        "publicationTypes",
        "publicationDate",
        "citationCount",
        "isOpenAccess",
        "openAccessPdf",
        "fieldsOfStudy",
        "s2FieldsOfStudy",
    ]
)


@dataclass
class SearchConfig:
    query: str
    from_year: str | None
    to_year: str | None
    require_abstract: bool
    require_open_access: bool
    limit: int
    max_results: int
    sampling_threshold: int
    quiet_progress: bool
    max_retries: int
    retry_delay: float
    max_retry_wait: float
    api_key: str | None
    out_dir: Path
    query_output_name: str
    config_file: Path | None
    metadata_config_file: Path


def parse_args() -> SearchConfig:
    parser = argparse.ArgumentParser(description="Run a Semantic Scholar search and export normalized results.")
    parser.add_argument("query", nargs="?", help="Semantic/natural-language query. Optional with --query-file.")
    parser.add_argument("--query-file", help="Path to a text file containing the Semantic Scholar query.")
    parser.add_argument(
        "--config-file",
        help=(
            "Path to env-style config. Supported keys: SEMANTIC_SCHOLAR_API_KEY, "
            "SEMANTIC_SCHOLAR_QUERY_FILE, SEMANTIC_SCHOLAR_FROM_YEAR, SEMANTIC_SCHOLAR_TO_YEAR, "
            "SEMANTIC_SCHOLAR_REQUIRE_ABSTRACT, SEMANTIC_SCHOLAR_REQUIRE_OPEN_ACCESS, "
            "SEMANTIC_SCHOLAR_LIMIT, SEMANTIC_SCHOLAR_MAX_RESULTS, PRISMA_MAX_RESULTS_THRESHOLD, "
            "SEMANTIC_SCHOLAR_MAX_RETRIES, SEMANTIC_SCHOLAR_RETRY_DELAY, "
            "SEMANTIC_SCHOLAR_MAX_RETRY_WAIT, SEMANTIC_SCHOLAR_OUT_DIR, "
            "SEMANTIC_SCHOLAR_QUERY_OUTPUT_NAME, SEMANTIC_SCHOLAR_METADATA_CONFIG."
        ),
    )
    parser.add_argument("--api-key", help="Semantic Scholar API key. Strongly recommended.")
    parser.add_argument("--from-year", help="Lower publication year bound in YYYY format.")
    parser.add_argument("--to-year", help="Upper publication year bound in YYYY format.")
    parser.add_argument("--require-abstract", action="store_true")
    parser.add_argument("--require-open-access", action="store_true")
    parser.add_argument("--limit", type=int, help=f"Results per API page. Default: {DEFAULT_LIMIT}. Max: {MAX_LIMIT}.")
    parser.add_argument("--max-results", type=int, help=f"Maximum records to export. Default: {DEFAULT_MAX_RESULTS}.")
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
    limit = min(max(resolve_int(args.limit, env_config.get("SEMANTIC_SCHOLAR_LIMIT"), DEFAULT_LIMIT), 1), MAX_LIMIT)
    max_results = max(
        resolve_int(args.max_results, env_config.get("SEMANTIC_SCHOLAR_MAX_RESULTS"), DEFAULT_MAX_RESULTS),
        1,
    )
    sampling_threshold = max(
        resolve_int(args.sampling_threshold, env_config.get("PRISMA_MAX_RESULTS_THRESHOLD"), DEFAULT_RESULTS_THRESHOLD),
        1,
    )
    max_retries = max(
        resolve_int(args.max_retries, env_config.get("SEMANTIC_SCHOLAR_MAX_RETRIES"), DEFAULT_MAX_RETRIES),
        0,
    )
    retry_delay = max(
        resolve_float(args.retry_delay, env_config.get("SEMANTIC_SCHOLAR_RETRY_DELAY"), DEFAULT_RETRY_DELAY),
        0.1,
    )
    max_retry_wait = max(
        resolve_float(
            args.max_retry_wait,
            env_config.get("SEMANTIC_SCHOLAR_MAX_RETRY_WAIT"),
            DEFAULT_MAX_RETRY_WAIT,
        ),
        0.1,
    )
    out_dir = resolve_workspace_path(
        resolve_str(args.out_dir, env_config.get("SEMANTIC_SCHOLAR_OUT_DIR"), "outputs/semanticscholar-search"),
        config_file,
        env_config,
    )
    metadata_config_raw = resolve_str(args.metadata_config, env_config.get("SEMANTIC_SCHOLAR_METADATA_CONFIG"))
    metadata_config_file = (
        resolve_workspace_path(metadata_config_raw, config_file, env_config)
        if metadata_config_raw
        else DEFAULT_METADATA_CONFIG_PATH
    )
    return SearchConfig(
        query=resolve_semanticscholar_query(args.query, args.query_file, env_config, config_file),
        from_year=resolve_str(args.from_year, env_config.get("SEMANTIC_SCHOLAR_FROM_YEAR")),
        to_year=resolve_str(args.to_year, env_config.get("SEMANTIC_SCHOLAR_TO_YEAR")),
        require_abstract=resolve_bool_flag(
            args.require_abstract,
            env_config.get("SEMANTIC_SCHOLAR_REQUIRE_ABSTRACT"),
            True,
        ),
        require_open_access=resolve_bool_flag(
            args.require_open_access,
            env_config.get("SEMANTIC_SCHOLAR_REQUIRE_OPEN_ACCESS"),
            False,
        ),
        limit=limit,
        max_results=max_results,
        sampling_threshold=sampling_threshold,
        quiet_progress=args.quiet_progress,
        max_retries=max_retries,
        retry_delay=retry_delay,
        max_retry_wait=max_retry_wait,
        api_key=resolve_str(args.api_key, env_config.get("SEMANTIC_SCHOLAR_API_KEY")),
        out_dir=out_dir,
        query_output_name=resolve_str(args.query_output_name, env_config.get("SEMANTIC_SCHOLAR_QUERY_OUTPUT_NAME"), "query.txt"),
        config_file=config_file,
        metadata_config_file=metadata_config_file,
    )


def resolve_semanticscholar_query(
    cli_query: str | None,
    query_file: str | None,
    env_config: dict[str, str],
    config_file: Path | None,
) -> str:
    config_query_file = env_config.get("SEMANTIC_SCHOLAR_QUERY_FILE", "").strip() or None
    effective_query_file = query_file or config_query_file
    if cli_query and effective_query_file:
        raise ValueError("Use either a positional query or SEMANTIC_SCHOLAR_QUERY_FILE/--query-file, not both.")
    if effective_query_file:
        query_path = (
            Path(effective_query_file).expanduser().resolve()
            if query_file
            else resolve_workspace_path(effective_query_file, config_file, env_config)
        )
        return query_path.read_text(encoding="utf-8").strip()
    if cli_query:
        return cli_query.strip()
    raise ValueError("A Semantic Scholar query is required.")


def search_output_dir(run_dir: Path) -> Path:
    return run_dir / "search" / "semanticscholar"


def screening_output_dir(run_dir: Path) -> Path:
    return run_dir / "screening"


def year_filter(config: SearchConfig) -> str | None:
    if not config.from_year and not config.to_year:
        return None
    start = config.from_year or ""
    end = config.to_year or ""
    if start and end:
        return f"{start}-{end}"
    return start or f"-{end}"


def fetch_results(config: SearchConfig) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    total: int | None = None
    next_offset: int | None = None

    while len(rows) < config.max_results:
        batch_size = min(config.limit, config.max_results - len(rows))
        params = {
            "query": config.query,
            "limit": str(batch_size),
            "offset": str(offset),
            "fields": DEFAULT_FIELDS,
        }
        years = year_filter(config)
        if years:
            params["year"] = years
        payload = fetch_json_with_retries(f"{API_URL}?{parse.urlencode(params)}", config)
        if total is None:
            total = parse_int(payload.get("total"))
        data = payload.get("data") or []
        if not data:
            break
        rows.extend(normalize_work(item, len(rows) + index + 1) for index, item in enumerate(data))
        if not config.quiet_progress:
            print(
                f"[Semantic Scholar] fetched {len(rows)} records "
                f"(Semantic Scholar reports about {total if total is not None else 'No reportado'}).",
                flush=True,
            )
        next_offset = parse_int(payload.get("next"))
        if not next_offset or next_offset <= offset:
            break
        offset = next_offset

    return rows, {"count": total, "next": next_offset, "query": config.query, "year": year_filter(config)}


def fetch_json_with_retries(url: str, config: SearchConfig) -> dict[str, Any]:
    attempt = 0
    delay = config.retry_delay
    while True:
        headers = {
            "Accept": "application/json",
            "User-Agent": "PRISMA-AI-Tutor/1.0",
        }
        if config.api_key:
            headers["x-api-key"] = config.api_key
        req = request.Request(url, headers=headers)
        try:
            with request.urlopen(req, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt >= config.max_retries:
                raise
            retry_after = exc.headers.get("Retry-After")
            wait = parse_retry_after(retry_after) or delay
            time.sleep(min(wait, config.max_retry_wait))
            attempt += 1
            delay *= 2
        except error.URLError:
            if attempt >= config.max_retries:
                raise
            time.sleep(min(delay, config.max_retry_wait))
            attempt += 1
            delay *= 2


def normalize_work(work: dict[str, Any], position: int) -> dict[str, Any]:
    external_ids = work.get("externalIds") or {}
    oa_pdf = work.get("openAccessPdf") or {}
    publication_venue = work.get("publicationVenue") or {}
    authors = work.get("authors") or []
    publication_types = work.get("publicationTypes") or []
    fields = work.get("fieldsOfStudy") or []
    s2_fields = work.get("s2FieldsOfStudy") or []
    doi = external_ids.get("DOI") or ""
    title = work.get("title") or ""
    abstract = work.get("abstract") or ""
    year = str(work.get("year") or "")
    primary_url = doi_url(doi) or work.get("url") or ""
    pdf_url = oa_pdf.get("url") or ""
    return {
        "code": f"S{position:03d}",
        "source": "Semantic Scholar",
        "source_id": work.get("paperId") or external_ids.get("CorpusId") or "",
        "title": title,
        "authors": "; ".join(item.get("name", "") for item in authors if item.get("name")),
        "year": year,
        "first_affiliation": "",
        "country_code": "",
        "country": "",
        "publication_date": work.get("publicationDate") or year,
        "doi": doi,
        "abstract": abstract,
        "journal": publication_venue.get("name") or work.get("venue") or "",
        "journal_type": publication_venue.get("type") or "",
        "language": "",
        "document_type": normalize_document_type(publication_types),
        "is_oa": bool(work.get("isOpenAccess")),
        "oa_status": oa_pdf.get("status") or "",
        "source_is_in_doaj": False,
        "cited_by_count": parse_int(work.get("citationCount")),
        "primary_url": primary_url,
        "pdf_url": pdf_url,
        "openalex_url": "",
        "fulltext_accessible": "Por verificar" if pdf_url or primary_url else "No",
        "abstract_available": bool(abstract),
        "semantic_scholar_url": work.get("url") or "",
        "semantic_scholar_fields": "; ".join(str(item) for item in fields if item),
        "semantic_scholar_s2_fields": "; ".join(
            item.get("category", "") for item in s2_fields if isinstance(item, dict) and item.get("category")
        ),
    }


def normalize_document_type(types: list[Any]) -> str:
    joined = "; ".join(str(item) for item in types if item)
    lower = joined.casefold()
    if "journalarticle" in lower or "journal article" in lower:
        return "article"
    if "review" in lower:
        return "review"
    if "conference" in lower:
        return "conference"
    if "book" in lower:
        return "book"
    return joined


def doi_url(doi: str) -> str:
    doi = doi.strip()
    return f"https://doi.org/{doi}" if doi else ""


def parse_int(value: Any) -> int:
    try:
        return int(str(value))
    except Exception:  # noqa: BLE001
        return 0


def parse_retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def filter_normalized_results(rows: list[dict[str, Any]], config: SearchConfig) -> list[dict[str, Any]]:
    filtered = rows
    if config.require_abstract:
        filtered = [row for row in filtered if row.get("abstract")]
    if config.require_open_access:
        filtered = [row for row in filtered if row.get("is_oa") or row.get("pdf_url")]
    return filtered


def sampling_warnings(config: SearchConfig, meta: dict[str, Any], exported_count: int) -> list[str]:
    warnings: list[str] = []
    if not config.api_key:
        warnings.append("SEMANTIC_SCHOLAR_API_KEY no está configurada; la API puede responder 429 por límites compartidos.")
    if config.max_results > config.sampling_threshold:
        warnings.append("SEMANTIC_SCHOLAR_MAX_RESULTS supera el umbral operativo configurado.")
    count = meta.get("count")
    if isinstance(count, int) and count > 1000:
        warnings.append(
            "Semantic Scholar reporta más de 1000 resultados estimados. "
            "Corresponde refinar la query semántica antes del cribado inicial."
        )
    elif isinstance(count, int) and count > config.max_results:
        warnings.append(
            "Semantic Scholar reporta más resultados que max_results. Si el usuario no aprueba "
            "trabajar con una muestra acotada, corresponde refinar la query."
        )
    if config.require_abstract and exported_count == 0:
        warnings.append("SEMANTIC_SCHOLAR_REQUIRE_ABSTRACT=true dejó la exportación vacía.")
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
    lines = [
        "# Bitacora de busqueda Semantic Scholar",
        "",
        f"- Fecha de ejecucion: `{datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')}`",
        "- Fuente: `Semantic Scholar Graph API`",
        f"- Consulta semantica: `{config.query}`",
        f"- Rango de años: `{year_filter(config) or 'sin filtro'}`",
        f"- Requerir abstract: `{config.require_abstract}`",
        f"- Requerir acceso abierto: `{config.require_open_access}`",
        f"- API key configurada: `{'si' if config.api_key else 'no'}`",
        f"- Total reportado por Semantic Scholar: `{meta.get('count', 'No reportado')}`",
        f"- Registros excluidos por filtros locales: `{filtered_out_count}`",
        f"- Resultados exportados: `{result_count}`",
        f"- Columnas de cribado: `{json.dumps(metadata_columns.get('screening_columns', []), ensure_ascii=True)}`",
        "",
        "## Nota metodologica",
        "",
        "Semantic Scholar se usa aqui como fuente complementaria de busqueda semantica.",
        "Su query no debe tratarse como sintaxis booleana estricta ni como busqueda por campo title/abstract/keywords.",
        "El solapamiento con otras fuentes se controla en la fusion y deduplicacion posterior.",
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
        print(f"Invalid Semantic Scholar configuration: {exc}", file=sys.stderr)
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
        print(f"Semantic Scholar request failed: {exc}", file=sys.stderr)
        return 1
    filtered = filter_normalized_results(raw_results, config)
    snapshot = compute_quality_snapshot(filtered)
    warnings = sampling_warnings(config, meta, len(filtered))
    filtered_out_count = max(len(raw_results) - len(filtered), 0)
    summary = {
        "source": "Semantic Scholar",
        "query": config.query,
        "config_file": str(config.config_file) if config.config_file else None,
        "max_results": config.max_results,
        "count": meta.get("count"),
        "exported_results": len(filtered),
        "require_abstract": config.require_abstract,
        "require_open_access": config.require_open_access,
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
    log_text = build_search_log_text(config, meta, len(filtered), snapshot, metadata_columns, warnings, filtered_out_count)
    (search_dir / "search_log.md").write_text(log_text, encoding="utf-8")
    print(log_text)
    refresh_run_outputs(config.out_dir)
    print(f"Archivos exportados en: {config.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
