#!/usr/bin/env python3
"""Generate student-facing run overview and traceability artifacts."""

from __future__ import annotations

import csv
import json
import os
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

PLACEHOLDER_MARKER = "<!-- PRISMA-AI: placeholder -->"


def first_existing(*paths: Path) -> Path:
    for path in paths:
        if path.exists():
            return path
    return paths[0]


def has_meaningful_file(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:  # noqa: BLE001
        return True
    return PLACEHOLDER_MARKER not in text


def read_json(path: Path) -> Any:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def parse_markdown_table(path: Path) -> list[dict[str, str]]:
    csv_path = path if path.suffix.casefold() == ".csv" else path.with_suffix(".csv")
    if csv_path.exists():
        return read_csv_rows(csv_path)
    if not path.exists():
        return []
    lines = [line.rstrip("\n") for line in path.read_text(encoding="utf-8").splitlines()]
    table_lines = [line for line in lines if line.startswith("|")]
    if len(table_lines) < 3:
        return []
    splitter = re.compile(r"(?<!\\)\|")
    def cells(line: str) -> list[str]:
        return [cell.strip().replace(r"\|", "|") for cell in splitter.split(line[1:-1])]
    headers = cells(table_lines[0])
    rows: list[dict[str, str]] = []
    for line in table_lines[2:]:
        values = cells(line)
        if len(values) != len(headers):
            raise ValueError(f"Malformed Markdown table row in {path}: {line[:100]}")
        rows.append(dict(zip(headers, values)))
    return rows


def rel_link(base_file: Path, target: Path, label: str | None = None) -> str:
    relative = os.path.relpath(target, start=base_file.parent)
    return f"[{label or target.name}]({relative})"


def maybe_link(base_file: Path, target: Path, label: str | None = None) -> str:
    if target.exists():
        return rel_link(base_file, target, label)
    return f"`{target.name}`"


def display_path(run_dir: Path, target: Path, fallback: str) -> str:
    if not target.exists():
        return fallback
    return target.as_posix().split(run_dir.as_posix() + "/")[-1]


def count_decision(rows: list[dict[str, str]], decision: str) -> int:
    return sum(1 for row in rows if row.get("decision", "").strip() == decision)


def is_zotero_screening_notes_complete(run_dir: Path) -> bool:
    summary_candidates = [
        run_dir / "zotero" / "zotero_notes_screening_summary.json",
        run_dir / "zotero_notes_screening_summary.json",
        run_dir / "zotero" / "zotero_notes_summary.json",
        run_dir / "zotero_notes_summary.json",
    ]
    actions_candidates = [
        run_dir / "zotero" / "zotero_notes_screening_actions.csv",
        run_dir / "zotero_notes_screening_actions.csv",
        run_dir / "zotero" / "zotero_notes_actions.csv",
        run_dir / "zotero_notes_actions.csv",
    ]
    for notes_summary_path in summary_candidates:
        notes_summary = read_json(notes_summary_path) or {}
        actions = notes_summary.get("actions")
        if isinstance(actions, list) and any(action.get("phase") == "screening" for action in actions):
            return True
    for notes_actions_path in actions_candidates:
        rows = read_csv_rows(notes_actions_path)
        if any(row.get("phase", "").strip() == "screening" for row in rows):
            return True
    return False


def focused_review_rows(
    initial_rows: list[dict[str, str]],
    focused_rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    if not initial_rows:
        return focused_rows
    eligible_codes = {
        row.get("code", "").strip()
        for row in initial_rows
        if row.get("decision", "").strip() in {"Incluir", "Dudoso"}
    }
    return [row for row in focused_rows if row.get("code", "").strip() in eligible_codes]


def final_evaluated_rows(final_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        row
        for row in final_rows
        if row.get("criterion", "").strip() != "Hereda exclusion previa"
    ]


def confirmed_final_selection(case_md: Path | None, run_dir: Path | None = None) -> str:
    paths = [case_md] if case_md else []
    if run_dir:
        paths.extend([
            run_dir / "fulltext" / "phase7_completion.md",
            run_dir / "screening" / "phase7_completion.md",
            run_dir / "screening" / "screening_summary_final.md",
        ])
    text = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in paths if path and path.exists()
    ).casefold()
    if "confirmacion humana del corpus final: confirmada" in text:
        return "confirmada"
    if "confirmación humana del corpus final: confirmada" in text:
        return "confirmada"
    if "selección final confirmada humanamente" in text:
        return "confirmada"
    if "confirmó explícitamente" in text and "selección final" in text:
        return "confirmada"
    if "elegibilidad final: cerrada y confirmada humanamente" in text:
        return "confirmada"
    return "no consta automáticamente"


def human_gate_status(run_dir: Path, phase: str, matrix: Path) -> str:
    if not has_meaningful_file(matrix):
        return "pendiente"
    report = matrix.parent / f"phase_{phase}_human_review_gate.json"
    payload = read_json(report) or {}
    if payload.get("human_validation_complete") is True:
        return "cerrada"
    phase_number = "9" if phase == "extraction" else "10"
    completion = matrix.parent / f"phase{phase_number}_completion.md"
    if completion.exists():
        text = completion.read_text(encoding="utf-8", errors="ignore").casefold()
        if "validó explícitamente" in text or "validada humanamente" in text:
            return "cerrada"
    return "propuesta pendiente de validación humana"


def synthesis_phase_status(run_dir: Path, synthesis: Path, audit: Path) -> str:
    if not (has_meaningful_file(synthesis) or has_meaningful_file(audit)):
        return "pendiente"
    completion = synthesis.parent / "phase11_completion.md"
    if completion.exists():
        text = completion.read_text(encoding="utf-8", errors="ignore").casefold()
        if "valid" in text and ("cerr" in text or "confirm" in text):
            return "cerrada"
    return "propuesta pendiente de validación humana"


def count_no_fulltext_exclusions(rows: list[dict[str, str]]) -> int:
    return sum(
        1 for row in final_evaluated_rows(rows)
        if row.get("criterion", "").strip().casefold() in {
            "fx0", "sin texto completo util para seleccion final", "sin texto completo útil para selección final"
        }
        or row.get("final_basis", "").strip().casefold() == "sin texto completo accesible"
    )


def final_fulltext_warnings(run_dir: Path, final_rows: list[dict[str, str]]) -> list[str]:
    download_rows = read_csv_rows(run_dir / "fulltext" / "fulltext_download_log.csv")
    access_by_code = {
        row.get("code", "").strip(): row.get("access_kind", "").strip()
        for row in download_rows
        if row.get("code", "").strip()
    }
    warnings: list[str] = []
    for row in final_rows:
        if row.get("decision", "").strip() != "Incluir":
            continue
        code = row.get("code", "").strip()
        access_kind = access_by_code.get(code)
        if access_kind and access_kind not in {"pdf_fulltext", "html_fulltext"}:
            warnings.append(
                f"`{code}` está incluido, pero el log de full text lo marca como `{access_kind}`."
            )
    return warnings


def estimated_result_count(search_summary: dict[str, Any]) -> Any:
    per_source = search_summary.get("per_source_counts")
    if isinstance(per_source, dict) and per_source:
        total = 0
        for value in per_source.values():
            try:
                total += int(value)
            except Exception:  # noqa: BLE001
                return "No reportado"
        return total
    for key in (
        "openalex_meta_count",
        "scielo_meta_count",
        "doaj_meta_count",
        "semanticscholar_meta_count",
        "lens_meta_count",
        "pubmed_meta_count",
        "scopus_meta_count",
        "redalyc_meta_count",
        "count",
    ):
        value = search_summary.get(key)
        if value not in (None, ""):
            return value
    return "No reportado"


def exported_result_count(search_summary: dict[str, Any]) -> Any:
    for key in ("exported_results", "merged_results"):
        value = search_summary.get(key)
        if value not in (None, ""):
            return value
    return "No reportado"


def determine_phase_statuses(run_dir: Path) -> dict[str, str]:
    search_summary = first_existing(
        run_dir / "search" / "merged_summary.json",
        run_dir / "search" / "summary.json",
        run_dir / "search" / "openalex" / "summary.json",
        run_dir / "search" / "scielo" / "summary.json",
        run_dir / "search" / "doaj" / "summary.json",
        run_dir / "search" / "semanticscholar" / "summary.json",
        run_dir / "search" / "lens" / "summary.json",
        run_dir / "search" / "pubmed" / "summary.json",
        run_dir / "search" / "scopus" / "summary.json",
        run_dir / "search" / "redalyc" / "summary.json",
        run_dir / "summary.json",
    )
    initial = first_existing(
        run_dir / "screening" / "screening_decisions_initial.csv",
        run_dir / "screening_decisions_initial.csv",
    )
    focused = first_existing(
        run_dir / "screening" / "screening_decisions_focused.csv",
        run_dir / "screening_decisions_focused.csv",
    )
    final = first_existing(
        run_dir / "screening" / "screening_decisions_final.csv",
        run_dir / "screening_decisions_final.csv",
    )
    fulltext_recovery = first_existing(
        run_dir / "fulltext" / "fulltext_recovery_summary.md",
        run_dir / "fulltext_recovery_summary.md",
    )
    fulltext_review = first_existing(
        run_dir / "fulltext" / "fulltext_review_text_summary.md",
        run_dir / "fulltext_review_text_summary.md",
    )
    zotero_sync = first_existing(
        run_dir / "zotero" / "zotero_sync_summary.json",
        run_dir / "zotero_sync_summary.json",
    )
    extraction_matrix = first_existing(
        run_dir / "extraction" / "extraction_matrix.md",
        run_dir / "extraction_matrix.md",
    )
    quality_matrix = first_existing(
        run_dir / "quality" / "quality_matrix.md",
        run_dir / "quality_matrix.md",
    )
    synthesis = first_existing(
        run_dir / "synthesis" / "narrative_synthesis.md",
        run_dir / "narrative_synthesis.md",
    )
    audit = first_existing(
        run_dir / "synthesis" / "final_audit.md",
        run_dir / "final_audit.md",
    )

    search_done = search_summary.exists()
    return {
        "Fase 1. Delimitación": "cerrada" if search_done else "pendiente",
        "Fase 2. Query": "cerrada" if search_done else "pendiente",
        "Fase 3. Búsqueda": "cerrada" if search_done else "pendiente",
        "Fase 4. Cribado inicial": "cerrada" if initial.exists() else "pendiente",
        "Fase 5. Cribado focused": "cerrada" if focused.exists() else "pendiente",
        "Fase 6. Accesibilidad y full text": (
            "cerrada" if fulltext_recovery.exists() and fulltext_review.exists() else "pendiente"
        ),
        "Fase 7. Selección final / elegibilidad": "cerrada" if final.exists() else "pendiente",
        "Fase 8. Zotero": (
            "cerrada" if zotero_sync.exists() and is_zotero_screening_notes_complete(run_dir) else "pendiente"
        ),
        "Fase 9. Extracción": human_gate_status(run_dir, "extraction", extraction_matrix),
        "Fase 10. Calidad": human_gate_status(run_dir, "quality", quality_matrix),
        "Fase 11. Síntesis y auditoría": synthesis_phase_status(run_dir, synthesis, audit),
    }


def determine_state(run_dir: Path) -> str:
    next_phase = determine_next_phase(run_dir)
    status = determine_phase_statuses(run_dir).get(next_phase, "")
    if next_phase == "Corrida cerrada":
        return "cerrado"
    if next_phase == "Fase 11. Síntesis y auditoría":
        return "síntesis pendiente"
    if next_phase == "Fase 10. Calidad":
        return "calidad propuesta; validación humana pendiente" if "propuesta" in status else "calidad pendiente"
    if next_phase == "Fase 9. Extracción":
        return "extracción propuesta; validación humana pendiente" if "propuesta" in status else "extracción pendiente"
    if next_phase == "Fase 8. Zotero":
        return "en Zotero"
    if next_phase == "Fase 7. Selección final / elegibilidad":
        return "en selección final"
    if next_phase == "Fase 6. Accesibilidad y full text":
        return "en full text"
    if next_phase == "Fase 5. Cribado focused":
        return "en cribado focused"
    if next_phase == "Fase 4. Cribado inicial":
        return "en cribado"
    return "en preparación"


def determine_next_phase(run_dir: Path) -> str:
    statuses = determine_phase_statuses(run_dir)
    for phase, status in statuses.items():
        if status != "cerrada":
            return phase
    return "Corrida cerrada"


def last_contiguous_closed_phase(phase_statuses: dict[str, str]) -> str:
    last = "ninguna"
    for phase, status in phase_statuses.items():
        if status != "cerrada":
            break
        last = phase
    return last


def find_case_context(run_dir: Path) -> tuple[str, Path | None, Path | None]:
    summary = read_json(
        first_existing(
            run_dir / "search" / "merged_summary.json",
            run_dir / "search" / "summary.json",
            run_dir / "search" / "openalex" / "summary.json",
            run_dir / "search" / "scielo" / "summary.json",
            run_dir / "search" / "doaj" / "summary.json",
            run_dir / "search" / "semanticscholar" / "summary.json",
            run_dir / "search" / "lens" / "summary.json",
            run_dir / "search" / "pubmed" / "summary.json",
            run_dir / "search" / "scopus" / "summary.json",
            run_dir / "search" / "redalyc" / "summary.json",
            run_dir / "summary.json",
        )
    ) or {}
    config_file_raw = summary.get("config_file")
    if config_file_raw:
        config_file = Path(config_file_raw)
        case_dir = config_file.parent
        case_md = case_dir / "case.md"
        protocol_md = case_dir / "protocol.md"
        return case_dir.name, case_md if case_md.exists() else None, protocol_md if protocol_md.exists() else None
    return run_dir.name, None, None


def build_run_overview(run_dir: Path) -> str:
    overview_path = run_dir / "run_overview.md"
    search_dir = run_dir / "search"
    screening_dir = run_dir / "screening"
    fulltext_dir = run_dir / "fulltext"
    zotero_dir = run_dir / "zotero"
    extraction_dir = run_dir / "extraction"
    quality_dir = run_dir / "quality"
    synthesis_dir = run_dir / "synthesis"

    search_summary_path = first_existing(
        search_dir / "merged_summary.json",
        search_dir / "summary.json",
        search_dir / "openalex" / "summary.json",
        search_dir / "scielo" / "summary.json",
        search_dir / "doaj" / "summary.json",
        search_dir / "semanticscholar" / "summary.json",
        search_dir / "lens" / "summary.json",
        search_dir / "pubmed" / "summary.json",
        search_dir / "scopus" / "summary.json",
        search_dir / "redalyc" / "summary.json",
        run_dir / "summary.json",
    )
    query_path = first_existing(
        search_dir / "query.txt",
        search_dir / "openalex" / "query.txt",
        search_dir / "scielo" / "query.txt",
        search_dir / "doaj" / "query.txt",
        search_dir / "semanticscholar" / "query.txt",
        search_dir / "lens" / "query.txt",
        search_dir / "pubmed" / "query.txt",
        search_dir / "scopus" / "query.txt",
        search_dir / "redalyc" / "query.txt",
        run_dir / "query.txt",
    )
    query_history_path = first_existing(
        search_dir / "query_history.md",
        search_dir / "openalex" / "query_history.md",
        search_dir / "scielo" / "query_history.md",
        search_dir / "doaj" / "query_history.md",
        search_dir / "semanticscholar" / "query_history.md",
        search_dir / "lens" / "query_history.md",
        search_dir / "pubmed" / "query_history.md",
        search_dir / "scopus" / "query_history.md",
        search_dir / "redalyc" / "query_history.md",
        run_dir / "query_history.md",
    )
    search_log_path = first_existing(
        search_dir / "source_merge_log.md",
        search_dir / "search_log.md",
        search_dir / "openalex" / "search_log.md",
        search_dir / "scielo" / "search_log.md",
        search_dir / "doaj" / "search_log.md",
        search_dir / "semanticscholar" / "search_log.md",
        search_dir / "lens" / "search_log.md",
        search_dir / "pubmed" / "search_log.md",
        search_dir / "scopus" / "search_log.md",
        search_dir / "redalyc" / "search_log.md",
        run_dir / "search_log.md",
    )
    screening_matrix_path = first_existing(screening_dir / "screening_matrix.md", run_dir / "screening_matrix.md")
    initial_summary_path = first_existing(
        screening_dir / "screening_summary_initial.md",
        run_dir / "screening_summary_initial.md",
    )
    focused_summary_path = first_existing(
        screening_dir / "screening_summary_focused.md",
        run_dir / "screening_summary_focused.md",
    )
    final_summary_path = first_existing(
        screening_dir / "screening_summary_final.md",
        run_dir / "screening_summary_final.md",
    )
    fulltext_recovery_path = first_existing(
        fulltext_dir / "fulltext_recovery_summary.md",
        run_dir / "fulltext_recovery_summary.md",
    )
    fulltext_review_summary_path = first_existing(
        fulltext_dir / "fulltext_review_text_summary.md",
        run_dir / "fulltext_review_text_summary.md",
    )
    extraction_matrix_path = first_existing(
        extraction_dir / "extraction_matrix.md",
        run_dir / "extraction_matrix.md",
    )
    quality_matrix_path = first_existing(
        quality_dir / "quality_matrix.md",
        run_dir / "quality_matrix.md",
    )
    synthesis_path = first_existing(
        synthesis_dir / "narrative_synthesis.md",
        run_dir / "narrative_synthesis.md",
    )
    audit_path = first_existing(
        synthesis_dir / "final_audit.md",
        run_dir / "final_audit.md",
    )
    final_report_path = first_existing(
        synthesis_dir / "informe_final.md",
        run_dir / "informe_final.md",
    )
    search_summary = read_json(search_summary_path) or {}
    initial_rows = read_csv_rows(first_existing(screening_dir / "screening_decisions_initial.csv", run_dir / "screening_decisions_initial.csv"))
    focused_rows = read_csv_rows(first_existing(screening_dir / "screening_decisions_focused.csv", run_dir / "screening_decisions_focused.csv"))
    final_rows = read_csv_rows(first_existing(screening_dir / "screening_decisions_final.csv", run_dir / "screening_decisions_final.csv"))
    case_name, case_md, protocol_md = find_case_context(run_dir)
    phase_statuses = determine_phase_statuses(run_dir)

    focused_rows_evaluated = focused_review_rows(initial_rows, focused_rows)
    final_rows_evaluated = final_evaluated_rows(final_rows)
    final_basis_counter = Counter(row.get("final_basis", "").strip() for row in final_rows_evaluated)
    final_criterion_counter = Counter(row.get("criterion", "").strip() for row in final_rows_evaluated)
    last_phase_closed = last_contiguous_closed_phase(phase_statuses)
    consistency_warnings = final_fulltext_warnings(run_dir, final_rows)

    lines = [
        "# Índice de corrida",
        "",
        "## Identificación",
        "",
        f"- Caso: `{case_name}`",
        f"- Corrida: `{run_dir.name}`",
        f"- Fecha de actualización: `{datetime.now().astimezone().isoformat(timespec='seconds')}`",
        f"- Estado general: `{determine_state(run_dir)}`",
        "",
        "## Punto de entrada recomendado",
        "",
        "Abre los artefactos en este orden:",
        "",
    ]
    if case_md:
        lines.append(f"- {rel_link(overview_path, case_md, 'case.md')}")
    else:
        lines.append("- `case.md`")
    if protocol_md:
        lines.append(f"- {rel_link(overview_path, protocol_md, 'protocol.md')}")
        lines.append("- `run_overview.md`")
        lines.append("- resumen de la fase actual")
    else:
        lines.append("- `run_overview.md`")
        lines.append("- resumen de la fase actual")
    lines.extend(
        [
            "- matriz o CSV solo si necesitas revisar detalle fino",
            "",
            "## Estado por fases",
            "",
        ]
    )
    for phase, status in phase_statuses.items():
        lines.append(f"- {phase}: `{status}`")

    lines.extend(
        [
            "",
            "## Resumen ejecutivo de la corrida",
            "",
            f"- Query vigente: {maybe_link(overview_path, query_path, display_path(run_dir, query_path, 'search/<fuente>/query.txt'))}",
            f"- Historial de refinamiento: {maybe_link(overview_path, query_history_path, display_path(run_dir, query_history_path, 'search/<fuente>/query_history.md'))}",
            f"- Última fase cerrada: `{last_phase_closed}`",
            f"- Próxima fase sugerida: `{determine_next_phase(run_dir)}`",
            f"- Resultados estimados por la fuente: `{estimated_result_count(search_summary)}`",
            f"- Resultados exportados para cribado: `{exported_result_count(search_summary)}`",
            f"- Incluidos en `initial`: `{count_decision(initial_rows, 'Incluir')}`",
            f"- Incluidos en `focused`: `{count_decision(focused_rows_evaluated, 'Incluir')}`",
            f"- Selección final confirmada: `{confirmed_final_selection(case_md, run_dir)}`",
            f"- Estudios con `Texto completo`: `{final_basis_counter.get('Texto completo', 0)}`",
            f"- Estudios excluidos por falta de `Texto completo`: `{count_no_fulltext_exclusions(final_rows)}`",
            "",
            "## Alertas de consistencia",
            "",
        ]
    )
    if consistency_warnings:
        lines.extend([f"- {warning}" for warning in consistency_warnings])
    else:
        lines.append("- Sin alertas automáticas.")
    lines.extend(
        [
            "",
            "## Artefactos clave por fase",
            "",
            "### Fase 3. Búsqueda",
            "",
            f"- {maybe_link(overview_path, search_log_path, display_path(run_dir, search_log_path, 'search/<fuente>/search_log.md'))}",
            f"- {maybe_link(overview_path, search_summary_path, display_path(run_dir, search_summary_path, 'search/<fuente>/summary.json'))}",
            f"- {maybe_link(overview_path, screening_matrix_path, 'screening/screening_matrix.md')}",
            "",
            "### Fases 4-5. Cribado",
            "",
            f"- {maybe_link(overview_path, initial_summary_path, 'screening/screening_summary_initial.md')}",
            f"- {maybe_link(overview_path, focused_summary_path, 'screening/screening_summary_focused.md')}",
            f"- {maybe_link(overview_path, screening_dir / 'screening_trace.md', 'screening/screening_trace.md')}",
            "",
            "### Fase 6. Full text",
            "",
            f"- {maybe_link(overview_path, fulltext_recovery_path, 'fulltext/fulltext_recovery_summary.md')}",
            f"- {maybe_link(overview_path, fulltext_review_summary_path, 'fulltext/fulltext_review_text_summary.md')}",
            "",
            "### Fase 7. Selección final",
            "",
            f"- {maybe_link(overview_path, final_summary_path, 'screening/screening_summary_final.md (selección final)')}",
            "",
            "### Fases 8-10",
            "",
            f"- {maybe_link(overview_path, zotero_dir / 'zotero_summary.md', 'zotero/zotero_summary.md')}",
            f"- {maybe_link(overview_path, extraction_dir / 'extraction_summary.md', 'extraction/extraction_summary.md')}",
            f"- {maybe_link(overview_path, quality_dir / 'quality_summary.md', 'quality/quality_summary.md')}",
            "",
            "### Fase 11",
            "",
            f"- {maybe_link(overview_path, synthesis_path, 'synthesis/narrative_synthesis.md')}",
            f"- {maybe_link(overview_path, audit_path, 'synthesis/final_audit.md')}",
            f"- {maybe_link(overview_path, final_report_path, 'synthesis/informe_final.md (solo con confirmación humana)')}",
            "",
        ]
    )
    return "\n".join(lines) + "\n"


def build_screening_trace(run_dir: Path) -> str:
    initial_rows = read_csv_rows(first_existing(run_dir / "screening" / "screening_decisions_initial.csv", run_dir / "screening_decisions_initial.csv"))
    focused_rows = read_csv_rows(first_existing(run_dir / "screening" / "screening_decisions_focused.csv", run_dir / "screening_decisions_focused.csv"))
    final_rows = read_csv_rows(first_existing(run_dir / "screening" / "screening_decisions_final.csv", run_dir / "screening_decisions_final.csv"))
    focused_rows_evaluated = focused_review_rows(initial_rows, focused_rows)
    preserved_initial_excluded = max(len(focused_rows) - len(focused_rows_evaluated), 0)
    final_rows_evaluated = final_evaluated_rows(final_rows)
    final_basis_counter = Counter(row.get("final_basis", "").strip() for row in final_rows_evaluated)
    final_criterion_counter = Counter(row.get("criterion", "").strip() for row in final_rows_evaluated)
    inherited_final_excluded = len(final_rows) - len(final_rows_evaluated)
    lines = [
        "# Trazabilidad de cribado y selección final",
        "",
        "## Paso 1. Cribado inicial",
        "",
        f"- Total revisado: `{len(initial_rows)}`",
        f"- `Incluir`: `{count_decision(initial_rows, 'Incluir')}`",
        f"- `Dudoso`: `{count_decision(initial_rows, 'Dudoso')}`",
        f"- `Excluir`: `{count_decision(initial_rows, 'Excluir')}`",
        "",
        "## Paso 2. Cribado focused",
        "",
        f"- Subconjunto reevaluado: `{len(focused_rows_evaluated)}`",
        f"- Filas preservadas como exclusión previa: `{preserved_initial_excluded}`",
        f"- `Incluir`: `{count_decision(focused_rows_evaluated, 'Incluir')}`",
        f"- `Dudoso`: `{count_decision(focused_rows_evaluated, 'Dudoso')}`",
        f"- `Excluir`: `{count_decision(focused_rows_evaluated, 'Excluir')}`",
        "",
        "## Paso 3. Selección final / elegibilidad",
        "",
        f"- Subconjunto evaluado en selección final: `{len(final_rows_evaluated)}`",
        f"- Registros preservados como exclusión previa: `{inherited_final_excluded}`",
        f"- Estudios evaluados con base `Texto completo`: `{final_basis_counter.get('Texto completo', 0)}`",
        f"- Estudios excluidos por falta de `Texto completo`: `{count_no_fulltext_exclusions(final_rows)}`",
        f"- Estudios incluidos en corpus final: `{count_decision(final_rows, 'Incluir')}`",
        f"- Dudosos remanentes: `{count_decision(final_rows, 'Dudoso')}`",
        f"- Estudios excluidos en selección final: `{count_decision(final_rows, 'Excluir')}`",
        "",
    ]
    return "\n".join(lines) + "\n"


def build_extraction_summary(run_dir: Path) -> str | None:
    matrix = first_existing(run_dir / "extraction" / "extraction_matrix.md", run_dir / "extraction_matrix.md")
    rows = parse_markdown_table(matrix)
    if not rows:
        return None
    code_field = next((field for field in ("Codigo", "Código", "Codigo estudio", "Código estudio") if field in rows[0]), None)
    review_candidates = (
        "Estado de revisión humana", "Estado de revision humana", "Revisión humana", "Revision humana",
        "Estado de revisión", "Estado de revision",
    )
    review_field = next((field for field in review_candidates if field in rows[0]), None)
    completed = 0
    administrative_fields = {
        "Codigo", "Código", "Codigo estudio", "Código estudio", "Autor/ano", "Pais",
        "Primera afiliacion", "Titulo", "Estado de revisión humana", "Estado de revision humana",
        "Revisión humana", "Revision humana", "Estado de revisión", "Estado de revision",
        "Observación humana", "Observacion humana",
    }
    for row in rows:
        payload = [
            value.strip()
            for key, value in row.items()
            if key not in administrative_fields
        ]
        if any(payload):
            completed += 1
    unique_studies = len({row.get(code_field, "").strip() for row in rows if code_field and row.get(code_field, "").strip()})
    review_counter = Counter(row.get(review_field, "").strip() or "No reportado" for row in rows) if review_field else Counter()
    lines = [
        "# Resumen de extracción de evidencia",
        "",
        f"- Matriz principal: `{matrix}`",
        f"- Filas o instancias registradas: `{len(rows)}`",
        f"- Estudios únicos registrados: `{unique_studies or len(rows)}`",
        f"- Filas con extracción no vacía: `{completed}`",
        f"- Filas pendientes o mínimas: `{max(len(rows) - completed, 0)}`",
        f"- Validación humana: `{dict(review_counter) if review_counter else 'No reportado'}`",
        "",
    ]
    return "\n".join(lines) + "\n"


def build_quality_summary(run_dir: Path) -> str | None:
    matrix = first_existing(run_dir / "quality" / "quality_matrix.md", run_dir / "quality_matrix.md")
    rows = parse_markdown_table(matrix)
    if not rows:
        return None
    category_field = next(
        (field for field in ("Calidad", "Adecuacion de reporte", "Adecuación de reporte", "Adecuación global dentro del diseño") if field in rows[0]),
        None,
    )
    counter = Counter(row.get(category_field, "").strip() or "No reportado" for row in rows) if category_field else Counter()
    code_field = next((field for field in ("Codigo", "Código", "Codigo estudio", "Código estudio") if field in rows[0]), None)
    unique_studies = len({row.get(code_field, "").strip() for row in rows if code_field and row.get(code_field, "").strip()})
    review_field = next(
        (field for field in ("Estado de revisión humana", "Estado de revision humana", "Revisión humana", "Revision humana", "Estado de revisión", "Estado de revision") if field in rows[0]),
        None,
    )
    review_counter = Counter(row.get(review_field, "").strip() or "No reportado" for row in rows) if review_field else Counter()
    lines = [
        "# Resumen de calidad metodológica",
        "",
        f"- Matriz principal: `{matrix}`",
        f"- Filas evaluadas: `{len(rows)}`",
        f"- Estudios únicos evaluados: `{unique_studies or len(rows)}`",
        f"- Campo de síntesis: `{category_field or 'No reportado'}`",
        f"- Categorías observadas: `{dict(counter) if counter else 'No reportado'}`",
        f"- Validación humana: `{dict(review_counter) if review_counter else 'No reportado'}`",
        "",
    ]
    return "\n".join(lines) + "\n"


def build_zotero_summary(run_dir: Path) -> str | None:
    prepared = read_json(first_existing(run_dir / "zotero" / "zotero_import_summary.json", run_dir / "zotero_import_summary.json")) or {}
    sync = read_json(first_existing(run_dir / "zotero" / "zotero_sync_summary.json", run_dir / "zotero_sync_summary.json")) or {}
    notes = read_json(first_existing(run_dir / "zotero" / "zotero_notes_summary.json", run_dir / "zotero_notes_summary.json")) or {}
    screening_notes = read_json(
        first_existing(
            run_dir / "zotero" / "zotero_notes_screening_summary.json",
            run_dir / "zotero_notes_screening_summary.json",
        )
    ) or {}
    extraction_notes = read_json(
        first_existing(
            run_dir / "zotero" / "zotero_notes_extraction_summary.json",
            run_dir / "zotero_notes_extraction_summary.json",
        )
    ) or {}
    quality_notes = read_json(
        first_existing(
            run_dir / "zotero" / "zotero_notes_quality_summary.json",
            run_dir / "zotero_notes_quality_summary.json",
        )
    ) or {}
    if not prepared and not sync and not notes and not screening_notes and not extraction_notes and not quality_notes:
        return None
    collection = sync.get("collection", {}).get("path") or prepared.get("zotero_collection") or "No reportado"
    lines = [
        "# Resumen de integración en Zotero",
        "",
        f"- Biblioteca destino: `{prepared.get('zotero_library', 'No reportado')}`",
        f"- Colección destino: `{collection}`",
        f"- Ítems preparados: `{prepared.get('included_items', 0)}`",
        f"- Ítems sincronizados: `{len(sync.get('actions', [])) if isinstance(sync.get('actions'), list) else 0}`",
        f"- Notas procesadas: `{notes.get('notes_processed', 0)}`",
        f"- Notas de screening: `{screening_notes.get('notes_processed', 0)}`",
        f"- Notas de extracción: `{extraction_notes.get('notes_processed', 0)}`",
        f"- Notas de calidad: `{quality_notes.get('notes_processed', 0)}`",
        "",
    ]
    return "\n".join(lines) + "\n"


def write_if_content(path: Path, content: str | None) -> None:
    if content is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def write_placeholder_if_missing(path: Path, content: str) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def extraction_matrix_placeholder() -> str:
    return "\n".join(
        [
            "# Matriz de extracción de evidencia",
            "",
            PLACEHOLDER_MARKER,
            "",
            "Pendiente de completar.",
            "",
            "Usa `assets/extraction-matrix.md` como referencia para poblar esta matriz cuando comience la Fase 9.",
            "",
        ]
    )


def quality_matrix_placeholder() -> str:
    return "\n".join(
        [
            "# Matriz de calidad metodológica",
            "",
            PLACEHOLDER_MARKER,
            "",
            "Pendiente de completar.",
            "",
            "Usa `assets/quality-matrix.md` como referencia para poblar esta matriz cuando comience la Fase 10.",
            "",
        ]
    )


def narrative_synthesis_placeholder() -> str:
    return "\n".join(
        [
            "# Síntesis narrativa",
            "",
            PLACEHOLDER_MARKER,
            "",
            "Pendiente de redactar.",
            "",
            "Se recomienda completar este artefacto al cierre de la Fase 11.",
            "",
            "## Hallazgo principal",
            "",
            "[[...]]",
            "",
            "## Matices y contradicciones",
            "",
            "[[...]]",
            "",
            "## Limitaciones",
            "",
            "[[...]]",
            "",
        ]
    )


def final_audit_placeholder() -> str:
    return "\n".join(
        [
            "# Auditoría final",
            "",
            PLACEHOLDER_MARKER,
            "",
            "Pendiente de completar.",
            "",
            "## Lista de verificación",
            "",
            "- Trazabilidad del caso verificada: [[sí / no]]",
            "- Uso de IA declarado: [[sí / no]]",
            "- Selección final confirmada humanamente: [[sí / no]]",
            "- Síntesis coherente con la evidencia: [[sí / no]]",
            "",
        ]
    )


def refresh_run_outputs(run_dir: Path) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    for name in ("search", "screening", "fulltext", "zotero", "extraction", "quality", "synthesis"):
        (run_dir / name).mkdir(parents=True, exist_ok=True)

    write_placeholder_if_missing(run_dir / "extraction" / "extraction_matrix.md", extraction_matrix_placeholder())
    write_placeholder_if_missing(run_dir / "quality" / "quality_matrix.md", quality_matrix_placeholder())
    write_placeholder_if_missing(run_dir / "synthesis" / "narrative_synthesis.md", narrative_synthesis_placeholder())
    write_placeholder_if_missing(run_dir / "synthesis" / "final_audit.md", final_audit_placeholder())

    write_if_content(run_dir / "run_overview.md", build_run_overview(run_dir))

    screening_dir = run_dir / "screening"
    if any(path.exists() for path in (
        screening_dir / "screening_decisions_initial.csv",
        screening_dir / "screening_decisions_focused.csv",
        screening_dir / "screening_decisions_final.csv",
        run_dir / "screening_decisions_initial.csv",
        run_dir / "screening_decisions_focused.csv",
        run_dir / "screening_decisions_final.csv",
    )):
        write_if_content(screening_dir / "screening_trace.md", build_screening_trace(run_dir))

    write_if_content(run_dir / "extraction" / "extraction_summary.md", build_extraction_summary(run_dir))
    write_if_content(run_dir / "quality" / "quality_summary.md", build_quality_summary(run_dir))
    write_if_content(run_dir / "zotero" / "zotero_summary.md", build_zotero_summary(run_dir))
