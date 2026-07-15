#!/usr/bin/env python3
"""Prepare plain-text review files from recovered PDF/HTML full text."""

from __future__ import annotations

import argparse
import csv
import os
import re
import shutil
import subprocess
from pathlib import Path

from fulltext_utils import bibliographic_identity, inspect_html, is_pdf_payload
from openalex_search import WORKSPACE_ROOT_KEY, resolve_workspace_path
from run_outputs import refresh_run_outputs


FULLTEXT_KINDS = {"pdf_fulltext", "html_fulltext"}
DEFAULT_MIN_WORDS = 200


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create plain-text review files from recovered PDF/HTML full text for "
            "assisted reading during final screening."
        )
    )
    parser.add_argument("--input-dir", required=True, help="Directory with recovered PDF/HTML files.")
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory where extracted .txt files will be written.",
    )
    parser.add_argument(
        "--download-log",
        help=(
            "Optional CSV log from download_fulltext.py. When provided, only "
            "pdf_fulltext and html_fulltext entries are prepared."
        ),
    )
    parser.add_argument(
        "--matrix",
        help="Optional screening matrix Markdown or CSV to synchronize from prepared text.",
    )
    parser.add_argument(
        "--decisions",
        help="Optional final/focused decisions CSV defining every code that must be synchronized.",
    )
    parser.add_argument(
        "--quarantine-dir",
        help="Directory for readable files whose bibliographic identity is mismatched.",
    )
    parser.add_argument("--resume", action="store_true", help="Reuse already prepared, identity-confirmed text.")
    parser.add_argument("--progress-every", type=int, default=25)
    parser.add_argument(
        "--min-words",
        type=int,
        default=DEFAULT_MIN_WORDS,
        help=f"Minimum extracted words required for legibility. Default: {DEFAULT_MIN_WORDS}.",
    )
    parser.add_argument(
        "--log",
        help="Optional CSV log path. Default: fulltext_review_text_log.csv next to the output directory.",
    )
    parser.add_argument(
        "--summary",
        help="Optional Markdown summary path. Default: fulltext_review_text_summary.md next to the output directory.",
    )
    parser.add_argument(
        "--workspace-root",
        help=(
            "Optional workspace root used to resolve relative CLI paths. "
            f"Equivalent to {WORKSPACE_ROOT_KEY} for CLI-only scripts."
        ),
    )
    return parser.parse_args()


def load_allowed_paths(download_log: Path) -> dict[str, dict[str, str]]:
    with download_log.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    return {
        str(Path(row.get("local_path", "")).resolve()): row
        for row in rows
        if row.get("access_kind", "").strip() in FULLTEXT_KINDS and row.get("local_path", "").strip()
    }


def load_matrix_metadata(matrix_path: Path) -> dict[str, dict[str, str]]:
    csv_path = matrix_path if matrix_path.suffix.lower() == ".csv" else matrix_path.with_suffix(".csv")
    if not csv_path.exists():
        raise SystemExit("Bibliographic identity validation requires the CSV matrix representation.")
    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or "Codigo" not in reader.fieldnames:
            raise SystemExit("Unexpected screening matrix schema: missing Codigo.")
        rows = list(reader)
    malformed = [index for index, row in enumerate(rows, start=2) if None in row]
    if malformed:
        raise SystemExit(f"Malformed screening matrix CSV rows: {malformed[:10]}")
    return {row["Codigo"].strip(): row for row in rows if row.get("Codigo", "").strip()}


def load_decision_codes(path: Path) -> set[str]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return {
            row.get("code", "").strip()
            for row in csv.DictReader(handle)
            if row.get("code", "").strip() and row.get("decision", "").strip() in {"Incluir", "Dudoso"}
        }


def extract_pdf_text(source: Path, destination: Path, min_words: int) -> tuple[str, str, int]:
    if not is_pdf_payload(source.read_bytes()[:1024]):
        return "error", "File extension is PDF but PDF magic signature is absent.", 0
    result = subprocess.run(
        ["pdftotext", str(source), str(destination)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return "error", (result.stderr or result.stdout or "pdftotext failed").strip(), 0
    text = destination.read_text(encoding="utf-8", errors="ignore").strip()
    words = len(re.findall(r"\b\w+\b", text, flags=re.UNICODE))
    if words < min_words:
        destination.unlink(missing_ok=True)
        return "error", f"Extracted text below legibility threshold: {words} < {min_words} words.", words
    return "prepared", "pdftotext ok; PDF signature and extracted text verified.", words


def extract_html_text(source: Path, destination: Path, min_words: int) -> tuple[str, str, int]:
    inspection = inspect_html(source.read_bytes(), source.as_uri())
    text = inspection.visible_text.strip()
    if not inspection.full_article:
        return (
            "error",
            f"HTML does not contain a verified full article body; words={inspection.word_count}; sections={inspection.section_score}.",
            inspection.word_count,
        )
    if inspection.word_count < min_words:
        return "error", f"Extracted HTML below legibility threshold: {inspection.word_count} words.", inspection.word_count
    destination.write_text(text + "\n", encoding="utf-8")
    return "prepared", "HTML scholarly body and extracted text verified.", inspection.word_count


def prepare_one(
    source: Path,
    output_dir: Path,
    metadata: dict[str, str],
    min_words: int,
    expected: dict[str, str] | None = None,
    quarantine_dir: Path | None = None,
) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / f"{source.stem}.txt"
    result = {
        "source_path": str(source),
        "output_path": str(destination),
        "code": metadata.get("code", ""),
        "access_kind": metadata.get("access_kind", ""),
        "status": "",
        "message": "",
        "word_count": "0",
        "identity_status": "not_checked",
        "identity_evidence": "",
        "quarantine_path": "",
    }
    suffix = source.suffix.lower()
    if suffix == ".pdf":
        status, message, words = extract_pdf_text(source, destination, min_words)
    elif suffix in {".html", ".htm"}:
        status, message, words = extract_html_text(source, destination, min_words)
    else:
        status, message, words = "skipped", f"Unsupported suffix: {suffix}", 0
    result["status"] = status
    result["message"] = message
    result["word_count"] = str(words)
    if status == "prepared" and expected is not None:
        extracted = destination.read_text(encoding="utf-8", errors="ignore")
        observed_title = ""
        if suffix in {".html", ".htm"}:
            observed_title = inspect_html(source.read_bytes(), source.as_uri()).title
        identity_status, identity_evidence = bibliographic_identity(
            expected_title=expected.get("Titulo", ""),
            expected_doi=expected.get("DOI", "") or expected.get("URL DOI", ""),
            expected_author_year=expected.get("Autor/ano", "") or expected.get("Autor/año", ""),
            observed_text=extracted,
            observed_title=observed_title,
        )
        result["identity_status"] = identity_status
        result["identity_evidence"] = identity_evidence
        if identity_status != "confirmed":
            destination.unlink(missing_ok=True)
            result["status"] = f"identity_{identity_status}"
            result["message"] = "Readable content rejected because bibliographic identity was not confirmed."
            if identity_status == "mismatch" and quarantine_dir is not None:
                quarantine_dir.mkdir(parents=True, exist_ok=True)
                quarantine_path = quarantine_dir / source.name
                if source.resolve() != quarantine_path.resolve():
                    shutil.move(str(source), str(quarantine_path))
                result["quarantine_path"] = str(quarantine_path)
    return result


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    fieldnames = [
        "code", "source_path", "output_path", "access_kind",
        "status", "word_count", "identity_status", "identity_evidence",
        "quarantine_path", "message",
    ]
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temporary, path)


def write_summary(path: Path, output_dir: Path, rows: list[dict[str, str]]) -> None:
    prepared = [row for row in rows if row["status"] == "prepared"]
    skipped = [row for row in rows if row["status"] == "skipped"]
    errors = [row for row in rows if row["status"] not in {"prepared", "skipped"}]
    mismatches = [row for row in rows if row["status"] == "identity_mismatch"]
    unconfirmed = [row for row in rows if row["status"] == "identity_insufficient"]
    lines = [
        "# Resumen de preparación de texto para revisión",
        "",
        f"- Directorio de salida: `{output_dir}`",
        f"- Archivos procesados: `{len(rows)}`",
        f"- Textos preparados: `{len(prepared)}`",
        f"- Omitidos: `{len(skipped)}`",
        f"- No preparados por error o identidad: `{len(errors)}`",
        f"- Identidad incompatible (cuarentena): `{len(mismatches)}`",
        f"- Identidad insuficiente: `{len(unconfirmed)}`",
        "",
        "## Identificadores clave",
        "",
        f"- Preparados: `{', '.join(Path(row['output_path']).stem for row in prepared) if prepared else 'ninguno'}`",
        f"- Con error: `{', '.join(Path(row['source_path']).stem for row in errors) if errors else 'ninguno'}`",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def markdown_cell(value: str) -> str:
    return value.replace("\r", " ").replace("\n", " ").replace("|", r"\|")


def synchronize_matrix(matrix_path: Path, target_codes: set[str], prepared_codes: set[str]) -> int:
    csv_path = matrix_path if matrix_path.suffix.lower() == ".csv" else matrix_path.with_suffix(".csv")
    md_path = matrix_path if matrix_path.suffix.lower() == ".md" else matrix_path.with_suffix(".md")
    if not csv_path.exists():
        raise SystemExit("Matrix synchronization requires the CSV representation.")
    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames
        rows = list(reader)
    if not fields or "Codigo" not in fields or "Texto completo accesible" not in fields:
        raise SystemExit("Unexpected screening matrix schema.")
    if any(None in row for row in rows):
        raise SystemExit("Malformed screening matrix CSV: one or more rows have extra columns.")
    codes = [row.get("Codigo", "").strip() for row in rows]
    duplicates = sorted({code for code in codes if code and codes.count(code) > 1})
    if duplicates:
        raise SystemExit(f"Duplicate Codigo values in screening matrix: {', '.join(duplicates[:10])}")
    missing = sorted(target_codes - set(codes))
    if missing:
        raise SystemExit(f"Decision codes missing from screening matrix: {', '.join(missing[:10])}")
    changed = 0
    for row in rows:
        code = row["Codigo"].strip()
        if code in target_codes:
            value = "Si" if code in prepared_codes else "No confirmado"
            if row["Texto completo accesible"] != value:
                row["Texto completo accesible"] = value
                changed += 1
    csv_tmp = csv_path.with_suffix(".csv.tmp")
    md_tmp = md_path.with_suffix(".md.tmp")
    with csv_tmp.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    with md_tmp.open("w", encoding="utf-8") as handle:
        handle.write("# Matriz de cribado (seleccion de estudios)\n\n")
        handle.write("| " + " | ".join(fields) + " |\n")
        handle.write("|" + "|".join("---" for _ in fields) + "|\n")
        for row in rows:
            handle.write("| " + " | ".join(markdown_cell(row[field]) for field in fields) + " |\n")
    csv_backup = csv_path.with_name(csv_path.name + ".bak.tmp")
    md_backup = md_path.with_name(md_path.name + ".bak.tmp")
    if csv_path.exists():
        shutil.copy2(csv_path, csv_backup)
    if md_path.exists():
        shutil.copy2(md_path, md_backup)
    try:
        os.replace(csv_tmp, csv_path)
        os.replace(md_tmp, md_path)
    except Exception:
        if csv_backup.exists():
            os.replace(csv_backup, csv_path)
        if md_backup.exists():
            os.replace(md_backup, md_path)
        raise
    finally:
        csv_tmp.unlink(missing_ok=True)
        md_tmp.unlink(missing_ok=True)
        csv_backup.unlink(missing_ok=True)
        md_backup.unlink(missing_ok=True)
    return changed


def infer_run_dir(output_dir: Path, summary_path: Path) -> Path:
    if summary_path.parent.name == "fulltext":
        return summary_path.parent.parent
    if output_dir.parent.name == "fulltext":
        return output_dir.parent.parent
    return output_dir.parent


def main() -> int:
    args = parse_args()
    env_config = {WORKSPACE_ROOT_KEY: args.workspace_root} if args.workspace_root else None
    input_dir = resolve_workspace_path(args.input_dir, None, env_config)
    output_dir = resolve_workspace_path(args.output_dir, None, env_config)
    download_log = (
        resolve_workspace_path(args.download_log, None, env_config)
        if args.download_log
        else None
    )
    matrix_path = (
        resolve_workspace_path(args.matrix, None, env_config)
        if args.matrix
        else None
    )
    decisions_path = (
        resolve_workspace_path(args.decisions, None, env_config)
        if args.decisions
        else None
    )
    log_path = (
        resolve_workspace_path(args.log, None, env_config)
        if args.log
        else output_dir.parent / "fulltext_review_text_log.csv"
    )
    summary_path = (
        resolve_workspace_path(args.summary, None, env_config)
        if args.summary
        else output_dir.parent / "fulltext_review_text_summary.md"
    )

    if not input_dir.exists():
        raise SystemExit(f"Input directory not found: {input_dir}")
    if download_log and not download_log.exists():
        raise SystemExit(f"Download log not found: {download_log}")
    if matrix_path and not matrix_path.exists():
        raise SystemExit(f"Matrix not found: {matrix_path}")
    if decisions_path and not decisions_path.exists():
        raise SystemExit(f"Decisions file not found: {decisions_path}")

    output_dir.mkdir(parents=True, exist_ok=True)
    allowed = load_allowed_paths(download_log) if download_log else None
    matrix_metadata = load_matrix_metadata(matrix_path) if matrix_path else {}
    quarantine_dir = (
        resolve_workspace_path(args.quarantine_dir, None, env_config)
        if args.quarantine_dir
        else input_dir / "quarantine_bibliographic_mismatch"
    )

    previous: dict[str, dict[str, str]] = {}
    if args.resume and log_path.exists():
        with log_path.open(encoding="utf-8-sig", newline="") as handle:
            previous = {row.get("source_path", ""): row for row in csv.DictReader(handle)}

    rows: list[dict[str, str]] = []
    for source in sorted(input_dir.iterdir()):
        if not source.is_file():
            continue
        source_key = str(source.resolve())
        if allowed is not None and source_key not in allowed:
            continue
        metadata = allowed.get(source_key, {}) if allowed is not None else {}
        cached = previous.get(str(source)) or previous.get(source_key)
        if (
            cached
            and cached.get("status") == "prepared"
            and cached.get("identity_status") in {"confirmed", "not_checked"}
            and Path(cached.get("output_path", "")).is_file()
        ):
            rows.append(cached)
        else:
            code = metadata.get("code", "").strip()
            if matrix_path and not code:
                raise SystemExit(f"Download log entry lacks code for recovered file: {source}")
            expected = matrix_metadata.get(code) if matrix_path else None
            if matrix_path and code and expected is None:
                raise SystemExit(f"Code missing from screening matrix during identity validation: {code}")
            rows.append(
                prepare_one(
                    source,
                    output_dir,
                    metadata,
                    max(args.min_words, 0),
                    expected=expected,
                    quarantine_dir=quarantine_dir,
                )
            )
        write_csv(log_path, rows)
        if args.progress_every and len(rows) % max(args.progress_every, 1) == 0:
            print(f"Prepared/checked {len(rows)} source files...", flush=True)

    write_csv(log_path, rows)
    write_summary(summary_path, output_dir, rows)
    if matrix_path and allowed is not None:
        target_codes = load_decision_codes(decisions_path) if decisions_path else {
            metadata.get("code", "").strip()
            for metadata in allowed.values()
            if metadata.get("code", "").strip()
        }
        prepared_codes = {
            row["code"].strip()
            for row in rows
            if row["status"] == "prepared" and row["code"].strip()
        }
        changed = synchronize_matrix(matrix_path, target_codes, prepared_codes)
        print(f"Synchronized full-text accessibility for {changed} matrix rows.")
    refresh_run_outputs(infer_run_dir(output_dir, summary_path))
    print(
        f"Prepared {sum(1 for row in rows if row['status'] == 'prepared')} review text files in: {output_dir}"
    )
    print(f"Preparation log: {log_path}")
    print(f"Preparation summary: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
