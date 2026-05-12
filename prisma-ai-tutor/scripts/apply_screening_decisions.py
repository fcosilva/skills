#!/usr/bin/env python3
"""Apply screening decisions to the generated screening matrix."""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from datetime import datetime
from pathlib import Path

from openalex_search import WORKSPACE_ROOT_KEY, resolve_workspace_path


FINAL_COLUMNS = ["Base de decision final", "Observacion final"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Update the generated screening_matrix.md with decisions stored in a CSV file."
        )
    )
    parser.add_argument(
        "--matrix",
        required=True,
        help="Path to the screening matrix to update.",
    )
    parser.add_argument(
        "--decisions",
        required=True,
        help="CSV file with decision updates.",
    )
    parser.add_argument(
        "--summary",
        help=(
            "Optional path for the screening summary Markdown. "
            "Default: derived from the decisions filename, for example "
            "screening_summary_initial.md next to screening_decisions_initial.csv."
        ),
    )
    parser.add_argument(
        "--matrix-csv",
        help=(
            "Optional path for the screening matrix CSV. "
            "Default: screening_matrix.csv next to the Markdown matrix."
        ),
    )
    parser.add_argument(
        "--workspace-root",
        help=(
            "Optional workspace root used to resolve relative CLI paths. "
            f"Equivalent to {WORKSPACE_ROOT_KEY} for CLI-only scripts."
        ),
    )
    return parser.parse_args()


def load_decisions(path: Path) -> tuple[dict[str, dict[str, str]], list[dict[str, str]]]:
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    decisions: dict[str, dict[str, str]] = {}
    for row in rows:
        code = row.get("code", "").strip()
        if not code:
            continue
        decisions[code] = {
            "decision": row.get("decision", "").strip(),
            "reason": row.get("reason", "").strip(),
            "criterion": row.get("criterion", "").strip(),
            "full_text": row.get("full_text", "").strip(),
            "final_basis": row.get("final_basis", "").strip(),
            "final_note": row.get("final_note", "").strip(),
        }
    return decisions, rows


def update_matrix(matrix_path: Path, decisions: dict[str, dict[str, str]]) -> str:
    lines = matrix_path.read_text(encoding="utf-8").splitlines()
    updated: list[str] = []
    decision_idx: int | None = None
    reason_idx: int | None = None
    criterion_idx: int | None = None
    full_text_idx: int | None = None
    final_basis_idx: int | None = None
    final_note_idx: int | None = None
    extend_separator = False

    for line in lines:
        if line.startswith("| Codigo |") or line.startswith("| Código |"):
            parts = [part.strip() for part in line.strip().split("|")]
            columns = parts[1:-1]
            if "Base de decision final" not in columns:
                columns.extend(FINAL_COLUMNS)
                extend_separator = True
            try:
                decision_idx = columns.index("Decision") + 1
                reason_idx = columns.index("Motivo de decision") + 1
                criterion_idx = columns.index("Criterio aplicado") + 1
                full_text_idx = columns.index("Revisar texto completo") + 1
                final_basis_idx = columns.index("Base de decision final") + 1
                final_note_idx = columns.index("Observacion final") + 1
            except ValueError:
                decision_idx = reason_idx = criterion_idx = full_text_idx = None
                final_basis_idx = final_note_idx = None
            updated.append("| " + " | ".join(columns) + " |")
            continue

        if extend_separator and line.startswith("|---"):
            parts = [part.strip() for part in line.strip().split("|")]
            columns = parts[1:-1]
            columns.extend(["---", "---"])
            updated.append("|" + "|".join(columns) + "|")
            extend_separator = False
            continue

        if not line.startswith("| E"):
            updated.append(line)
            continue

        parts = [part.strip() for part in line.strip().split("|")]
        if len(parts) < 12:
            updated.append(line)
            continue
        if final_basis_idx is not None and final_note_idx is not None:
            required_len = final_note_idx + 2
            while len(parts) < required_len:
                parts.insert(-1, "")

        code = parts[1]
        decision = decisions.get(code)
        if not decision:
            updated.append(line)
            continue

        if None in {decision_idx, reason_idx, criterion_idx, full_text_idx}:
            if len(parts) >= 12:
                decision_idx, reason_idx, criterion_idx, full_text_idx = 7, 8, 9, 10
            else:
                updated.append(line)
                continue

        parts[decision_idx] = decision["decision"] or parts[decision_idx]
        parts[reason_idx] = escape_md(decision["reason"]) or parts[reason_idx]
        parts[criterion_idx] = escape_md(decision["criterion"]) or parts[criterion_idx]
        parts[full_text_idx] = decision["full_text"] or parts[full_text_idx]
        if final_basis_idx is not None:
            parts[final_basis_idx] = escape_md(decision["final_basis"]) or parts[final_basis_idx]
        if final_note_idx is not None:
            parts[final_note_idx] = escape_md(decision["final_note"]) or parts[final_note_idx]
        updated.append("| " + " | ".join(parts[1:-1]) + " |")

    text = "\n".join(updated) + "\n"
    matrix_path.write_text(text, encoding="utf-8")
    return text


def escape_md(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ").strip()


def collect_ids(rows: list[dict[str, str]], decision: str) -> list[str]:
    return [row.get("code", "").strip() for row in rows if row.get("decision", "").strip() == decision]


def write_summary(summary_path: Path, decisions_path: Path, rows: list[dict[str, str]]) -> None:
    counts = Counter(row.get("decision", "").strip() for row in rows)
    include_ids = collect_ids(rows, "Incluir")
    doubtful_ids = collect_ids(rows, "Dudoso")
    lines = [
        "# Resumen de cribado",
        "",
        f"- Fecha: `{datetime.now().astimezone().isoformat(timespec='seconds')}`",
        f"- Iteracion / directorio: `{decisions_path.parent}`",
        f"- Total cribado: `{len(rows)}`",
        f"- Incluir: `{counts.get('Incluir', 0)}`",
        f"- Dudoso: `{counts.get('Dudoso', 0)}`",
        f"- Excluir: `{counts.get('Excluir', 0)}`",
        "",
        "## Identificadores clave",
        "",
        f"- Incluidos: `{', '.join(include_ids) if include_ids else 'ninguno'}`",
        f"- Dudosos: `{', '.join(doubtful_ids) if doubtful_ids else 'ninguno'}`",
        "",
    ]
    summary_path.write_text("\n".join(lines), encoding="utf-8")


def export_matrix_csv(matrix_markdown_path: Path, csv_path: Path) -> None:
    lines = matrix_markdown_path.read_text(encoding="utf-8").splitlines()
    header: list[str] | None = None
    rows: list[list[str]] = []

    for line in lines:
        if line.startswith("| Codigo |") or line.startswith("| Código |"):
            header = [part.strip() for part in line.strip().split("|")[1:-1]]
            continue
        if header is None or line.startswith("|---") or not line.startswith("| E"):
            continue
        rows.append([part.strip() for part in line.strip().split("|")[1:-1]])

    if header is None:
        raise SystemExit(f"Could not parse matrix header from: {matrix_markdown_path}")

    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def derive_summary_path(decisions_path: Path) -> Path:
    stem = decisions_path.stem
    if stem.startswith("screening_decisions_"):
        suffix = stem.removeprefix("screening_decisions_")
        return decisions_path.with_name(f"screening_summary_{suffix}.md")
    if stem == "screening_decisions":
        return decisions_path.with_name("screening_summary.md")
    return decisions_path.with_name(f"{stem}_summary.md")


def main() -> int:
    args = parse_args()
    env_config = {WORKSPACE_ROOT_KEY: args.workspace_root} if args.workspace_root else None
    matrix_path = resolve_workspace_path(args.matrix, None, env_config)
    decisions_path = resolve_workspace_path(args.decisions, None, env_config)
    summary_path = (
        resolve_workspace_path(args.summary, None, env_config)
        if args.summary
        else derive_summary_path(decisions_path)
    )
    matrix_csv_path = (
        resolve_workspace_path(args.matrix_csv, None, env_config)
        if args.matrix_csv
        else matrix_path.with_suffix(".csv")
    )

    if not matrix_path.exists():
        raise SystemExit(f"Matrix not found: {matrix_path}")
    if not decisions_path.exists():
        raise SystemExit(f"Decisions CSV not found: {decisions_path}")

    decisions, rows = load_decisions(decisions_path)
    update_matrix(matrix_path, decisions)
    export_matrix_csv(matrix_path, matrix_csv_path)
    write_summary(summary_path, decisions_path, rows)
    print(f"Updated screening matrix: {matrix_path}")
    print(f"Updated screening matrix CSV: {matrix_csv_path}")
    print(f"Updated screening summary: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
