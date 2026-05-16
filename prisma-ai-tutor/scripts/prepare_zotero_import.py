#!/usr/bin/env python3
"""Prepare a Zotero import package from the confirmed screening outputs."""

from __future__ import annotations

import argparse
import csv
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from openalex_search import load_env_config, resolve_workspace_path
from run_outputs import refresh_run_outputs


@dataclass
class ZoteroConfig:
    config_file: Path
    library: str
    collection: str
    attachments_dir: Path
    library_files_dir: Path
    screening_decisions: Path
    screening_matrix: Path
    out_dir: Path


def parse_args() -> ZoteroConfig:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare a Zotero import manifest from the confirmed final screening, "
            "copying PDFs to the Zotero files directory when available."
        )
    )
    parser.add_argument(
        "--config-file",
        required=True,
        help="Env-style configuration file for the case, for example cases/<slug>/case.env.",
    )
    parser.add_argument("--zotero-library", default=None, help="Override ZOTERO_LIBRARY.")
    parser.add_argument("--zotero-collection", default=None, help="Override ZOTERO_COLLECTION.")
    parser.add_argument(
        "--attachments-dir",
        default=None,
        help="Override ZOTERO_ATTACHMENTS_DIR (source directory with PDFs).",
    )
    parser.add_argument(
        "--library-files-dir",
        default=None,
        help="Override ZOTERO_LIBRARY_FILES_DIR (destination directory used by Zotero).",
    )
    parser.add_argument(
        "--screening-decisions",
        default=None,
        help="Override ZOTERO_SCREENING_DECISIONS.",
    )
    parser.add_argument(
        "--screening-matrix",
        default=None,
        help="Override ZOTERO_SCREENING_MATRIX.",
    )
    parser.add_argument(
        "--out-dir",
        default=None,
        help=(
            "Directory for generated Zotero manifests and copy logs. "
            "Default: outputs/<run>/zotero."
        ),
    )

    args = parser.parse_args()
    config_file = Path(args.config_file).expanduser().resolve()
    env_config = load_env_config(config_file)

    library = resolve_required(args.zotero_library, env_config, "ZOTERO_LIBRARY")
    collection = resolve_required(args.zotero_collection, env_config, "ZOTERO_COLLECTION")
    attachments_dir = resolve_workspace_path(
        resolve_required(args.attachments_dir, env_config, "ZOTERO_ATTACHMENTS_DIR"),
        config_file,
        env_config,
    )
    library_files_dir = resolve_workspace_path(
        resolve_required(args.library_files_dir, env_config, "ZOTERO_LIBRARY_FILES_DIR"),
        config_file,
        env_config,
    )
    screening_decisions = resolve_workspace_path(
        resolve_required(args.screening_decisions, env_config, "ZOTERO_SCREENING_DECISIONS"),
        config_file,
        env_config,
    )
    screening_matrix = resolve_workspace_path(
        resolve_required(args.screening_matrix, env_config, "ZOTERO_SCREENING_MATRIX"),
        config_file,
        env_config,
    )
    out_dir = (
        resolve_workspace_path(args.out_dir, config_file, env_config)
        if args.out_dir
        else screening_decisions.parent.parent / "zotero"
    )

    return ZoteroConfig(
        config_file=config_file,
        library=library,
        collection=collection,
        attachments_dir=attachments_dir,
        library_files_dir=library_files_dir,
        screening_decisions=screening_decisions,
        screening_matrix=screening_matrix,
        out_dir=out_dir,
    )


def resolve_required(cli_value: str | None, env_config: dict[str, str], key: str) -> str:
    if cli_value is not None and cli_value.strip():
        return cli_value.strip()
    value = env_config.get(key, "").strip()
    if value:
        return value
    raise ValueError(f"Missing required Zotero configuration value: {key}")


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def read_json_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def find_normalized_results(screening_matrix: Path) -> Path:
    candidates = [
        screening_matrix.parent / "normalized_results.json",
        screening_matrix.parent.parent / "search" / "normalized_results.json",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return screening_matrix.parent.parent / "search" / "normalized_results.json"


def find_source_attachment(attachments_dir: Path, code: str) -> Path | None:
    candidates = sorted(attachments_dir.glob(f"{code}_*"))
    if not candidates:
        return None

    pdf_candidates = [path for path in candidates if path.suffix.lower() == ".pdf"]
    if pdf_candidates:
        return pdf_candidates[0]
    return None


def copy_attachment(source: Path, destination_dir: Path) -> tuple[Path, str]:
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / source.name
    if destination.exists():
        same_size = destination.stat().st_size == source.stat().st_size
        if same_size:
            return destination, "already_present"
    shutil.copy2(source, destination)
    return destination, "copied"


def build_manifest_row(
    matrix_row: dict[str, str],
    decision_row: dict[str, str],
    normalized_row: dict[str, Any] | None,
    zotero_config: ZoteroConfig,
    copied_attachment: Path | None,
    attachment_status: str,
) -> dict[str, Any]:
    normalized_row = normalized_row or {}
    return {
        "code": matrix_row.get("Codigo", ""),
        "title": matrix_row.get("Titulo", ""),
        "author_year": matrix_row.get("Autor/ano", ""),
        "authors": normalized_row.get("authors", ""),
        "year": normalized_row.get("year", ""),
        "publication_date": normalized_row.get("publication_date", ""),
        "first_affiliation": matrix_row.get("Primera afiliacion", ""),
        "country": matrix_row.get("Pais", ""),
        "source": matrix_row.get("Fuente", ""),
        "document_type": matrix_row.get("Tipo documental", ""),
        "doi": matrix_row.get("DOI", ""),
        "abstract": normalized_row.get("abstract", ""),
        "journal": normalized_row.get("journal", ""),
        "language": normalized_row.get("language", ""),
        "open_access": matrix_row.get("Acceso abierto", ""),
        "fulltext_accessible": matrix_row.get("Texto completo accesible", ""),
        "url_doi": matrix_row.get("URL DOI", ""),
        "url_access": matrix_row.get("URL de acceso", ""),
        "url_openalex": matrix_row.get("URL OpenAlex", ""),
        "abstract_available": matrix_row.get("Resumen disponible", ""),
        "decision": decision_row.get("decision", ""),
        "reason": decision_row.get("reason", ""),
        "criterion": decision_row.get("criterion", ""),
        "final_basis": decision_row.get("final_basis", ""),
        "final_note": decision_row.get("final_note", ""),
        "zotero_library": zotero_config.library,
        "zotero_collection": zotero_config.collection,
        "source_attachment": str(find_source_attachment(zotero_config.attachments_dir, matrix_row.get("Codigo", "")) or ""),
        "zotero_attachment_path": str(copied_attachment or ""),
        "attachment_status": attachment_status,
        "source_url": first_nonempty(
            matrix_row.get("URL de acceso", ""),
            matrix_row.get("URL DOI", ""),
            matrix_row.get("URL OpenAlex", ""),
        ),
    }


def first_nonempty(*values: str) -> str:
    for value in values:
        if value and value.strip():
            return value.strip()
    return ""


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def prepare_import(config: ZoteroConfig) -> dict[str, Any]:
    decisions_rows = read_csv_rows(config.screening_decisions)
    matrix_rows = read_csv_rows(config.screening_matrix)
    matrix_by_code = {row.get("Codigo", "").strip(): row for row in matrix_rows}
    normalized_path = find_normalized_results(config.screening_matrix)
    normalized_rows = read_json_rows(normalized_path)
    normalized_by_code = {str(row.get("code", "")).strip(): row for row in normalized_rows}

    included = [
        row for row in decisions_rows
        if row.get("decision", "").strip().lower() == "incluir"
    ]

    manifest_rows: list[dict[str, Any]] = []
    copy_log_rows: list[dict[str, Any]] = []

    for decision_row in included:
        code = decision_row.get("code", "").strip()
        if not code:
            continue
        matrix_row = matrix_by_code.get(code)
        if matrix_row is None:
            raise ValueError(
                f"Code {code} is present in {config.screening_decisions} but missing in "
                f"{config.screening_matrix}."
            )

        source_attachment = find_source_attachment(config.attachments_dir, code)
        copied_attachment: Path | None = None
        attachment_status = "no_local_pdf"

        if source_attachment is not None:
            copied_attachment, attachment_status = copy_attachment(
                source_attachment,
                config.library_files_dir,
            )

        manifest_rows.append(
            build_manifest_row(
                matrix_row,
                decision_row,
                normalized_by_code.get(code),
                config,
                copied_attachment,
                attachment_status,
            )
        )
        copy_log_rows.append(
            {
                "code": code,
                "title": matrix_row.get("Titulo", ""),
                "source_attachment": str(source_attachment or ""),
                "zotero_attachment_path": str(copied_attachment or ""),
                "attachment_status": attachment_status,
            }
        )

    summary = {
        "generated_at": Path(__file__).resolve().name,
        "config_file": str(config.config_file),
        "zotero_library": config.library,
        "zotero_collection": config.collection,
        "attachments_dir": str(config.attachments_dir),
        "library_files_dir": str(config.library_files_dir),
        "screening_decisions": str(config.screening_decisions),
        "screening_matrix": str(config.screening_matrix),
        "included_items": len(included),
        "copied_pdfs": sum(1 for row in copy_log_rows if row["attachment_status"] == "copied"),
        "already_present_pdfs": sum(
            1 for row in copy_log_rows if row["attachment_status"] == "already_present"
        ),
        "missing_local_pdfs": sum(
            1 for row in copy_log_rows if row["attachment_status"] == "no_local_pdf"
        ),
    }

    return {
        "summary": summary,
        "manifest_rows": manifest_rows,
        "copy_log_rows": copy_log_rows,
    }


def main() -> int:
    config = parse_args()
    result = prepare_import(config)

    config.out_dir.mkdir(parents=True, exist_ok=True)

    manifest_json = config.out_dir / "zotero_import_manifest.json"
    manifest_csv = config.out_dir / "zotero_import_manifest.csv"
    copy_log_csv = config.out_dir / "zotero_attachment_copy_log.csv"
    summary_json = config.out_dir / "zotero_import_summary.json"

    write_json(manifest_json, result["manifest_rows"])
    write_csv(manifest_csv, result["manifest_rows"])
    write_csv(copy_log_csv, result["copy_log_rows"])
    write_json(summary_json, result["summary"])
    refresh_run_outputs(config.out_dir.parent)

    print(f"Prepared Zotero manifest for {result['summary']['included_items']} items.")
    print(f"Library: {config.library}")
    print(f"Collection: {config.collection}")
    print(f"Manifest JSON: {manifest_json}")
    print(f"Manifest CSV: {manifest_csv}")
    print(f"Attachment copy log: {copy_log_csv}")
    print(f"Summary JSON: {summary_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
