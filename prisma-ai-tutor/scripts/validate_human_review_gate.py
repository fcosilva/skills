#!/usr/bin/env python3
"""Validate human approval before closing extraction or quality phases."""

from __future__ import annotations

import argparse
import csv
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path


CODE_CANDIDATES = ("Codigo", "Código", "Codigo estudio", "Código estudio")
REVIEW_CANDIDATES = (
    "Estado de revisión humana",
    "Estado de revision humana",
    "Revisión humana",
    "Revision humana",
    "Estado de revisión",
    "Estado de revision",
)
DEFAULT_ACCEPTED = ("Validado", "Aprobado", "Confirmado", "Revisado humanamente")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check that every extraction/quality row was explicitly validated by a human."
    )
    parser.add_argument("--matrix", required=True, help="CSV or Markdown matrix to validate.")
    parser.add_argument("--phase", required=True, choices=("extraction", "quality"))
    parser.add_argument("--code-column")
    parser.add_argument("--review-column")
    parser.add_argument("--accepted-value", action="append", dest="accepted_values")
    parser.add_argument("--report", help="JSON gate report path.")
    return parser.parse_args()


def normalized(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value or "")
    return "".join(char for char in decomposed if not unicodedata.combining(char)).strip().casefold()


def split_markdown_row(line: str) -> list[str]:
    return [cell.strip().replace(r"\|", "|") for cell in re.split(r"(?<!\\)\|", line.strip()[1:-1])]


def read_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    csv_path = path if path.suffix.casefold() == ".csv" else path.with_suffix(".csv")
    if csv_path.exists():
        with csv_path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            fields = reader.fieldnames or []
            rows = list(reader)
        if any(None in row for row in rows):
            raise ValueError("Malformed CSV: one or more rows have extra columns.")
        return fields, rows
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.startswith("|")]
    if len(lines) < 3:
        raise ValueError("No Markdown table found.")
    fields = split_markdown_row(lines[0])
    rows: list[dict[str, str]] = []
    for line_number, line in enumerate(lines[2:], start=3):
        values = split_markdown_row(line)
        if len(values) != len(fields):
            raise ValueError(f"Malformed Markdown table row at table line {line_number}.")
        rows.append(dict(zip(fields, values)))
    return fields, rows


def choose_column(fields: list[str], requested: str | None, candidates: tuple[str, ...], kind: str) -> str:
    if requested:
        if requested not in fields:
            raise ValueError(f"Requested {kind} column not found: {requested}")
        return requested
    for candidate in candidates:
        if candidate in fields:
            return candidate
    raise ValueError(f"No {kind} column found. Candidates: {', '.join(candidates)}")


def evaluate_gate(
    path: Path,
    phase: str,
    code_column: str | None = None,
    review_column: str | None = None,
    accepted_values: list[str] | None = None,
) -> dict[str, object]:
    fields, rows = read_rows(path)
    if not rows:
        raise ValueError("The review matrix has no data rows.")
    code_field = choose_column(fields, code_column, CODE_CANDIDATES, "study code")
    review_field = choose_column(fields, review_column, REVIEW_CANDIDATES, "human review")
    accepted = {normalized(value) for value in (accepted_values or list(DEFAULT_ACCEPTED))}
    pending_rows: list[dict[str, str]] = []
    status_counts: Counter[str] = Counter()
    codes: set[str] = set()
    for index, row in enumerate(rows, start=1):
        code = row.get(code_field, "").strip()
        if not code:
            raise ValueError(f"Missing study code in data row {index}.")
        codes.add(code)
        status = row.get(review_field, "").strip()
        status_counts[status or "(vacío)"] += 1
        if normalized(status) not in accepted:
            pending_rows.append({"row": str(index), "code": code, "status": status})
    return {
        "phase": phase,
        "matrix": str(path),
        "code_column": code_field,
        "review_column": review_field,
        "accepted_values": sorted(accepted),
        "rows": len(rows),
        "unique_studies": len(codes),
        "status_counts": dict(status_counts),
        "pending_rows": pending_rows,
        "human_validation_complete": not pending_rows,
    }


def main() -> int:
    args = parse_args()
    matrix = Path(args.matrix).expanduser().resolve()
    if not matrix.exists() and not matrix.with_suffix(".csv").exists():
        raise SystemExit(f"Matrix not found: {matrix}")
    try:
        result = evaluate_gate(
            matrix,
            args.phase,
            args.code_column,
            args.review_column,
            args.accepted_values,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    report = Path(args.report).expanduser().resolve() if args.report else matrix.parent / f"phase_{args.phase}_human_review_gate.json"
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Human review complete: {result['human_validation_complete']}")
    print(f"Rows: {result['rows']}; unique studies: {result['unique_studies']}")
    print(f"Report: {report}")
    return 0 if result["human_validation_complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
