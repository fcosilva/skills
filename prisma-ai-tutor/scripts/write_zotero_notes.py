#!/usr/bin/env python3
"""Write structured child notes in Zotero for synchronized review items."""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from openalex_search import load_env_config, resolve_workspace_path
from run_outputs import refresh_run_outputs
from zotero_mcp_client import ZoteroMCPClient


DEFAULT_MCP_URL = "http://127.0.0.1:23120/mcp"
SCREENING_DECISION_HEADER = "Decision de cribado"
SCREENING_REASON_HEADER = "Motivo de cribado"
SCREENING_CRITERION_HEADER = "Criterio de cribado"
FINAL_BASIS_HEADER = "Base de seleccion final"
FINAL_NOTE_HEADER = "Observacion de seleccion final"


@dataclass
class NotesConfig:
    config_file: Path
    mcp_url: str
    phase: str
    screening_matrix: Path
    screening_decisions: Path
    extraction_matrix: Path
    sync_actions: Path
    out_dir: Path
    dry_run: bool


def parse_args() -> NotesConfig:
    parser = argparse.ArgumentParser(
        description=(
            "Create or update structured child notes in Zotero using screening "
            "and extraction outputs from PRISMA-AI Tutor."
        )
    )
    parser.add_argument(
        "--config-file",
        required=True,
        help="Env-style configuration file for the case, for example cases/<slug>/case.env.",
    )
    parser.add_argument(
        "--phase",
        choices=("screening", "extraction", "quality"),
        default="screening",
        help="Kind of Zotero child note to create or update. Default: screening.",
    )
    parser.add_argument("--mcp-url", default=None, help="Override ZOTERO_MCP_URL.")
    parser.add_argument(
        "--screening-matrix",
        default=None,
        help="Override ZOTERO_SCREENING_MATRIX.",
    )
    parser.add_argument(
        "--screening-decisions",
        default=None,
        help="Override ZOTERO_SCREENING_DECISIONS.",
    )
    parser.add_argument(
        "--extraction-matrix",
        default=None,
        help="Path to extraction_matrix.md. Default: outputs/<run>/extraction/extraction_matrix.md.",
    )
    parser.add_argument(
        "--sync-actions",
        default=None,
        help="Path to zotero_sync_actions.csv. Default: outputs/<run>/zotero/zotero_sync_actions.csv.",
    )
    parser.add_argument(
        "--out-dir",
        default=None,
        help="Directory for note generation logs. Default: outputs/<run>/zotero.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview note actions only.")

    args = parser.parse_args()
    config_file = Path(args.config_file).expanduser().resolve()
    env_config = load_env_config(config_file)
    screening_matrix = resolve_workspace_path(
        args.screening_matrix or env_config.get("ZOTERO_SCREENING_MATRIX", "").strip(),
        config_file,
        env_config,
    )
    screening_decisions = resolve_workspace_path(
        args.screening_decisions or env_config.get("ZOTERO_SCREENING_DECISIONS", "").strip(),
        config_file,
        env_config,
    )
    if not str(screening_matrix):
        raise ValueError("Missing ZOTERO_SCREENING_MATRIX.")
    if not str(screening_decisions):
        raise ValueError("Missing ZOTERO_SCREENING_DECISIONS.")

    run_dir = screening_matrix.parent.parent
    extraction_matrix = (
        resolve_workspace_path(args.extraction_matrix, config_file, env_config)
        if args.extraction_matrix
        else run_dir / "extraction" / "extraction_matrix.md"
    )
    sync_actions = (
        resolve_workspace_path(args.sync_actions, config_file, env_config)
        if args.sync_actions
        else run_dir / "zotero" / "zotero_sync_actions.csv"
    )
    out_dir = (
        resolve_workspace_path(args.out_dir, config_file, env_config)
        if args.out_dir
        else run_dir / "zotero"
    )
    mcp_url = args.mcp_url or env_config.get("ZOTERO_MCP_URL", DEFAULT_MCP_URL).strip() or DEFAULT_MCP_URL

    return NotesConfig(
        config_file=config_file,
        mcp_url=mcp_url,
        phase=args.phase,
        screening_matrix=screening_matrix,
        screening_decisions=screening_decisions,
        extraction_matrix=extraction_matrix,
        sync_actions=sync_actions,
        out_dir=out_dir,
        dry_run=args.dry_run,
    )


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def parse_markdown_table(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    lines = [line.rstrip("\n") for line in path.read_text(encoding="utf-8").splitlines()]
    table_lines = [line for line in lines if line.startswith("|")]
    if len(table_lines) < 2:
        return []

    headers = [cell.strip() for cell in table_lines[0].strip("|").split("|")]
    rows: list[dict[str, str]] = []
    for line in table_lines[2:]:
        values = [cell.strip() for cell in line.strip("|").split("|")]
        if len(values) != len(headers):
            continue
        rows.append(dict(zip(headers, values)))
    return rows


def build_screening_note_content(
    matrix_row: dict[str, str],
    decision_row: dict[str, str] | None,
    action_row: dict[str, str],
) -> str:
    lines = [
        "# PRISMA-AI | Seleccion final",
        "",
        "## Seleccion final / evaluacion de elegibilidad",
        "",
        f"- Codigo: `{matrix_row.get('Codigo', '')}`",
        f"- Decision de cribado: `{matrix_row.get(SCREENING_DECISION_HEADER, '')}`",
        f"- Motivo de cribado: {matrix_row.get(SCREENING_REASON_HEADER, '')}",
        f"- Criterio de cribado: {matrix_row.get(SCREENING_CRITERION_HEADER, '')}",
        f"- Base de seleccion final: `{matrix_row.get(FINAL_BASIS_HEADER, '')}`",
        f"- Observacion de seleccion final: {matrix_row.get(FINAL_NOTE_HEADER, '')}",
        f"- Revisar texto completo: `{matrix_row.get('Revisar texto completo', '')}`",
        f"- Texto completo accesible: `{matrix_row.get('Texto completo accesible', '')}`",
        "",
        "## Metadatos operativos",
        "",
        f"- DOI: {matrix_row.get('DOI', '')}",
        f"- URL de acceso: {matrix_row.get('URL de acceso', '')}",
        f"- URL DOI: {matrix_row.get('URL DOI', '')}",
        f"- URL OpenAlex: {matrix_row.get('URL OpenAlex', '')}",
        f"- Primera afiliacion: {matrix_row.get('Primera afiliacion', '')}",
        f"- Pais: {matrix_row.get('Pais', '')}",
        f"- PDF preparado para Zotero: {action_row.get('zotero_attachment_path', '')}",
    ]

    if decision_row:
        lines.extend(
            [
                "",
                "## Registro de seleccion automatizada",
                "",
                f"- Criterio resumido: {decision_row.get('criterion', '')}",
                f"- Nota automatizada: {decision_row.get('final_note', '')}",
            ]
        )

    return "\n".join(lines).strip() + "\n"


def build_extraction_note_content(
    matrix_row: dict[str, str],
    extraction_row: dict[str, str] | None,
) -> str:
    lines = [
        "# PRISMA-AI | Extraccion",
        "",
        "## Identificacion",
        "",
        f"- Codigo: `{matrix_row.get('Codigo', '')}`",
        f"- Decision de cribado: `{matrix_row.get(SCREENING_DECISION_HEADER, '')}`",
        f"- Base de seleccion final: `{matrix_row.get(FINAL_BASIS_HEADER, '')}`",
        "",
        "## Extraccion de evidencia",
        "",
    ]
    if extraction_row:
        if "Población" in extraction_row or "Poblacion" in extraction_row or "Tipo de patología" in extraction_row:
            lines.extend(
                [
                    f"- Población: {extraction_row.get('Población', extraction_row.get('Poblacion', ''))}",
                    f"- Tipo de patología: {extraction_row.get('Tipo de patología', extraction_row.get('Tipo de patologia', ''))}",
                    f"- Métodos diagnósticos: {extraction_row.get('Métodos diagnósticos', extraction_row.get('Metodos diagnosticos', ''))}",
                    f"- Enfoque terapéutico: {extraction_row.get('Enfoque terapéutico', extraction_row.get('Enfoque terapeutico', ''))}",
                    f"- Resultados clínicos / recuperación: {extraction_row.get('Resultados clínicos / recuperación', extraction_row.get('Resultados clinicos / recuperacion', ''))}",
                    f"- Limitaciones: {extraction_row.get('Limitaciones reportadas', extraction_row.get('Limitaciones', ''))}",
                    f"- Relevancia: {extraction_row.get('Relevancia', '')}",
                ]
            )
        else:
            lines.extend(
                [
                    f"- Objetivo: {extraction_row.get('Objetivo', '')}",
                    f"- Metodo: {extraction_row.get('Metodo', '')}",
                    f"- Contexto: {extraction_row.get('Contexto', '')}",
                    f"- Muestra/corpus: {extraction_row.get('Muestra/corpus', '')}",
                    f"- Tecnologia/herramienta: {extraction_row.get('Tecnologia/herramienta', '')}",
                    f"- Variable principal observada: {extraction_row.get('Variable principal observada', '')}",
                    f"- Tipo de efecto reportado: {extraction_row.get('Tipo de efecto reportado', '')}",
                    f"- Relacion con autonomia: {extraction_row.get('Relacion con autonomia', '')}",
                    f"- Relacion con dependencia cognitiva: {extraction_row.get('Relacion con dependencia cognitiva', '')}",
                    f"- Relacion con rendimiento en programacion: {extraction_row.get('Relacion con rendimiento en programacion', '')}",
                    f"- Hallazgos principales: {extraction_row.get('Hallazgos principales', '')}",
                    f"- Limitaciones: {extraction_row.get('Limitaciones', '')}",
                    f"- Relevancia: {extraction_row.get('Relevancia', '')}",
                ]
            )
    else:
        lines.extend(
            [
                "- No disponible para este estudio en la iteracion actual.",
            ]
        )
    return "\n".join(lines).strip() + "\n"


def build_quality_note_content(
    matrix_row: dict[str, str],
    extraction_row: dict[str, str] | None,
) -> str:
    lines = [
        "# PRISMA-AI | Calidad",
        "",
        "## Identificacion",
        "",
        f"- Codigo: `{matrix_row.get('Codigo', '')}`",
        f"- Decision de cribado: `{matrix_row.get(SCREENING_DECISION_HEADER, '')}`",
        f"- Texto completo accesible: `{matrix_row.get('Texto completo accesible', '')}`",
        "",
        "## Evaluacion de calidad",
        "",
    ]
    if extraction_row:
        if "Población" in extraction_row or "Poblacion" in extraction_row or "Tipo de patología" in extraction_row:
            lines.extend(
                [
                    f"- Población: {extraction_row.get('Población', extraction_row.get('Poblacion', ''))}",
                    f"- Tipo de patología: {extraction_row.get('Tipo de patología', extraction_row.get('Tipo de patologia', ''))}",
                    f"- Limitaciones: {extraction_row.get('Limitaciones reportadas', extraction_row.get('Limitaciones', ''))}",
                    f"- Relevancia: {extraction_row.get('Relevancia', '')}",
                ]
            )
        else:
            lines.extend(
                [
                    f"- Metodo reportado: {extraction_row.get('Metodo', '')}",
                    f"- Muestra/corpus: {extraction_row.get('Muestra/corpus', '')}",
                    f"- Limitaciones: {extraction_row.get('Limitaciones', '')}",
                    f"- Relevancia: {extraction_row.get('Relevancia', '')}",
                ]
            )
    else:
        lines.append("- No disponible para este estudio en la iteracion actual.")
    return "\n".join(lines).strip() + "\n"


def build_note_content(
    phase: str,
    matrix_row: dict[str, str],
    decision_row: dict[str, str] | None,
    extraction_row: dict[str, str] | None,
    action_row: dict[str, str],
) -> str:
    if phase == "screening":
        return build_screening_note_content(matrix_row, decision_row, action_row)
    if phase == "extraction":
        return build_extraction_note_content(matrix_row, extraction_row)
    return build_quality_note_content(matrix_row, extraction_row)


def note_title_for_phase(phase: str) -> str:
    return {
        "screening": "PRISMA-AI | Seleccion final",
        "extraction": "PRISMA-AI | Extraccion",
        "quality": "PRISMA-AI | Calidad",
    }[phase]


def note_tags_for_phase(phase: str) -> list[str]:
    return ["prisma-ai-tutor", f"prisma-{phase}-note"]


def sync_notes(config: NotesConfig) -> dict[str, Any]:
    matrix_rows = read_csv_rows(config.screening_matrix)
    decisions_rows = read_csv_rows(config.screening_decisions)
    extraction_rows = parse_markdown_table(config.extraction_matrix)
    action_rows = read_csv_rows(config.sync_actions)

    matrix_by_code = {row.get("Codigo", "").strip(): row for row in matrix_rows}
    decisions_by_code = {row.get("code", "").strip(): row for row in decisions_rows}
    extraction_by_code = {row.get("Codigo", "").strip(): row for row in extraction_rows}

    client = ZoteroMCPClient(config.mcp_url)
    client.initialize()

    note_actions: list[dict[str, str]] = []

    for action_row in action_rows:
        code = action_row.get("code", "").strip()
        item_key = action_row.get("item_key", "").strip()
        if not code or not item_key:
            continue

        matrix_row = matrix_by_code.get(code)
        if not matrix_row:
            continue
        content = build_note_content(
            config.phase,
            matrix_row,
            decisions_by_code.get(code),
            extraction_by_code.get(code),
            action_row,
        )

        details = client.call_tool("get_item_details", {"itemKey": item_key, "mode": "complete"})
        notes = details.get("notes", []) if isinstance(details, dict) else []

        note_key = ""
        action = "create_note"
        phase_title = note_title_for_phase(config.phase)

        if notes:
            for note in notes:
                if not isinstance(note, dict):
                    continue
                note_text = str(note.get("note") or note.get("content") or "")
                if phase_title in note_text and note.get("key"):
                    note_key = str(note["key"])
                    action = "update_note"
                    break

        if not config.dry_run:
            if action == "update_note" and note_key:
                client.call_tool(
                    "write_note",
                    {
                        "action": "update",
                        "noteKey": note_key,
                        "content": content,
                        "tags": note_tags_for_phase(config.phase),
                    },
                )
            else:
                created = client.call_tool(
                    "write_note",
                    {
                        "action": "create",
                        "parentKey": item_key,
                        "content": content,
                        "tags": note_tags_for_phase(config.phase),
                    },
                )
                if isinstance(created, dict):
                    note_key = (
                        str(created.get("noteKey") or created.get("key") or created.get("data", {}).get("noteKey", ""))
                    )

        note_actions.append(
            {
                "code": code,
                "item_key": item_key,
                "phase": config.phase,
                "note_action": action,
                "note_key": note_key,
            }
        )

    return {
        "dry_run": config.dry_run,
        "mcp_url": config.mcp_url,
        "notes_processed": len(note_actions),
        "actions": note_actions,
    }


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


def main() -> int:
    config = parse_args()
    result = sync_notes(config)
    config.out_dir.mkdir(parents=True, exist_ok=True)
    summary_path = config.out_dir / "zotero_notes_summary.json"
    actions_path = config.out_dir / "zotero_notes_actions.csv"
    write_json(summary_path, result)
    write_csv(actions_path, result["actions"])
    refresh_run_outputs(config.out_dir.parent)
    print(
        f"Zotero notes {'preview' if config.dry_run else 'completed'} for "
        f"{result['notes_processed']} items."
    )
    print(f"Summary JSON: {summary_path}")
    print(f"Actions CSV: {actions_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
