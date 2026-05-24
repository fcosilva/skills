#!/usr/bin/env python3
"""Merge normalized search results from multiple sources into one screening set."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from metadata_config import DEFAULT_METADATA_CONFIG_PATH, load_metadata_config
from openalex_search import (
    ensure_dir,
    load_env_config,
    resolve_str,
    resolve_workspace_path,
    write_csv,
    write_json,
    write_screening_matrix,
    write_screening_matrix_csv,
)
from run_outputs import refresh_run_outputs


DEFAULT_SOURCES = ["openalex", "doaj"]


@dataclass
class MergeConfig:
    run_dir: Path
    sources: list[str]
    metadata_config_file: Path
    config_file: Path | None


def parse_args() -> MergeConfig:
    parser = argparse.ArgumentParser(
        description=(
            "Merge normalized search results from one or more source folders "
            "inside outputs/<corrida>/search/ and regenerate the common screening matrix."
        )
    )
    parser.add_argument(
        "--run-dir",
        required=True,
        help="Run directory, for example outputs/mi-corrida.",
    )
    parser.add_argument(
        "--config-file",
        help=(
            "Optional env-style configuration file. Supports "
            "PRISMA_AI_TUTOR_WORKSPACE_ROOT and MERGE_METADATA_CONFIG."
        ),
    )
    parser.add_argument(
        "--source",
        action="append",
        dest="sources",
        help=(
            "Source folder to include under search/<source>/, for example openalex, doaj, scielo. "
            "Repeat the flag to include more than one source. Default: openalex + doaj."
        ),
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
    run_dir = resolve_workspace_path(args.run_dir, config_file, env_config)
    sources = normalize_sources(args.sources or DEFAULT_SOURCES)
    metadata_config_raw = resolve_str(args.metadata_config, env_config.get("MERGE_METADATA_CONFIG"))
    metadata_config_file = (
        resolve_workspace_path(metadata_config_raw, config_file, env_config)
        if metadata_config_raw
        else DEFAULT_METADATA_CONFIG_PATH
    )

    return MergeConfig(
        run_dir=run_dir,
        sources=sources,
        metadata_config_file=metadata_config_file,
        config_file=config_file,
    )


def normalize_sources(values: list[str]) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for value in values:
        item = value.strip().lower()
        if not item or item in seen:
            continue
        seen.add(item)
        normalized.append(item)
    return normalized


def search_dir(run_dir: Path) -> Path:
    return run_dir / "search"


def screening_dir(run_dir: Path) -> Path:
    return run_dir / "screening"


def load_rows(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_source_rows(run_dir: Path, source: str) -> tuple[list[dict[str, Any]], Path]:
    path = search_dir(run_dir) / source / "normalized_results.json"
    if not path.exists():
        raise FileNotFoundError(f"Missing source results: {path}")
    rows = load_rows(path)
    return rows, path


def merge_rows(source_rows: list[tuple[str, list[dict[str, Any]]]]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    merged: list[dict[str, Any]] = []
    merge_log: list[dict[str, str]] = []
    seen_by_doi: dict[str, int] = {}
    seen_by_title_year: dict[str, int] = {}

    for source, rows in source_rows:
        for row in rows:
            doi_key = normalize_doi(row.get("doi", ""))
            title_year_key = normalize_title_year(row.get("title", ""), row.get("year", ""))

            if doi_key and doi_key in seen_by_doi:
                kept = merged[seen_by_doi[doi_key]]
                merge_log.append(
                    build_merge_log_entry(
                        row,
                        source,
                        "duplicate_doi",
                        kept.get("code", ""),
                        kept.get("source", ""),
                    )
                )
                continue

            if title_year_key and title_year_key in seen_by_title_year:
                kept = merged[seen_by_title_year[title_year_key]]
                merge_log.append(
                    build_merge_log_entry(
                        row,
                        source,
                        "duplicate_title_year",
                        kept.get("code", ""),
                        kept.get("source", ""),
                    )
                )
                continue

            merged.append(dict(row))
            index = len(merged) - 1
            if doi_key:
                seen_by_doi[doi_key] = index
            if title_year_key:
                seen_by_title_year[title_year_key] = index
            merge_log.append(
                build_merge_log_entry(row, source, "kept", row.get("code", ""), row.get("source", ""))
            )

    renumbered = renumber_rows(merged)
    return renumbered, merge_log


def normalize_doi(value: str) -> str:
    value = value.strip().lower()
    value = value.removeprefix("https://doi.org/")
    return value


def normalize_title_year(title: str, year: Any) -> str:
    title_key = re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", title.lower())).strip()
    year_key = str(year).strip()
    if not title_key:
        return ""
    return f"{title_key}::{year_key}"


def build_merge_log_entry(
    row: dict[str, Any],
    source: str,
    status: str,
    kept_code: str,
    kept_source: str,
) -> dict[str, str]:
    return {
        "incoming_code": str(row.get("code", "")),
        "incoming_source": source,
        "incoming_title": str(row.get("title", "")),
        "incoming_year": str(row.get("year", "")),
        "incoming_doi": str(row.get("doi", "")),
        "status": status,
        "kept_code": kept_code,
        "kept_source": kept_source,
    }


def renumber_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    renumbered: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        updated = dict(row)
        updated["code"] = f"M{index:03d}"
        renumbered.append(updated)
    return renumbered


def harmonize_row_fields(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not rows:
        return rows
    field_order: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row.keys():
            if key in seen:
                continue
            seen.add(key)
            field_order.append(key)
    harmonized: list[dict[str, Any]] = []
    for row in rows:
        harmonized.append({key: row.get(key, "") for key in field_order})
    return harmonized


def build_summary(
    config: MergeConfig,
    source_rows: list[tuple[str, list[dict[str, Any]]]],
    merged_rows: list[dict[str, Any]],
    merge_log: list[dict[str, str]],
) -> dict[str, Any]:
    per_source = {source: len(rows) for source, rows in source_rows}
    removed = sum(1 for row in merge_log if row["status"] != "kept")
    return {
        "sources": config.sources,
        "config_file": str(config.config_file) if config.config_file else None,
        "per_source_counts": per_source,
        "merged_results": len(merged_rows),
        "duplicates_removed": removed,
        "dedupe_policy": [
            "doi_exact",
            "title_year_normalized",
        ],
    }


def build_merge_log_markdown(
    config: MergeConfig,
    source_rows: list[tuple[str, list[dict[str, Any]]]],
    merged_rows: list[dict[str, Any]],
    merge_log: list[dict[str, str]],
) -> str:
    summary = build_summary(config, source_rows, merged_rows, merge_log)
    lines = [
        "# Bitacora de fusion de fuentes",
        "",
        f"- Fuentes incluidas: `{', '.join(summary['sources'])}`",
        f"- Registros finales fusionados: `{summary['merged_results']}`",
        f"- Duplicados removidos: `{summary['duplicates_removed']}`",
        "",
        "## Conteo por fuente antes de fusionar",
        "",
    ]
    for source, count in summary["per_source_counts"].items():
        lines.append(f"- `{source}`: `{count}`")

    lines.extend(
        [
            "",
            "## Politica de deduplicacion",
            "",
            "- primero por DOI exacto normalizado;",
            "- luego por combinacion normalizada de titulo + año.",
            "",
            "## Tabla de decisiones de fusion",
            "",
            "| incoming_code | incoming_source | incoming_title | incoming_year | incoming_doi | status | kept_code | kept_source |",
            "|---|---|---|---|---|---|---|---|",
        ]
    )
    for row in merge_log:
        values = [
            escape_pipe(row["incoming_code"]),
            escape_pipe(row["incoming_source"]),
            escape_pipe(row["incoming_title"]),
            escape_pipe(row["incoming_year"]),
            escape_pipe(row["incoming_doi"]),
            escape_pipe(row["status"]),
            escape_pipe(row["kept_code"]),
            escape_pipe(row["kept_source"]),
        ]
        lines.append("| " + " | ".join(values) + " |")
    lines.append("")
    return "\n".join(lines)


def escape_pipe(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ").strip()


def main() -> int:
    try:
        config = parse_args()
        metadata_columns = load_metadata_config(config.metadata_config_file)
    except Exception as exc:  # noqa: BLE001
        print(f"Merge configuration failed: {exc}", file=sys.stderr)
        return 2

    source_rows: list[tuple[str, list[dict[str, Any]]]] = []
    try:
        for source in config.sources:
            rows, _ = read_source_rows(config.run_dir, source)
            source_rows.append((source, rows))
    except Exception as exc:  # noqa: BLE001
        print(f"Merge input failed: {exc}", file=sys.stderr)
        return 1

    merged_rows, merge_log = merge_rows(source_rows)
    merged_rows = harmonize_row_fields(merged_rows)
    summary = build_summary(config, source_rows, merged_rows, merge_log)

    search_root = search_dir(config.run_dir)
    screening_root = screening_dir(config.run_dir)
    ensure_dir(search_root)
    ensure_dir(screening_root)

    write_json(search_root / "merged_normalized_results.json", merged_rows)
    write_csv(search_root / "merged_normalized_results.csv", merged_rows)
    write_json(search_root / "merged_summary.json", summary)
    (search_root / "source_merge_log.md").write_text(
        build_merge_log_markdown(config, source_rows, merged_rows, merge_log),
        encoding="utf-8",
    )
    with (search_root / "source_merge_log.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "incoming_code",
                "incoming_source",
                "incoming_title",
                "incoming_year",
                "incoming_doi",
                "status",
                "kept_code",
                "kept_source",
            ],
        )
        writer.writeheader()
        writer.writerows(merge_log)

    write_screening_matrix(
        screening_root / "screening_matrix.md",
        merged_rows,
        metadata_columns.get("screening_columns", []),
    )
    write_screening_matrix_csv(
        screening_root / "screening_matrix.csv",
        merged_rows,
        metadata_columns.get("screening_columns", []),
    )

    refresh_run_outputs(config.run_dir)
    print(f"Fusion completada en: {config.run_dir}")
    print(json.dumps(summary, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
