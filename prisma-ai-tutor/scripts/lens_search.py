#!/usr/bin/env python3
"""Search Lens Scholarly API and export normalized PRISMA results."""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import error, request

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


API_URL = "https://api.lens.org/scholarly/search"
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 100
DEFAULT_MAX_RESULTS = 100
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_DELAY = 2.0
DEFAULT_MAX_RETRY_WAIT = 60.0
DEFAULT_RESULTS_THRESHOLD = 500
DEFAULT_QUERY_FIELDS = ["title", "abstract"]
DEFAULT_INCLUDE_FIELDS = [
    "lens_id",
    "title",
    "abstract",
    "year_published",
    "date_published",
    "publication_type",
    "source",
    "authors",
    "external_ids",
    "open_access",
    "fields_of_study",
    "scholarly_citations_count",
]


@dataclass
class SearchConfig:
    query: str
    from_year: str | None
    to_year: str | None
    publication_type: str | None
    require_abstract: bool
    require_open_access: bool
    page_size: int
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
    parser = argparse.ArgumentParser(description="Run a Lens Scholarly API search and export normalized results.")
    parser.add_argument("query", nargs="?", help="Lens query_string query. Optional with --query-file.")
    parser.add_argument("--query-file", help="Path to a text file containing the Lens query.")
    parser.add_argument(
        "--config-file",
        help=(
            "Path to env-style config. Supported keys: LENS_API_KEY, LENS_QUERY_FILE, "
            "LENS_FROM_YEAR, LENS_TO_YEAR, LENS_PUBLICATION_TYPE, LENS_REQUIRE_ABSTRACT, "
            "LENS_REQUIRE_OPEN_ACCESS, LENS_PAGE_SIZE, LENS_MAX_RESULTS, "
            "PRISMA_MAX_RESULTS_THRESHOLD, LENS_MAX_RETRIES, LENS_RETRY_DELAY, "
            "LENS_MAX_RETRY_WAIT, LENS_OUT_DIR, LENS_QUERY_OUTPUT_NAME, LENS_METADATA_CONFIG."
        ),
    )
    parser.add_argument("--api-key", help="Lens API key.")
    parser.add_argument("--from-year", help="Lower publication year bound in YYYY format.")
    parser.add_argument("--to-year", help="Upper publication year bound in YYYY format.")
    parser.add_argument("--publication-type", help="Lens publication_type filter. Example: journal article.")
    parser.add_argument("--require-abstract", action="store_true")
    parser.add_argument("--require-open-access", action="store_true")
    parser.add_argument("--page-size", type=int, help=f"Results per API page. Default: {DEFAULT_PAGE_SIZE}.")
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
    page_size = min(max(resolve_int(args.page_size, env_config.get("LENS_PAGE_SIZE"), DEFAULT_PAGE_SIZE), 1), MAX_PAGE_SIZE)
    max_results = max(resolve_int(args.max_results, env_config.get("LENS_MAX_RESULTS"), DEFAULT_MAX_RESULTS), 1)
    sampling_threshold = max(
        resolve_int(args.sampling_threshold, env_config.get("PRISMA_MAX_RESULTS_THRESHOLD"), DEFAULT_RESULTS_THRESHOLD),
        1,
    )
    max_retries = max(resolve_int(args.max_retries, env_config.get("LENS_MAX_RETRIES"), DEFAULT_MAX_RETRIES), 0)
    retry_delay = max(resolve_float(args.retry_delay, env_config.get("LENS_RETRY_DELAY"), DEFAULT_RETRY_DELAY), 0.1)
    max_retry_wait = max(
        resolve_float(args.max_retry_wait, env_config.get("LENS_MAX_RETRY_WAIT"), DEFAULT_MAX_RETRY_WAIT),
        0.1,
    )
    out_dir = resolve_workspace_path(
        resolve_str(args.out_dir, env_config.get("LENS_OUT_DIR"), "outputs/lens-search"),
        config_file,
        env_config,
    )
    metadata_config_raw = resolve_str(args.metadata_config, env_config.get("LENS_METADATA_CONFIG"))
    metadata_config_file = (
        resolve_workspace_path(metadata_config_raw, config_file, env_config)
        if metadata_config_raw
        else DEFAULT_METADATA_CONFIG_PATH
    )
    return SearchConfig(
        query=resolve_lens_query(args.query, args.query_file, env_config, config_file),
        from_year=resolve_str(args.from_year, env_config.get("LENS_FROM_YEAR")),
        to_year=resolve_str(args.to_year, env_config.get("LENS_TO_YEAR")),
        publication_type=resolve_str(args.publication_type, env_config.get("LENS_PUBLICATION_TYPE"), "journal article"),
        require_abstract=resolve_bool_flag(args.require_abstract, env_config.get("LENS_REQUIRE_ABSTRACT"), True),
        require_open_access=resolve_bool_flag(args.require_open_access, env_config.get("LENS_REQUIRE_OPEN_ACCESS"), False),
        page_size=page_size,
        max_results=max_results,
        sampling_threshold=sampling_threshold,
        quiet_progress=args.quiet_progress,
        max_retries=max_retries,
        retry_delay=retry_delay,
        max_retry_wait=max_retry_wait,
        api_key=resolve_str(args.api_key, env_config.get("LENS_API_KEY")),
        out_dir=out_dir,
        query_output_name=resolve_str(args.query_output_name, env_config.get("LENS_QUERY_OUTPUT_NAME"), "query.txt"),
        config_file=config_file,
        metadata_config_file=metadata_config_file,
    )


def resolve_lens_query(
    cli_query: str | None,
    query_file: str | None,
    env_config: dict[str, str],
    config_file: Path | None,
) -> str:
    config_query_file = env_config.get("LENS_QUERY_FILE", "").strip() or None
    effective_query_file = query_file or config_query_file
    if cli_query and effective_query_file:
        raise ValueError("Use either a positional query or LENS_QUERY_FILE/--query-file, not both.")
    if effective_query_file:
        query_path = (
            Path(effective_query_file).expanduser().resolve()
            if query_file
            else resolve_workspace_path(effective_query_file, config_file, env_config)
        )
        return query_path.read_text(encoding="utf-8").strip()
    if cli_query:
        return cli_query.strip()
    raise ValueError("A Lens query is required.")


def search_output_dir(run_dir: Path) -> Path:
    return run_dir / "search" / "lens"


def screening_output_dir(run_dir: Path) -> Path:
    return run_dir / "screening"


def build_lens_query(config: SearchConfig) -> dict[str, Any]:
    must: list[dict[str, Any]] = [
        {"query_string": {"query": config.query, "fields": DEFAULT_QUERY_FIELDS}},
    ]
    if config.from_year or config.to_year:
        range_filter: dict[str, str] = {}
        if config.from_year:
            range_filter["gte"] = config.from_year
        if config.to_year:
            range_filter["lte"] = config.to_year
        must.append({"range": {"year_published": range_filter}})
    if config.publication_type:
        must.append({"match": {"publication_type": config.publication_type}})
    if config.require_abstract:
        must.append({"exists": {"field": "abstract"}})
    if config.require_open_access:
        must.append({"match": {"open_access": True}})
    return {"bool": {"must": must}}


def fetch_results(config: SearchConfig) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    raw_rows: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    offset = 0
    total: int | None = None

    while len(rows) < config.max_results:
        batch_size = min(config.page_size, config.max_results - len(rows))
        payload = {
            "query": build_lens_query(config),
            "from": offset,
            "size": batch_size,
            "include": DEFAULT_INCLUDE_FIELDS,
        }
        response = fetch_json_with_retries(payload, config)
        if total is None:
            total = parse_int(response.get("total"))
        data = response.get("data") or []
        if not data:
            break
        raw_rows.extend(data)
        base_index = len(rows)
        rows.extend(normalize_work(item, base_index + index + 1) for index, item in enumerate(data))
        if not config.quiet_progress:
            print(
                f"[Lens] fetched {len(rows)} records "
                f"(Lens reports about {total if total is not None else 'No reportado'}).",
                flush=True,
            )
        if len(data) < batch_size:
            break
        offset += len(data)

    return raw_rows, rows, {"count": total, "query": config.query, "year": year_filter(config)}


def fetch_json_with_retries(payload: dict[str, Any], config: SearchConfig) -> dict[str, Any]:
    if not config.api_key:
        raise ValueError("LENS_API_KEY is required for Lens Scholarly API.")
    attempt = 0
    delay = config.retry_delay
    while True:
        req = request.Request(
            API_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {config.api_key}",
                "Content-Type": "application/json",
                "User-Agent": "PRISMA-AI-Tutor/1.0",
            },
            method="POST",
        )
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
    external_ids = work.get("external_ids") or []
    open_access = work.get("open_access") or {}
    source = work.get("source") or {}
    doi = external_id(external_ids, "doi")
    openalex_id = external_id(external_ids, "openalex")
    pmid = external_id(external_ids, "pmid")
    title = clean_text(work.get("title") or "")
    abstract = clean_text(work.get("abstract") or "")
    year = str(work.get("year_published") or "")
    primary_url = doi_url(doi) or lens_url(work.get("lens_id") or "")
    return {
        "code": f"L{position:03d}",
        "source": "Lens",
        "source_id": work.get("lens_id") or "",
        "title": title,
        "authors": normalize_authors(work.get("authors") or []),
        "year": year,
        "first_affiliation": "",
        "country_code": "",
        "country": "",
        "publication_date": work.get("date_published") or year,
        "doi": doi,
        "abstract": abstract,
        "journal": source.get("title") or source.get("display_name") or source.get("name") or "",
        "journal_type": source.get("type") or "",
        "language": "",
        "document_type": normalize_document_type(work.get("publication_type") or ""),
        "is_oa": bool(open_access),
        "oa_status": open_access.get("colour") or ("open_access" if open_access else ""),
        "source_is_in_doaj": False,
        "cited_by_count": parse_int(work.get("scholarly_citations_count")),
        "primary_url": primary_url,
        "pdf_url": "",
        "openalex_url": openalex_url(openalex_id),
        "fulltext_accessible": "Por verificar" if primary_url else "No",
        "abstract_available": bool(abstract),
        "lens_url": lens_url(work.get("lens_id") or ""),
        "pmid": pmid,
        "lens_fields_of_study": normalize_fields(work.get("fields_of_study") or []),
    }


def normalize_authors(authors: list[Any]) -> str:
    names: list[str] = []
    for author in authors:
        if not isinstance(author, dict):
            continue
        name = author.get("display_name") or author.get("full_name") or author.get("name")
        if name:
            names.append(str(name))
    return "; ".join(names)


def normalize_fields(fields: list[Any]) -> str:
    values: list[str] = []
    for field in fields:
        if isinstance(field, dict):
            value = field.get("name") or field.get("field")
        else:
            value = field
        if value:
            values.append(str(value))
    return "; ".join(values)


def external_id(external_ids: list[Any], wanted_type: str) -> str:
    for item in external_ids:
        if not isinstance(item, dict):
            continue
        if str(item.get("type", "")).casefold() == wanted_type.casefold():
            return str(item.get("value") or "")
    return ""


def normalize_document_type(value: str) -> str:
    lower = value.casefold()
    if "journal article" in lower or lower == "article":
        return "article"
    if "review" in lower:
        return "review"
    if "conference" in lower:
        return "conference"
    if "book" in lower:
        return "book"
    return value


def clean_text(value: str) -> str:
    return " ".join(str(value).split())


def doi_url(doi: str) -> str:
    doi = doi.strip()
    return f"https://doi.org/{doi}" if doi else ""


def lens_url(lens_id: str) -> str:
    lens_id = lens_id.strip()
    return f"https://www.lens.org/lens/scholar/article/{lens_id}" if lens_id else ""


def openalex_url(openalex_id: str) -> str:
    openalex_id = openalex_id.strip()
    if not openalex_id:
        return ""
    if openalex_id.startswith("http"):
        return openalex_id
    return f"https://openalex.org/{openalex_id}"


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


def year_filter(config: SearchConfig) -> str | None:
    if not config.from_year and not config.to_year:
        return None
    start = config.from_year or ""
    end = config.to_year or ""
    if start and end:
        return f"{start}-{end}"
    return start or f"-{end}"


def sampling_warnings(config: SearchConfig, meta: dict[str, Any], exported_count: int) -> list[str]:
    warnings: list[str] = []
    if config.max_results > config.sampling_threshold:
        warnings.append("LENS_MAX_RESULTS supera el umbral operativo configurado.")
    count = meta.get("count")
    if isinstance(count, int) and count > 1000:
        warnings.append(
            "Lens reporta más de 1000 resultados estimados. "
            "Corresponde refinar la query antes del cribado inicial."
        )
    elif isinstance(count, int) and count > config.max_results:
        warnings.append(
            "Lens reporta más resultados que max_results. Si el usuario no aprueba "
            "trabajar con una muestra acotada, corresponde refinar la query."
        )
    if config.require_abstract and exported_count == 0:
        warnings.append("LENS_REQUIRE_ABSTRACT=true dejó la exportación vacía.")
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
        "# Bitacora de busqueda Lens",
        "",
        f"- Fecha de ejecucion: `{datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')}`",
        "- Fuente: `Lens Scholarly API`",
        f"- Consulta Lens: `{config.query}`",
        f"- Campos de búsqueda: `{', '.join(DEFAULT_QUERY_FIELDS)}`",
        f"- Rango de años: `{year_filter(config) or 'sin filtro'}`",
        f"- Tipo documental Lens: `{config.publication_type or 'sin filtro'}`",
        f"- Requerir abstract: `{config.require_abstract}`",
        f"- Requerir acceso abierto: `{config.require_open_access}`",
        f"- API key configurada: `{'si' if config.api_key else 'no'}`",
        f"- Total reportado por Lens: `{meta.get('count', 'No reportado')}`",
        f"- Resultados exportados: `{result_count}`",
        f"- Columnas de cribado: `{json.dumps(metadata_columns.get('screening_columns', []), ensure_ascii=True)}`",
        "",
        "## Nota metodologica",
        "",
        "Lens se usa como fuente programatica opcional con API key institucional o academica.",
        "La query se interpreta con `query_string` sobre `title` y `abstract`, por lo que puede usar booleanos simples.",
        "El solapamiento con otras fuentes se controla en la fusion y deduplicacion posterior mediante DOI y titulo/anio.",
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
        print(f"Invalid Lens configuration: {exc}", file=sys.stderr)
        return 2
    ensure_dir(config.out_dir)
    search_dir = search_output_dir(config.out_dir)
    screening_dir = screening_output_dir(config.out_dir)
    ensure_dir(search_dir)
    ensure_dir(screening_dir)
    write_query_file(search_dir / config.query_output_name, config.query)
    try:
        metadata_columns = load_metadata_config(config.metadata_config_file)
        raw_results, normalized_results, meta = fetch_results(config)
    except Exception as exc:  # noqa: BLE001
        print(f"Lens request failed: {exc}", file=sys.stderr)
        return 1
    snapshot = compute_quality_snapshot(normalized_results)
    warnings = sampling_warnings(config, meta, len(normalized_results))
    summary = {
        "source": "Lens",
        "query": config.query,
        "config_file": str(config.config_file) if config.config_file else None,
        "max_results": config.max_results,
        "count": meta.get("count"),
        "exported_results": len(normalized_results),
        "require_abstract": config.require_abstract,
        "require_open_access": config.require_open_access,
        "publication_type": config.publication_type,
        "sampling_warnings": warnings,
        "snapshot": snapshot,
        "metadata_config_file": str(config.metadata_config_file),
        "screening_columns": metadata_columns.get("screening_columns", []),
        "extraction_columns": metadata_columns.get("extraction_columns", []),
    }
    write_json(search_dir / "raw_results.json", raw_results)
    write_json(search_dir / "normalized_results.json", normalized_results)
    write_json(search_dir / "summary.json", summary)
    write_csv(search_dir / "normalized_results.csv", normalized_results)
    write_screening_matrix(screening_dir / "screening_matrix.md", normalized_results, metadata_columns.get("screening_columns", []))
    write_screening_matrix_csv(screening_dir / "screening_matrix.csv", normalized_results, metadata_columns.get("screening_columns", []))
    log_text = build_search_log_text(config, meta, len(normalized_results), snapshot, metadata_columns, warnings)
    (search_dir / "search_log.md").write_text(log_text, encoding="utf-8")
    print(log_text)
    refresh_run_outputs(config.out_dir)
    print(f"Archivos exportados en: {config.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
