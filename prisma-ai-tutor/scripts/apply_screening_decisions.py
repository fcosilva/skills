#!/usr/bin/env python3
"""Apply screening decisions to the generated screening matrix."""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from datetime import datetime
from pathlib import Path

from openalex_search import WORKSPACE_ROOT_KEY, resolve_workspace_path
from run_outputs import refresh_run_outputs


SCREENING_DECISION_HEADER = "Decision de cribado"
SCREENING_REASON_HEADER = "Motivo de cribado"
SCREENING_CRITERION_HEADER = "Criterio de cribado"
FINAL_BASIS_HEADER = "Base de seleccion final"
FINAL_NOTE_HEADER = "Observacion de seleccion final"
FINAL_COLUMNS = [FINAL_BASIS_HEADER, FINAL_NOTE_HEADER]
FULLTEXT_KINDS = {"pdf_fulltext", "html_fulltext"}


def is_matrix_data_row(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("|") and not stripped.startswith("|---")


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


def load_download_access_kinds(run_dir: Path) -> dict[str, str]:
    download_log = run_dir / "fulltext" / "fulltext_download_log.csv"
    if not download_log.exists():
        return {}
    with download_log.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return {
        row.get("code", "").strip(): row.get("access_kind", "").strip()
        for row in rows
        if row.get("code", "").strip()
    }


def validate_final_inclusions(rows: list[dict[str, str]], decisions_path: Path) -> None:
    if phase_label(decisions_path) != "selección final / elegibilidad":
        return
    run_dir = decisions_path.parent.parent if decisions_path.parent.name == "screening" else decisions_path.parent
    access_kinds = load_download_access_kinds(run_dir)
    invalid: list[str] = []
    for row in rows:
        if row.get("decision", "").strip() != "Incluir":
            continue
        code = row.get("code", "").strip()
        full_text = row.get("full_text", "").strip()
        final_basis = row.get("final_basis", "").strip()
        access_kind = access_kinds.get(code)
        if full_text != "Si" or final_basis != "Texto completo":
            invalid.append(
                f"{code}: decision=Incluir requiere full_text=Si y final_basis=Texto completo"
            )
            continue
        if access_kind is not None and access_kind not in FULLTEXT_KINDS:
            invalid.append(
                f"{code}: access_kind={access_kind or 'No reportado'} no es texto completo util"
            )
    if invalid:
        details = "\n- ".join(invalid)
        raise SystemExit(
            "La selección final contiene inclusiones sin texto completo verificable.\n"
            "Corrige `screening_decisions_final.csv` o recupera texto completo antes de aplicar la fase.\n"
            f"- {details}"
        )


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
            if FINAL_BASIS_HEADER not in columns:
                columns.extend(FINAL_COLUMNS)
                extend_separator = True
            try:
                decision_idx = columns.index(SCREENING_DECISION_HEADER) + 1
                reason_idx = columns.index(SCREENING_REASON_HEADER) + 1
                criterion_idx = columns.index(SCREENING_CRITERION_HEADER) + 1
                full_text_idx = columns.index("Revisar texto completo") + 1
                final_basis_idx = columns.index(FINAL_BASIS_HEADER) + 1
                final_note_idx = columns.index(FINAL_NOTE_HEADER) + 1
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

        if not is_matrix_data_row(line):
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


def counter_lines(counter: Counter[str]) -> list[str]:
    ordered = [(key, value) for key, value in counter.items() if key]
    ordered.sort(key=lambda item: (-item[1], item[0].casefold()))
    if not ordered:
        return ["- `No reportado`: `0`"]
    return [f"- `{key}`: `{value}`" for key, value in ordered]


def phase_label(decisions_path: Path) -> str:
    stem = decisions_path.stem.casefold()
    if stem.endswith("_final"):
        return "selección final / elegibilidad"
    if stem.endswith("_focused"):
        return "cribado focused"
    if stem.endswith("_initial"):
        return "cribado inicial"
    return "cribado"


def phase_methodology_lines(phase: str) -> list[str]:
    if phase == "cribado inicial":
        return [
            "- Base principal de decisión: `título + resumen + metadatos básicos`",
            "- Uso esperado: separar ruido evidente de señal potencial antes del `focused`",
        ]
    if phase == "cribado focused":
        return [
            "- Base principal de decisión: `título + resumen`, con mayor exigencia temática y metodológica",
            "- Uso esperado: reevaluar solo los casos `Incluir` y `Dudoso` heredados de `initial`",
        ]
    if phase == "selección final / elegibilidad":
        return [
            "- Base principal de decisión: `texto completo` cuando está disponible",
            "- Regla operativa: la elegibilidad final debe justificarse con acceso efectivo al estudio completo o dejar explícita la limitación",
        ]
    return [
        "- Base principal de decisión: `No reportado`",
    ]


def write_summary(summary_path: Path, decisions_path: Path, rows: list[dict[str, str]]) -> None:
    counts = Counter(row.get("decision", "").strip() for row in rows)
    include_ids = collect_ids(rows, "Incluir")
    doubtful_ids = collect_ids(rows, "Dudoso")
    criterion_counter = Counter(row.get("criterion", "").strip() for row in rows)
    reason_counter = Counter(row.get("reason", "").strip() for row in rows)
    phase = phase_label(decisions_path)
    title = "# Resumen de selección final / elegibilidad" if phase == "selección final / elegibilidad" else "# Resumen de cribado"
    total_label = "Total evaluado en selección final" if phase == "selección final / elegibilidad" else "Total cribado"
    include_label = "Estudios incluidos en corpus final" if phase == "selección final / elegibilidad" else "Incluir"
    doubtful_label = "Dudosos remanentes" if phase == "selección final / elegibilidad" else "Dudoso"
    exclude_label = "Estudios excluidos en selección final" if phase == "selección final / elegibilidad" else "Excluir"
    lines = [
        title,
        "",
        f"- Fecha: `{datetime.now().astimezone().isoformat(timespec='seconds')}`",
        f"- Fase declarada: `{phase}`",
        f"- Iteracion / directorio: `{decisions_path.parent}`",
        f"- Archivo de decisiones aplicado: `{decisions_path}`",
        f"- {total_label}: `{len(rows)}`",
        f"- {include_label}: `{counts.get('Incluir', 0)}`",
        f"- {doubtful_label}: `{counts.get('Dudoso', 0)}`",
        f"- {exclude_label}: `{counts.get('Excluir', 0)}`",
        "",
        "## Base metodológica de la fase",
        "",
        *phase_methodology_lines(phase),
        "",
        "## Criterios aplicados",
        "",
        *counter_lines(criterion_counter),
        "",
        "## Motivos registrados",
        "",
        *counter_lines(reason_counter),
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
        if header is None or not is_matrix_data_row(line):
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
    validate_final_inclusions(rows, decisions_path)
    update_matrix(matrix_path, decisions)
    export_matrix_csv(matrix_path, matrix_csv_path)
    write_summary(summary_path, decisions_path, rows)
    run_dir = matrix_path.parent.parent if matrix_path.parent.name == "screening" else matrix_path.parent
    refresh_run_outputs(run_dir)
    print(f"Updated screening matrix: {matrix_path}")
    print(f"Updated screening matrix CSV: {matrix_csv_path}")
    print(f"Updated screening summary: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
