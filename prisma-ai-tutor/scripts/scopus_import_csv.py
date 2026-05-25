#!/usr/bin/env python3
"""Import a manual Scopus CSV export into the PRISMA normalized schema."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from metadata_config import DEFAULT_METADATA_CONFIG_PATH, load_metadata_config
from openalex_search import (
    compute_quality_snapshot,
    ensure_dir,
    load_env_config,
    render_count_lines,
    render_warning_lines,
    resolve_bool_flag,
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


DEFAULT_MAX_RESULTS = 500
DEFAULT_RESULTS_THRESHOLD = 500


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import a Scopus CSV export for PRISMA screening.")
    parser.add_argument("--config-file", help="Path to case .env.")
    parser.add_argument("--csv-file", help="Path to Scopus CSV export.")
    parser.add_argument("--query-file", help="Path to approved Scopus query.")
    parser.add_argument("--require-abstract", action="store_true")
    parser.add_argument("--max-results", type=int)
    parser.add_argument("--out-dir")
    parser.add_argument("--query-output-name")
    parser.add_argument("--metadata-config")
    return parser.parse_args()


def get_field(row: dict[str, str], *names: str) -> str:
    normalized = {key.strip().casefold(): value for key, value in row.items()}
    for name in names:
        value = normalized.get(name.casefold())
        if value:
            return " ".join(value.split())
    return ""


def parse_bool(value: str) -> bool:
    text = value.strip().casefold()
    return text in {"1", "yes", "true", "y"} or "open access" in text


def normalize_row(row: dict[str, str], index: int) -> dict[str, Any]:
    title = get_field(row, "Title", "Document Title", "dc:title")
    year = get_field(row, "Year", "Publication Year")
    doi = get_field(row, "DOI", "prism:doi")
    link = get_field(row, "Link", "URL", "Scopus Link", "prism:url")
    eid = get_field(row, "EID", "eid")
    abstract = get_field(row, "Abstract", "Description", "dc:description")
    open_access = get_field(row, "Open Access", "OpenAccess", "openaccess")
    return {
        "code": f"S{index:03d}",
        "source": "Scopus",
        "source_id": eid,
        "title": title,
        "authors": get_field(row, "Authors", "Author(s)", "dc:creator"),
        "year": year[:4],
        "first_affiliation": get_field(row, "Affiliations", "Affiliation"),
        "country_code": "",
        "country": "",
        "publication_date": get_field(row, "Publication Date", "Date", "Year"),
        "doi": doi,
        "abstract": abstract,
        "journal": get_field(row, "Source title", "Source Title", "Publication Name", "prism:publicationName"),
        "journal_type": "",
        "language": get_field(row, "Language"),
        "document_type": normalize_document_type(get_field(row, "Document Type", "subtypeDescription")),
        "is_oa": parse_bool(open_access),
        "oa_status": open_access,
        "source_is_in_doaj": False,
        "cited_by_count": parse_int(get_field(row, "Cited by", "Cited By", "citedby-count")),
        "primary_url": link,
        "pdf_url": "",
        "openalex_url": "",
        "fulltext_accessible": "Por verificar" if link or doi else "No",
        "abstract_available": bool(abstract),
    }


def normalize_document_type(value: str) -> str:
    item = value.casefold()
    if "article" in item:
        return "article"
    if "review" in item:
        return "review"
    return value


def parse_int(value: str) -> int:
    try:
        return int(value)
    except Exception:  # noqa: BLE001
        return 0


def search_output_dir(run_dir: Path) -> Path:
    return run_dir / "search" / "scopus"


def screening_output_dir(run_dir: Path) -> Path:
    return run_dir / "screening"


def main() -> int:
    args = parse_args()
    config_file = Path(args.config_file).expanduser().resolve() if args.config_file else None
    env_config = load_env_config(config_file)
    try:
        csv_file = resolve_workspace_path(
            resolve_str(args.csv_file, env_config.get("SCOPUS_CSV_FILE")),
            config_file,
            env_config,
        )
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
        metadata_columns = load_metadata_config(metadata_config_file)
    except Exception as exc:  # noqa: BLE001
        print(f"Scopus CSV import configuration failed: {exc}", file=sys.stderr)
        return 2

    query_text = ""
    query_file_raw = resolve_str(args.query_file, env_config.get("SCOPUS_QUERY_FILE"))
    if query_file_raw:
        query_path = resolve_workspace_path(query_file_raw, config_file, env_config)
        query_text = query_path.read_text(encoding="utf-8").strip()

    max_results = max(resolve_int(args.max_results, env_config.get("SCOPUS_MAX_RESULTS"), DEFAULT_MAX_RESULTS), 1)
    threshold = max(resolve_int(None, env_config.get("PRISMA_MAX_RESULTS_THRESHOLD"), DEFAULT_RESULTS_THRESHOLD), 1)
    require_abstract = resolve_bool_flag(args.require_abstract, env_config.get("SCOPUS_REQUIRE_ABSTRACT"), True)

    with csv_file.open(encoding="utf-8-sig", newline="") as handle:
        raw_rows = list(csv.DictReader(handle))
    normalized = [normalize_row(row, index + 1) for index, row in enumerate(raw_rows[:max_results])]
    if require_abstract:
        normalized = [row for row in normalized if row.get("abstract")]

    ensure_dir(out_dir)
    search_dir = search_output_dir(out_dir)
    screening_dir = screening_output_dir(out_dir)
    ensure_dir(search_dir)
    ensure_dir(screening_dir)
    if query_text:
        write_query_file(search_dir / resolve_str(args.query_output_name, env_config.get("SCOPUS_QUERY_OUTPUT_NAME"), "query.txt"), query_text)

    snapshot = compute_quality_snapshot(normalized)
    warnings = []
    if len(raw_rows) > max_results:
        warnings.append("El CSV contiene más filas que SCOPUS_MAX_RESULTS; se importó una muestra acotada.")
    if max_results > threshold:
        warnings.append("SCOPUS_MAX_RESULTS supera el umbral operativo configurado.")
    if require_abstract and len(normalized) < min(len(raw_rows), max_results):
        warnings.append("Se excluyeron filas sin abstract por SCOPUS_REQUIRE_ABSTRACT=true.")

    summary = {
        "source": "Scopus",
        "mode": "manual_csv",
        "csv_file": str(csv_file),
        "query": query_text,
        "config_file": str(config_file) if config_file else None,
        "count": len(raw_rows),
        "exported_results": len(normalized),
        "require_abstract": require_abstract,
        "sampling_warnings": warnings,
        "snapshot": snapshot,
        "metadata_config_file": str(metadata_config_file),
        "screening_columns": metadata_columns.get("screening_columns", []),
        "extraction_columns": metadata_columns.get("extraction_columns", []),
    }
    write_json(search_dir / "raw_results.json", raw_rows)
    write_json(search_dir / "normalized_results.json", normalized)
    write_json(search_dir / "summary.json", summary)
    write_csv(search_dir / "normalized_results.csv", normalized)
    write_screening_matrix(screening_dir / "screening_matrix.md", normalized, metadata_columns.get("screening_columns", []))
    write_screening_matrix_csv(screening_dir / "screening_matrix.csv", normalized, metadata_columns.get("screening_columns", []))
    log = [
        "# Bitacora de importacion Scopus CSV",
        "",
        f"- Fecha de ejecucion: `{datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')}`",
        f"- CSV importado: `{csv_file}`",
        f"- Filas en CSV: `{len(raw_rows)}`",
        f"- Resultados exportados: `{len(normalized)}`",
        f"- Requerir abstract: `{require_abstract}`",
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
    (search_dir / "search_log.md").write_text("\n".join(log), encoding="utf-8")
    refresh_run_outputs(out_dir)
    print(f"Scopus CSV import completed in: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
