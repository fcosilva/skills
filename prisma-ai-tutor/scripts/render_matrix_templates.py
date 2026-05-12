#!/usr/bin/env python3
"""Render matrix templates from metadata-columns.yaml."""

from __future__ import annotations

import argparse
from pathlib import Path

from metadata_config import (
    DEFAULT_METADATA_CONFIG_PATH,
    SCREENING_DECISION_COLUMNS,
    extraction_template_row,
    headers_for_columns,
    load_metadata_config,
    render_markdown_header,
    screening_template_row,
)


SKILL_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCREENING_TEMPLATE = SKILL_ROOT / "assets" / "screening-matrix.md"
DEFAULT_EXTRACTION_TEMPLATE = SKILL_ROOT / "assets" / "extraction-matrix.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render screening and extraction matrix templates from YAML config."
    )
    parser.add_argument(
        "--metadata-config",
        default=str(DEFAULT_METADATA_CONFIG_PATH),
        help=f"Path to metadata-columns.yaml. Default: {DEFAULT_METADATA_CONFIG_PATH}.",
    )
    parser.add_argument(
        "--screening-template",
        default=str(DEFAULT_SCREENING_TEMPLATE),
        help=f"Output path for screening template. Default: {DEFAULT_SCREENING_TEMPLATE}.",
    )
    parser.add_argument(
        "--extraction-template",
        default=str(DEFAULT_EXTRACTION_TEMPLATE),
        help=f"Output path for extraction template. Default: {DEFAULT_EXTRACTION_TEMPLATE}.",
    )
    return parser.parse_args()


def render_screening_template(path: Path, screening_keys: list[str]) -> None:
    headers = headers_for_columns(screening_keys) + SCREENING_DECISION_COLUMNS
    sample_row = screening_template_row(screening_keys)
    lines = [
        "# Matriz de cribado (seleccion de estudios)",
        "",
        *render_markdown_header(headers),
        "| " + " | ".join(sample_row) + " |",
        "",
        "> Esta plantilla se genera desde `assets/metadata-columns.yaml` del skill.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def render_extraction_template(path: Path, extraction_keys: list[str]) -> None:
    headers = headers_for_columns(extraction_keys)
    sample_row = extraction_template_row(extraction_keys)
    lines = [
        "# Matriz de extraccion de evidencia",
        "",
        *render_markdown_header(headers),
        "| " + " | ".join(sample_row) + " |",
        "",
        "> Esta plantilla se genera desde `assets/metadata-columns.yaml` del skill.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    config = load_metadata_config(Path(args.metadata_config))
    render_screening_template(Path(args.screening_template), config["screening_columns"])
    render_extraction_template(Path(args.extraction_template), config["extraction_columns"])
    print(f"Updated screening template: {args.screening_template}")
    print(f"Updated extraction template: {args.extraction_template}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
