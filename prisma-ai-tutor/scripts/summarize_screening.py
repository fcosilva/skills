#!/usr/bin/env python3
"""Generate a screening summary from a screening decisions CSV."""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from datetime import datetime
from pathlib import Path

from openalex_search import WORKSPACE_ROOT_KEY, resolve_workspace_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a Markdown summary for a screening iteration."
    )
    parser.add_argument(
        "--decisions",
        required=True,
        help="CSV file with screening decisions.",
    )
    parser.add_argument(
        "--output",
        help=(
            "Markdown file to write the screening summary. "
            "Default: derived from the decisions filename."
        ),
    )
    parser.add_argument(
        "--source-dir",
        help="Optional label for the output directory of this iteration.",
    )
    parser.add_argument(
        "--notes",
        help="Optional short methodological note to include in the summary.",
    )
    parser.add_argument(
        "--workspace-root",
        help=(
            "Optional workspace root used to resolve relative CLI paths. "
            f"Equivalent to {WORKSPACE_ROOT_KEY} for CLI-only scripts."
        ),
    )
    return parser.parse_args()


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def collect_ids(rows: list[dict[str, str]], decision: str) -> list[str]:
    return [row.get("code", "").strip() for row in rows if row.get("decision", "").strip() == decision]


def build_summary(rows: list[dict[str, str]], source_dir: str | None, notes: str | None) -> str:
    counts = Counter(row.get("decision", "").strip() for row in rows)
    total = len(rows)
    include_ids = collect_ids(rows, "Incluir")
    doubtful_ids = collect_ids(rows, "Dudoso")

    lines = [
        "# Resumen de cribado",
        "",
        f"- Fecha: `{datetime.now().astimezone().isoformat(timespec='seconds')}`",
    ]
    if source_dir:
        lines.append(f"- Iteracion / directorio: `{source_dir}`")
    lines.extend(
        [
            f"- Total cribado: `{total}`",
            f"- Incluir: `{counts.get('Incluir', 0)}`",
            f"- Dudoso: `{counts.get('Dudoso', 0)}`",
            f"- Excluir: `{counts.get('Excluir', 0)}`",
            "",
            "## Identificadores clave",
            "",
            f"- Incluidos: `{', '.join(include_ids) if include_ids else 'ninguno'}`",
            f"- Dudosos: `{', '.join(doubtful_ids) if doubtful_ids else 'ninguno'}`",
        ]
    )
    if notes:
        lines.extend(
            [
                "",
                "## Nota metodologica",
                "",
                notes.strip(),
            ]
        )
    lines.append("")
    return "\n".join(lines)


def derive_output_path(decisions_path: Path) -> Path:
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
    decisions_path = resolve_workspace_path(args.decisions, None, env_config)
    output_path = (
        resolve_workspace_path(args.output, None, env_config)
        if args.output
        else derive_output_path(decisions_path)
    )

    if not decisions_path.exists():
        raise SystemExit(f"Decisions CSV not found: {decisions_path}")

    rows = load_rows(decisions_path)
    summary = build_summary(rows, args.source_dir, args.notes)
    output_path.write_text(summary, encoding="utf-8")
    print(f"Updated screening summary: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
