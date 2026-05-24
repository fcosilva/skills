#!/usr/bin/env python3
"""Search DOAJ articles and export normalized results for PRISMA-style workflows."""

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


API_URL = "https://doaj.org/api/v4/search/articles/"
DEFAULT_PAGE_SIZE = 20
DEFAULT_MAX_RESULTS = 100
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_DELAY = 2.0
DEFAULT_MAX_RETRY_WAIT = 60.0
DEFAULT_RESULTS_THRESHOLD = 500
MAX_PAGE_SIZE = 100


@dataclass
class SearchConfig:
    query: str
    from_year: str | None
    to_year: str | None
    require_abstract: bool
    page_size: int
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
            "Run a DOAJ article search and export normalized results for screening "
            "and traceability."
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
        "--config-file",
        help=(
            "Path to an env-style configuration file. Supported keys: "
            "DOAJ_QUERY_FILE, DOAJ_FROM_YEAR, DOAJ_TO_YEAR, DOAJ_REQUIRE_ABSTRACT, "
            "DOAJ_PAGE_SIZE, DOAJ_MAX_RESULTS, PRISMA_MAX_RESULTS_THRESHOLD, "
            "DOAJ_MAX_RETRIES, DOAJ_RETRY_DELAY, DOAJ_MAX_RETRY_WAIT, "
            "DOAJ_OUT_DIR, DOAJ_QUERY_OUTPUT_NAME, DOAJ_METADATA_CONFIG."
        ),
    )
    parser.add_argument(
        "--from-year",
        help="Lower publication year bound in YYYY format. Applied locally after retrieval.",
    )
    parser.add_argument(
        "--to-year",
        help="Upper publication year bound in YYYY format. Applied locally after retrieval.",
    )
    parser.add_argument(
        "--require-abstract",
        action="store_true",
        help=(
            "Keep only results with abstract available. Default: true unless "
            "DOAJ_REQUIRE_ABSTRACT=false in the config file."
        ),
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=None,
        help=(
            f"Results per API page. Default: {DEFAULT_PAGE_SIZE}. "
            f"Suggested maximum for this script: {MAX_PAGE_SIZE}."
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
        help=f"Maximum retries for transient HTTP/network failures. Default: {DEFAULT_MAX_RETRIES}.",
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
            "`search/doaj/` and screening artifacts under `screening/`."
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
    query = resolve_doaj_query(args.query, args.query_file, env_config, config_file)

    page_size = min(
        max(resolve_int(args.page_size, env_config.get("DOAJ_PAGE_SIZE"), DEFAULT_PAGE_SIZE), 1),
        MAX_PAGE_SIZE,
    )
    max_results = max(
        resolve_int(args.max_results, env_config.get("DOAJ_MAX_RESULTS"), DEFAULT_MAX_RESULTS),
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
        resolve_int(args.max_retries, env_config.get("DOAJ_MAX_RETRIES"), DEFAULT_MAX_RETRIES),
        0,
    )
    retry_delay = max(
        resolve_float(args.retry_delay, env_config.get("DOAJ_RETRY_DELAY"), DEFAULT_RETRY_DELAY),
        0.1,
    )
    max_retry_wait = max(
        resolve_float(
            args.max_retry_wait,
            env_config.get("DOAJ_MAX_RETRY_WAIT"),
            DEFAULT_MAX_RETRY_WAIT,
        ),
        0.1,
    )
    require_abstract = resolve_bool_flag(
        args.require_abstract,
        env_config.get("DOAJ_REQUIRE_ABSTRACT"),
        True,
    )
    out_dir = resolve_workspace_path(
        resolve_str(args.out_dir, env_config.get("DOAJ_OUT_DIR"), "outputs/doaj-search"),
        config_file,
        env_config,
    )
    query_output_name = resolve_str(
        args.query_output_name,
        env_config.get("DOAJ_QUERY_OUTPUT_NAME"),
        "query.txt",
    )
    metadata_config_raw = resolve_str(args.metadata_config, env_config.get("DOAJ_METADATA_CONFIG"))
    metadata_config_file = (
        resolve_workspace_path(metadata_config_raw, config_file, env_config)
        if metadata_config_raw
        else DEFAULT_METADATA_CONFIG_PATH
    )

    return SearchConfig(
        query=query,
        from_year=resolve_str(args.from_year, env_config.get("DOAJ_FROM_YEAR")),
        to_year=resolve_str(args.to_year, env_config.get("DOAJ_TO_YEAR")),
        require_abstract=require_abstract,
        page_size=page_size,
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


def resolve_doaj_query(
    cli_query: str | None,
    query_file: str | None,
    env_config: dict[str, str],
    config_file: Path | None,
) -> str:
    config_query_file = env_config.get("DOAJ_QUERY_FILE", "").strip() or None
    effective_query_file = query_file or config_query_file

    if cli_query and query_file:
        raise ValueError("Use either a positional query or --query-file, not both.")
    if cli_query and config_query_file:
        raise ValueError(
            "Use either a positional query or DOAJ_QUERY_FILE/--query-file, not both."
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
    raise ValueError(
        "A query is required. Provide it directly or with --query-file/DOAJ_QUERY_FILE."
    )


def validate_year(value: str | None) -> None:
    if value is None:
        return
    if len(value) != 4 or not value.isdigit():
        raise ValueError(f"Invalid year: {value!r}. Expected YYYY.")


def search_output_dir(run_dir: Path) -> Path:
    return run_dir / "search" / "doaj"


def screening_output_dir(run_dir: Path) -> Path:
    return run_dir / "screening"


def fetch_results(config: SearchConfig) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    results: list[dict[str, Any]] = []
    page = 1
    total: int | None = None
    next_url: str | None = None
    pages_fetched = 0

    while len(results) < config.max_results:
        if next_url is None:
            query_segment = parse.quote(config.query, safe="")
            url = f"{API_URL}{query_segment}?page={page}&pageSize={config.page_size}"
        else:
            url = next_url

        payload = fetch_json_with_retries(url, config)
        pages_fetched += 1

        if total is None:
            total = payload.get("total")

        page_results = payload.get("results", [])
        if not page_results:
            break

        remaining = config.max_results - len(results)
        results.extend(page_results[:remaining])

        if not config.quiet_progress:
            total_hint = total if total is not None else "No reportado"
            print(
                f"[DOAJ] page {payload.get('page', page)} fetched, accumulated {len(results)} "
                f"records (DOAJ reports about {total_hint}).",
                flush=True,
            )

        next_url = payload.get("next")
        if not next_url or len(page_results) < config.page_size:
            break
        page += 1

    meta = {
        "count": total,
        "pages_fetched": pages_fetched,
        "page_size": config.page_size,
        "query": config.query,
        "next": next_url,
    }
    return results, meta


def fetch_json_with_retries(url: str, config: SearchConfig) -> dict[str, Any]:
    attempt = 0
    delay = config.retry_delay

    while True:
        req = request.Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "PRISMA-AI-Tutor/1.0",
            },
        )
        try:
            with request.urlopen(req) as response:
                return json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt >= config.max_retries:
                raise
            sleep_seconds = min(delay, config.max_retry_wait)
            print(
                f"[DOAJ] transient HTTP {exc.code}; retrying in {sleep_seconds:.1f}s "
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
                f"[DOAJ] transient network error; retrying in {delay:.1f}s "
                f"(attempt {attempt + 1} of {config.max_retries}).",
                flush=True,
            )
            time.sleep(delay)
            attempt += 1
            delay *= 2


def normalize_work(work: dict[str, Any], position: int) -> dict[str, Any]:
    bibjson = work.get("bibjson") or {}
    identifiers = bibjson.get("identifier") or []
    authors = bibjson.get("author") or []
    journal = bibjson.get("journal") or {}
    links = bibjson.get("link") or []

    doi = next(
        (item.get("id", "") for item in identifiers if (item.get("type") or "").lower() == "doi"),
        "",
    )
    fulltext_link = next(
        (item.get("url", "") for item in links if (item.get("type") or "").lower() == "fulltext"),
        "",
    )
    first_affiliation = next((item.get("affiliation", "") for item in authors if item.get("affiliation")), "")
    journal_languages = journal.get("language") or []
    language = ",".join(journal_languages)

    return {
        "code": f"D{position:03d}",
        "source": "DOAJ",
        "source_id": work.get("id", ""),
        "title": bibjson.get("title", ""),
        "authors": "; ".join(item.get("name", "") for item in authors if item.get("name")),
        "year": bibjson.get("year", ""),
        "first_affiliation": first_affiliation,
        "country_code": journal.get("country", ""),
        "country": journal.get("country", ""),
        "publication_date": build_publication_date(bibjson),
        "doi": doi,
        "abstract": bibjson.get("abstract", ""),
        "journal": journal.get("title", ""),
        "journal_type": "",
        "language": language,
        "document_type": "article",
        "is_oa": True,
        "oa_status": "doaj",
        "source_is_in_doaj": True,
        "cited_by_count": 0,
        "primary_url": fulltext_link,
        "pdf_url": infer_pdf_url(links),
        "openalex_url": "",
        "fulltext_accessible": "Por verificar" if fulltext_link else "No",
        "abstract_available": bool(bibjson.get("abstract")),
    }


def build_publication_date(bibjson: dict[str, Any]) -> str:
    year = (bibjson.get("year") or "").strip()
    month = (bibjson.get("month") or "").strip()
    if not year:
        return ""
    if month.isdigit():
        return f"{year}-{int(month):02d}-01"
    return year


def infer_pdf_url(links: list[dict[str, Any]]) -> str:
    for item in links:
        content_type = (item.get("content_type") or "").lower()
        url = item.get("url", "")
        if "pdf" in content_type or url.lower().endswith(".pdf"):
            return url
    return ""


def filter_normalized_results(
    rows: list[dict[str, Any]],
    config: SearchConfig,
) -> list[dict[str, Any]]:
    filtered = rows
    if config.require_abstract:
        filtered = [row for row in filtered if row.get("abstract")]
    if config.from_year:
        filtered = [row for row in filtered if extract_year(row.get("year")) >= int(config.from_year)]
    if config.to_year:
        filtered = [row for row in filtered if extract_year(row.get("year")) <= int(config.to_year)]
    return filtered


def extract_year(value: Any) -> int:
    try:
        return int(str(value)[:4])
    except Exception:  # noqa: BLE001
        return 0


def post_api_filter_descriptions(config: SearchConfig) -> list[str]:
    descriptions: list[str] = []
    if config.require_abstract:
        descriptions.append(
            "Se excluyen localmente los registros sin `bibjson.abstract` porque el caso exige `require_abstract=true`."
        )
    if config.from_year:
        descriptions.append(
            f"Se excluyen localmente los registros anteriores a `{config.from_year}`."
        )
    if config.to_year:
        descriptions.append(
            f"Se excluyen localmente los registros posteriores a `{config.to_year}`."
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
            "DOAJ reporta más de 1000 resultados estimados. Corresponde refinar "
            "la query antes del cribado inicial."
        )
    elif count > config.max_results:
        warnings.append(
            "DOAJ reporta más resultados que max_results. Si el usuario no aprueba "
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
        "from_year": config.from_year,
        "to_year": config.to_year,
        "require_abstract": config.require_abstract,
        "sampling_threshold": config.sampling_threshold,
        "page_size": config.page_size,
        "max_retries": config.max_retries,
        "retry_delay": config.retry_delay,
        "max_retry_wait": config.max_retry_wait,
        "config_file": str(config.config_file) if config.config_file else None,
        "metadata_config_file": str(config.metadata_config_file),
        "screening_columns": metadata_columns.get("screening_columns", []),
    }
    local_post_filters = post_api_filter_descriptions(config)
    fetched_before_post_filters = result_count + filtered_out_count

    lines = [
        "# Bitacora de busqueda DOAJ",
        "",
        f"- Fecha de ejecucion: `{run_at}`",
        f"- Fuente: `DOAJ API`",
        f"- Consulta: `{config.query}`",
        f"- Resultados por pagina: `{config.page_size}`",
        f"- Requerir abstract: `{config.require_abstract}`",
        f"- Umbral operativo de muestra: `{config.sampling_threshold}`",
        f"- Filtros: `{json.dumps(filters, ensure_ascii=True)}`",
        f"- Resultados estimados por DOAJ: `{meta.get('count', 'No reportado')}`",
        f"- Paginas recuperadas: `{meta.get('pages_fetched', 'No reportado')}`",
        f"- Registros recuperados por esta ejecucion antes de filtros locales: `{fetched_before_post_filters}`",
        f"- Registros excluidos por reglas locales posteriores a la API: `{filtered_out_count}`",
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
        f"- Registros con abstract: `{snapshot['with_abstract']}` de `{snapshot['total_results']}`",
        f"- Registros con revista o fuente identificada: `{snapshot['with_journal']}` de `{snapshot['total_results']}`",
        f"- Registros tipo article: `{snapshot['articles']}` de `{snapshot['total_results']}`",
        f"- Registros open access: `{snapshot['open_access_items']}` de `{snapshot['total_results']}`",
        f"- Registros con fuente en DOAJ: `{snapshot['source_in_doaj_items']}` de `{snapshot['total_results']}`",
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
        "Esta bitacora documenta una recuperacion automatizada inicial desde la API de DOAJ.",
        "La inclusion final de estudios debe realizarse mediante cribado humano con criterios explicitos.",
        "Si DOAJ reporta mas resultados que `max_results`, el recorte se interpreta como una",
        "muestra operativa priorizada por la query ejecutada, no como una seleccion metodologica final.",
        "",
    ]
    insert_at = lines.index("## Alertas de muestreo y volumen") - 1
    if local_post_filters:
        lines[insert_at:insert_at] = [f"- {item}" for item in local_post_filters]
    else:
        lines[insert_at:insert_at] = ["- `No se aplicaron filtros locales posteriores a la API.`"]
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
    write_query_file(search_dir / config.query_output_name, config.query)

    try:
        metadata_columns = load_metadata_config(config.metadata_config_file)
    except Exception as exc:  # noqa: BLE001
        print(f"Metadata config failed: {exc}", file=sys.stderr)
        return 2

    try:
        raw_results, meta = fetch_results(config)
    except Exception as exc:  # noqa: BLE001
        print(f"DOAJ request failed: {exc}", file=sys.stderr)
        return 1

    normalized = [
        normalize_work(work, position=index + 1)
        for index, work in enumerate(raw_results)
    ]
    filtered_normalized = filter_normalized_results(normalized, config)
    filtered_out_count = len(normalized) - len(filtered_normalized)
    snapshot = compute_quality_snapshot(filtered_normalized)
    sampling_warnings = compute_sampling_warnings(config, meta)

    summary = {
        "source": "DOAJ",
        "query": config.query,
        "config_file": str(config.config_file) if config.config_file else None,
        "from_year": config.from_year,
        "to_year": config.to_year,
        "page_size": config.page_size,
        "max_results": config.max_results,
        "sampling_threshold": config.sampling_threshold,
        "require_abstract": config.require_abstract,
        "fetched_results_before_post_filters": len(normalized),
        "exported_results": len(filtered_normalized),
        "filtered_out_after_fetch": filtered_out_count,
        "doaj_meta_count": meta.get("count"),
        "pages_fetched": meta.get("pages_fetched"),
        "sampling_warnings": sampling_warnings,
        "snapshot": snapshot,
        "metadata_config_file": str(config.metadata_config_file),
        "screening_columns": metadata_columns.get("screening_columns", []),
        "extraction_columns": metadata_columns.get("extraction_columns", []),
    }

    write_json(search_dir / "raw_results.json", raw_results)
    write_json(search_dir / "normalized_results.json", filtered_normalized)
    write_json(search_dir / "summary.json", summary)
    write_csv(search_dir / "normalized_results.csv", filtered_normalized)
    write_screening_matrix(
        screening_dir / "screening_matrix.md",
        filtered_normalized,
        metadata_columns.get("screening_columns", []),
    )
    write_screening_matrix_csv(
        screening_dir / "screening_matrix.csv",
        filtered_normalized,
        metadata_columns.get("screening_columns", []),
    )
    search_log_text = write_search_log(
        search_dir / "search_log.md",
        config,
        meta,
        len(filtered_normalized),
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
