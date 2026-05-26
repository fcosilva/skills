#!/usr/bin/env python3
"""Prepare plain-text review files from recovered PDF/HTML full text."""

from __future__ import annotations

import argparse
import csv
import subprocess
from html.parser import HTMLParser
from pathlib import Path

from openalex_search import WORKSPACE_ROOT_KEY, resolve_workspace_path
from run_outputs import refresh_run_outputs


FULLTEXT_KINDS = {"pdf_fulltext", "html_fulltext"}


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.chunks: list[str] = []

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if text:
            self.chunks.append(text)

    def get_text(self) -> str:
        return "\n".join(self.chunks)


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


def load_allowed_paths(download_log: Path) -> set[str]:
    with download_log.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    return {
        str(Path(row.get("local_path", "")).resolve())
        for row in rows
        if row.get("access_kind", "").strip() in FULLTEXT_KINDS and row.get("local_path", "").strip()
    }


def extract_pdf_text(source: Path, destination: Path) -> tuple[str, str]:
    result = subprocess.run(
        ["pdftotext", str(source), str(destination)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return "error", (result.stderr or result.stdout or "pdftotext failed").strip()
    return "prepared", "pdftotext ok"


def extract_html_text(source: Path, destination: Path) -> tuple[str, str]:
    parser = TextExtractor()
    parser.feed(source.read_text(encoding="utf-8", errors="ignore"))
    text = parser.get_text().strip()
    if not text:
        return "error", "No textual content extracted from HTML."
    destination.write_text(text + "\n", encoding="utf-8")
    return "prepared", "html text extracted"


def prepare_one(source: Path, output_dir: Path) -> dict[str, str]:
    destination = output_dir / f"{source.stem}.txt"
    result = {
        "source_path": str(source),
        "output_path": str(destination),
        "status": "",
        "message": "",
    }
    suffix = source.suffix.lower()
    if suffix == ".pdf":
        status, message = extract_pdf_text(source, destination)
    elif suffix in {".html", ".htm"}:
        status, message = extract_html_text(source, destination)
    else:
        status, message = "skipped", f"Unsupported suffix: {suffix}"
    result["status"] = status
    result["message"] = message
    return result


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    fieldnames = ["source_path", "output_path", "status", "message"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_summary(path: Path, output_dir: Path, rows: list[dict[str, str]]) -> None:
    prepared = [row for row in rows if row["status"] == "prepared"]
    skipped = [row for row in rows if row["status"] == "skipped"]
    errors = [row for row in rows if row["status"] == "error"]
    lines = [
        "# Resumen de preparación de texto para revisión",
        "",
        f"- Directorio de salida: `{output_dir}`",
        f"- Archivos procesados: `{len(rows)}`",
        f"- Textos preparados: `{len(prepared)}`",
        f"- Omitidos: `{len(skipped)}`",
        f"- Errores: `{len(errors)}`",
        "",
        "## Identificadores clave",
        "",
        f"- Preparados: `{', '.join(Path(row['output_path']).stem for row in prepared) if prepared else 'ninguno'}`",
        f"- Con error: `{', '.join(Path(row['source_path']).stem for row in errors) if errors else 'ninguno'}`",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


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

    output_dir.mkdir(parents=True, exist_ok=True)
    allowed = load_allowed_paths(download_log) if download_log else None

    rows: list[dict[str, str]] = []
    for source in sorted(input_dir.iterdir()):
        if not source.is_file():
            continue
        if allowed is not None and str(source.resolve()) not in allowed:
            continue
        rows.append(prepare_one(source, output_dir))

    write_csv(log_path, rows)
    write_summary(summary_path, output_dir, rows)
    refresh_run_outputs(infer_run_dir(output_dir, summary_path))
    print(
        f"Prepared {sum(1 for row in rows if row['status'] == 'prepared')} review text files in: {output_dir}"
    )
    print(f"Preparation log: {log_path}")
    print(f"Preparation summary: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
