#!/usr/bin/env python3
"""Search Redalyc records and export normalized results for PRISMA-style workflows."""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import unicodedata
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


API_URL = "http://api.redalyc.org/search/"
DEFAULT_SEARCH_FIELD = "title"
DEFAULT_BATCH_SIZE = 10
DEFAULT_MAX_RESULTS = 100
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_DELAY = 2.0
DEFAULT_MAX_RETRY_WAIT = 60.0
DEFAULT_RESULTS_THRESHOLD = 500
VALID_SEARCH_FIELDS = {
    "all",
    "country",
    "date",
    "issn",
    "language",
    "publisher",
    "rights",
    "subject",
    "title",
    "type",
}
DOI_PATTERN = re.compile(r"10\.\d{4,9}/\S+", re.IGNORECASE)
BOOLEAN_QUERY_PATTERN = re.compile(r"\b(AND|OR|NOT)\b|[()]", re.IGNORECASE)


@dataclass
class SearchConfig:
    query: str
    search_field: str
    from_year: str | None
    to_year: str | None
    require_abstract: bool
    batch_size: int
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
        description=(
            "Run a Redalyc search and export normalized results for screening "
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
            "REDALYC_API_KEY, REDALYC_QUERY_FILE, REDALYC_SEARCH_FIELD, "
            "REDALYC_FROM_YEAR, REDALYC_TO_YEAR, REDALYC_REQUIRE_ABSTRACT, "
            "REDALYC_BATCH_SIZE, REDALYC_MAX_RESULTS, PRISMA_MAX_RESULTS_THRESHOLD, "
            "REDALYC_MAX_RETRIES, REDALYC_RETRY_DELAY, REDALYC_MAX_RETRY_WAIT, "
            "REDALYC_OUT_DIR, REDALYC_QUERY_OUTPUT_NAME, REDALYC_METADATA_CONFIG."
        ),
    )
    parser.add_argument(
        "--api-key",
        help="Redalyc API key. If omitted, the script checks config file and REDALYC_API_KEY.",
    )
    parser.add_argument(
        "--search-field",
        choices=sorted(VALID_SEARCH_FIELDS),
        default=None,
        help=(
            "Redalyc search field. Default: title. Use one documented field only. "
            "Examples: title, language, country, subject, type. "
            "`subject` filters discipline, not abstract/resumen."
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
            "Keep only results with `dc_description` available after retrieval. "
            "Default: true unless REDALYC_REQUIRE_ABSTRACT=false in the config file."
        ),
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help=(
            "Requested batch size for Redalyc. The API may still return fixed batches "
            f"of about {DEFAULT_BATCH_SIZE} records. Default request: {DEFAULT_BATCH_SIZE}."
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
        help="Hide per-batch progress messages during retrieval.",
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
            "`search/redalyc/` and screening artifacts under `screening/`."
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
    query = resolve_redalyc_query(args.query, args.query_file, env_config, config_file)
    api_key = resolve_str(args.api_key, env_config.get("REDALYC_API_KEY"))
    if not api_key:
        raise ValueError("Redalyc API key missing. Provide --api-key or REDALYC_API_KEY.")

    batch_size = max(
        resolve_int(args.batch_size, env_config.get("REDALYC_BATCH_SIZE"), DEFAULT_BATCH_SIZE),
        1,
    )
    max_results = max(
        resolve_int(args.max_results, env_config.get("REDALYC_MAX_RESULTS"), DEFAULT_MAX_RESULTS),
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
        resolve_int(args.max_retries, env_config.get("REDALYC_MAX_RETRIES"), DEFAULT_MAX_RETRIES),
        0,
    )
    retry_delay = max(
        resolve_float(
            args.retry_delay,
            env_config.get("REDALYC_RETRY_DELAY"),
            DEFAULT_RETRY_DELAY,
        ),
        0.1,
    )
    max_retry_wait = max(
        resolve_float(
            args.max_retry_wait,
            env_config.get("REDALYC_MAX_RETRY_WAIT"),
            DEFAULT_MAX_RETRY_WAIT,
        ),
        0.1,
    )
    require_abstract = resolve_bool_flag(
        args.require_abstract,
        env_config.get("REDALYC_REQUIRE_ABSTRACT"),
        True,
    )
    search_field = resolve_str(
        args.search_field,
        env_config.get("REDALYC_SEARCH_FIELD"),
        DEFAULT_SEARCH_FIELD,
    ).lower()
    if search_field not in VALID_SEARCH_FIELDS:
        raise ValueError(
            f"Invalid REDALYC_SEARCH_FIELD: {search_field!r}. "
            f"Expected one of: {', '.join(sorted(VALID_SEARCH_FIELDS))}."
        )
    if search_field == "all":
        raise ValueError(
            "REDALYC_SEARCH_FIELD=all is not compatible with the query-driven Phase 3 flow. "
            "Redalyc documents `all()` without a query value, so use a specific field such "
            "as `title`, `language`, `country` or `subject`."
        )
    out_dir = resolve_workspace_path(
        resolve_str(args.out_dir, env_config.get("REDALYC_OUT_DIR"), "outputs/redalyc-search"),
        config_file,
        env_config,
    )
    query_output_name = resolve_str(
        args.query_output_name,
        env_config.get("REDALYC_QUERY_OUTPUT_NAME"),
        "query.txt",
    )
    metadata_config_raw = resolve_str(args.metadata_config, env_config.get("REDALYC_METADATA_CONFIG"))
    metadata_config_file = (
        resolve_workspace_path(metadata_config_raw, config_file, env_config)
        if metadata_config_raw
        else DEFAULT_METADATA_CONFIG_PATH
    )

    return SearchConfig(
        query=query,
        search_field=search_field,
        from_year=resolve_str(args.from_year, env_config.get("REDALYC_FROM_YEAR")),
        to_year=resolve_str(args.to_year, env_config.get("REDALYC_TO_YEAR")),
        require_abstract=require_abstract,
        batch_size=batch_size,
        max_results=max_results,
        sampling_threshold=sampling_threshold,
        quiet_progress=args.quiet_progress,
        max_retries=max_retries,
        retry_delay=retry_delay,
        max_retry_wait=max_retry_wait,
        api_key=api_key,
        out_dir=out_dir,
        query_output_name=query_output_name,
        config_file=config_file,
        metadata_config_file=metadata_config_file,
    )


def resolve_redalyc_query(
    cli_query: str | None,
    query_file: str | None,
    env_config: dict[str, str],
    config_file: Path | None,
) -> str:
    config_query_file = env_config.get("REDALYC_QUERY_FILE", "").strip() or None
    effective_query_file = query_file or config_query_file

    if cli_query and query_file:
        raise ValueError("Use either a positional query or --query-file, not both.")
    if cli_query and config_query_file:
        raise ValueError(
            "Use either a positional query or REDALYC_QUERY_FILE/--query-file, not both."
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
        "A query is required. Provide it directly or with --query-file/REDALYC_QUERY_FILE."
    )


def validate_year(value: str | None) -> None:
    if value is None:
        return
    if len(value) != 4 or not value.isdigit():
        raise ValueError(f"Invalid year: {value!r}. Expected YYYY.")


def search_output_dir(run_dir: Path) -> Path:
    return run_dir / "search" / "redalyc"


def screening_output_dir(run_dir: Path) -> Path:
    return run_dir / "screening"


def build_search_url(config: SearchConfig, start_position: int) -> str:
    encoded_query = parse.quote(config.query, safe="")
    return (
        f"{API_URL}{config.search_field}({encoded_query}),"
        f"page({start_position}),sizePage({config.batch_size})/"
        f"output(json)/download(yes)/token({config.api_key})"
    )


def fetch_results(config: SearchConfig) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    results: list[dict[str, Any]] = []
    start_position = 1
    batches_fetched = 0
    seen_ids: set[str] = set()
    observed_batch_sizes: list[int] = []
    requested_batch_size = config.batch_size
    likely_more_available = False

    while len(results) < config.max_results:
        payload = fetch_json_with_retries(build_search_url(config, start_position), config)
        response = payload.get("searchRetrieveResponse") or {}
        records = response.get("records") or []
        batches_fetched += 1

        if not records:
            break

        observed_batch_sizes.append(len(records))
        new_batch_count = 0
        max_position = start_position
        for item in records:
            source_id = str(item.get("recordIdentifier", "")).strip()
            try:
                max_position = max(max_position, int(str(item.get("recordPosition", "")).strip()))
            except ValueError:
                pass
            if source_id and source_id in seen_ids:
                continue
            if source_id:
                seen_ids.add(source_id)
            results.append(item)
            new_batch_count += 1
            if len(results) >= config.max_results:
                break

        if not config.quiet_progress:
            print(
                f"[Redalyc] start {start_position}, received {len(records)} records, "
                f"accumulated {len(results)} normalized candidates.",
                flush=True,
            )

        if len(results) >= config.max_results:
            likely_more_available = len(records) >= max(1, requested_batch_size)
            break
        if new_batch_count == 0:
            break
        if len(records) < max(1, requested_batch_size):
            break
        next_start = max_position + 1
        if next_start <= start_position:
            break
        start_position = next_start

    meta = {
        "reported_batch_count": (payload.get("searchRetrieveResponse") or {}).get("numberOfRecords")
        if "payload" in locals()
        else None,
        "batches_fetched": batches_fetched,
        "requested_batch_size": requested_batch_size,
        "observed_batch_sizes": observed_batch_sizes,
        "likely_more_available": likely_more_available,
        "query": config.query,
        "search_field": config.search_field,
    }
    return results[: config.max_results], meta


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
                f"[Redalyc] transient HTTP {exc.code}; retrying in {sleep_seconds:.1f}s "
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
                f"[Redalyc] transient network error; retrying in {delay:.1f}s "
                f"(attempt {attempt + 1} of {config.max_retries}).",
                flush=True,
            )
            time.sleep(delay)
            attempt += 1
            delay *= 2


def normalize_work(work: dict[str, Any], position: int) -> dict[str, Any]:
    record = work.get("recordData") or {}
    source_id = str(work.get("recordIdentifier", "")).strip()
    dc_source = clean_text(record.get("dc_source"))
    journal = clean_text(record.get("dc_rights")) or parse_journal_from_source(dc_source)
    article_url = build_article_url(source_id)
    country = parse_country_from_source(dc_source)
    doi = extract_doi(record.get("dc_identifier"))
    document_type = normalize_document_type(clean_text(record.get("dc_type")))
    abstract = clean_text(record.get("dc_description"))
    language = clean_text(record.get("dc_language"))
    authors = normalize_authors(record.get("dc_creator"))

    return {
        "code": f"R{position:03d}",
        "source": "Redalyc",
        "source_id": source_id,
        "title": clean_text(record.get("dc_title")),
        "authors": authors,
        "year": extract_year_text(record.get("dc_date")),
        "first_affiliation": "",
        "country_code": "",
        "country": country,
        "publication_date": extract_year_text(record.get("dc_date")),
        "doi": doi,
        "abstract": abstract,
        "journal": journal,
        "journal_type": "",
        "language": language,
        "document_type": document_type,
        "is_oa": True,
        "oa_status": "gold",
        "source_is_in_doaj": False,
        "cited_by_count": 0,
        "primary_url": article_url or clean_text(record.get("dc_relation")),
        "pdf_url": "",
        "openalex_url": "",
        "fulltext_accessible": (
            "Por verificar" if article_url or clean_text(record.get("dc_format")) else "No"
        ),
        "abstract_available": bool(abstract),
    }


def build_article_url(source_id: str) -> str:
    if not source_id:
        return ""
    return f"http://www.redalyc.org/articulo.oa?id={source_id}"


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "; ".join(clean_text(item) for item in value if clean_text(item))
    text = str(value)
    text = re.sub(r"\s+", " ", text, flags=re.UNICODE).strip()
    return text


def normalize_authors(value: Any) -> str:
    if isinstance(value, list):
        return "; ".join(clean_text(item) for item in value if clean_text(item))
    return clean_text(value)


def parse_journal_from_source(dc_source: str) -> str:
    if not dc_source:
        return ""
    match = re.match(r"^(.*?)\s+\(", dc_source)
    return match.group(1).strip() if match else dc_source


def parse_country_from_source(dc_source: str) -> str:
    if not dc_source:
        return ""
    match = re.search(r"\(([^)]+)\)", dc_source)
    return match.group(1).strip() if match else ""


def extract_doi(identifier_value: Any) -> str:
    values = identifier_value if isinstance(identifier_value, list) else [identifier_value]
    for item in values:
        text = clean_text(item)
        match = DOI_PATTERN.search(text)
        if match:
            return match.group(0)
    return ""


def normalize_document_type(value: str) -> str:
    item = value.lower()
    if "art" in item and ("cient" in item or "scientific" in item):
        return "article"
    if item == "editorial":
        return "editorial"
    if not item:
        return ""
    return item


def extract_year_text(value: Any) -> str:
    text = clean_text(value)
    match = re.search(r"\b(\d{4})\b", text)
    return match.group(1) if match else ""


def filter_normalized_results(
    rows: list[dict[str, Any]],
    config: SearchConfig,
) -> list[dict[str, Any]]:
    filtered = rows
    relevance_terms = extract_relevance_terms(config.query)
    if relevance_terms:
        filtered = [
            row
            for row in filtered
            if has_relevance_term(row, relevance_terms)
        ]
    if config.require_abstract:
        filtered = [row for row in filtered if row.get("abstract")]
    if config.from_year:
        filtered = [row for row in filtered if extract_year_int(row.get("year")) >= int(config.from_year)]
    if config.to_year:
        filtered = [row for row in filtered if extract_year_int(row.get("year")) <= int(config.to_year)]
    return filtered


def normalize_for_match(value: Any) -> str:
    text = clean_text(value).casefold()
    text = "".join(
        char for char in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(char)
    )
    return text


def extract_relevance_terms(query: str) -> list[str]:
    if not BOOLEAN_QUERY_PATTERN.search(query):
        return []
    raw_parts = re.split(r"\b(?:AND|OR|NOT)\b", query, flags=re.IGNORECASE)
    terms: list[str] = []
    for part in raw_parts:
        term = normalize_for_match(part.strip().strip('"').strip("'").strip("()"))
        if len(term) >= 4:
            terms.append(term)
    return terms


def has_relevance_term(row: dict[str, Any], terms: list[str]) -> bool:
    haystack = normalize_for_match(f"{row.get('title', '')} {row.get('abstract', '')}")
    return any(term in haystack for term in terms)


def extract_year_int(value: Any) -> int:
    try:
        return int(str(value)[:4])
    except Exception:  # noqa: BLE001
        return 0


def post_api_filter_descriptions(config: SearchConfig) -> list[str]:
    descriptions: list[str] = []
    if config.require_abstract:
        descriptions.append(
            "Se excluyen localmente los registros sin `dc_description` porque el caso exige `require_abstract=true`."
        )
    if extract_relevance_terms(config.query):
        descriptions.append(
            "Se excluyen localmente registros que no contienen ningún término sustantivo de la query en `dc_title` o `dc_description`, "
            "porque la API de Redalyc no interpreta de forma confiable cadenas booleanas complejas dentro de `title(...)`."
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
    if config.search_field == "subject":
        warnings.append(
            "En Redalyc, `subject` recupera disciplina o descriptores tematicos. "
            "No equivale a una busqueda por resumen."
        )
    if config.search_field == "title" and BOOLEAN_QUERY_PATTERN.search(config.query):
        warnings.append(
            "La query de Redalyc contiene operadores booleanos. La API no los interpreta "
            "de forma equivalente a OpenAlex/DOAJ; se aplico un filtro local de pertinencia "
            "sobre titulo y dc_description."
        )
    elif config.search_field != "title":
        warnings.append(
            "La API de Redalyc no expone un filtro documentado por resumen. "
            "Al usar un campo distinto de `title`, la logica de recuperacion deja de aproximarse "
            "a `titulo + resumen` y debe justificarse metodologicamente."
        )
    if meta.get("likely_more_available"):
        warnings.append(
            "Redalyc probablemente tiene más resultados que los exportados, pero esta API "
            "no expone un total global confiable en las pruebas actuales."
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
        "search_field": config.search_field,
        "from_year": config.from_year,
        "to_year": config.to_year,
        "require_abstract": config.require_abstract,
        "sampling_threshold": config.sampling_threshold,
        "requested_batch_size": config.batch_size,
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
        "# Bitacora de busqueda Redalyc",
        "",
        f"- Fecha de ejecucion: `{run_at}`",
        f"- Fuente: `Redalyc API`",
        f"- Campo de busqueda: `{config.search_field}`",
        f"- Consulta: `{config.query}`",
        f"- Lote solicitado por llamada: `{config.batch_size}`",
        f"- Lotes observados: `{meta.get('observed_batch_sizes', [])}`",
        f"- Requerir abstract: `{config.require_abstract}`",
        f"- Umbral operativo de muestra: `{config.sampling_threshold}`",
        f"- Filtros: `{json.dumps(filters, ensure_ascii=True)}`",
        f"- Conteo reportado por Redalyc en el ultimo lote: `{meta.get('reported_batch_count', 'No reportado')}`",
        f"- Total estimado por la fuente: `No reportado de forma confiable`",
        f"- Lotes recuperados: `{meta.get('batches_fetched', 'No reportado')}`",
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
        "Esta bitacora documenta una recuperacion automatizada inicial desde la API de Redalyc.",
        "La API documentada permite buscar por un campo a la vez o combinar filtros metadata, pero no expone un filtro por resumen/abstract.",
        "Cuando `dc_description` aparece en la respuesta, se usa como equivalente operativo de resumen para el cribado posterior, no como campo de consulta en la API.",
        "La inclusion final de estudios debe realizarse mediante cribado humano con criterios explicitos.",
        "En las pruebas actuales, Redalyc no expone un total global estable comparable al de OpenAlex o DOAJ.",
        "Por eso, el control principal de volumen se apoya en `max_results`, el historial de refinamiento y el juicio humano.",
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
        print(f"Redalyc request failed: {exc}", file=sys.stderr)
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
        "source": "Redalyc",
        "query": config.query,
        "search_field": config.search_field,
        "config_file": str(config.config_file) if config.config_file else None,
        "from_year": config.from_year,
        "to_year": config.to_year,
        "batch_size_requested": config.batch_size,
        "batch_sizes_observed": meta.get("observed_batch_sizes", []),
        "max_results": config.max_results,
        "sampling_threshold": config.sampling_threshold,
        "require_abstract": config.require_abstract,
        "fetched_results_before_post_filters": len(normalized),
        "exported_results": len(filtered_normalized),
        "filtered_out_after_fetch": filtered_out_count,
        "count": "No reportado",
        "redalyc_reported_batch_count": meta.get("reported_batch_count"),
        "batches_fetched": meta.get("batches_fetched"),
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
