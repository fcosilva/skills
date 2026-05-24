#!/usr/bin/env python3
"""Shared metadata-column configuration for PRISMA-AI Tutor."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_METADATA_CONFIG_PATH = SKILL_ROOT / "assets" / "metadata-columns.yaml"


@dataclass(frozen=True)
class ColumnDefinition:
    header: str
    screening_placeholder: str = ""
    extraction_placeholder: str = ""


SCREENING_DECISION_COLUMNS = [
    "Decision de cribado",
    "Motivo de cribado",
    "Criterio de cribado",
    "Revisar texto completo",
    "Base de seleccion final",
    "Observacion de seleccion final",
]


COLUMN_DEFINITIONS: dict[str, ColumnDefinition] = {
    "code": ColumnDefinition("Codigo", "E01", "E01"),
    "title": ColumnDefinition("Titulo"),
    "author_year": ColumnDefinition("Autor/ano"),
    "first_affiliation": ColumnDefinition("Primera afiliacion"),
    "country": ColumnDefinition("Pais"),
    "language": ColumnDefinition("Idioma"),
    "source": ColumnDefinition("Fuente"),
    "document_type": ColumnDefinition("Tipo documental", "Articulo/Tesis/Otro"),
    "doi": ColumnDefinition("DOI"),
    "open_access": ColumnDefinition("Acceso abierto", "Si/No"),
    "fulltext_accessible": ColumnDefinition(
        "Texto completo accesible", "Si/No/Por verificar/No confirmado"
    ),
    "url_doi": ColumnDefinition("URL DOI"),
    "url_access": ColumnDefinition("URL de acceso"),
    "url_openalex": ColumnDefinition("URL OpenAlex"),
    "abstract_available": ColumnDefinition("Resumen disponible", "Si/No"),
    "objective": ColumnDefinition("Objetivo"),
    "method": ColumnDefinition("Metodo"),
    "context": ColumnDefinition("Contexto"),
    "sample_corpus": ColumnDefinition("Muestra/corpus"),
    "tool": ColumnDefinition("Tecnologia/herramienta"),
    "main_variable": ColumnDefinition("Variable principal observada"),
    "effect_type": ColumnDefinition(
        "Tipo de efecto reportado",
        extraction_placeholder="Positivo/Negativo/Mixto/No concluyente",
    ),
    "autonomy_relation": ColumnDefinition(
        "Relacion con autonomia", extraction_placeholder="Alta/Media/Baja/Nula"
    ),
    "dependency_relation": ColumnDefinition(
        "Relacion con dependencia cognitiva",
        extraction_placeholder="Alta/Media/Baja/Nula",
    ),
    "performance_relation": ColumnDefinition(
        "Relacion con rendimiento en programacion",
        extraction_placeholder="Alta/Media/Baja/Nula",
    ),
    "findings": ColumnDefinition("Hallazgos principales"),
    "limitations": ColumnDefinition("Limitaciones"),
    "relevance": ColumnDefinition(
        "Relevancia", extraction_placeholder="Alta/Media/Baja"
    ),
}


def load_metadata_config(path: Path | None = None) -> dict[str, list[str]]:
    config_path = path or DEFAULT_METADATA_CONFIG_PATH
    raw = _parse_simple_yaml_lists(config_path)
    screening = raw.get("screening_columns", [])
    extraction = raw.get("extraction_columns", [])

    _validate_column_keys(screening, "screening_columns")
    _validate_column_keys(extraction, "extraction_columns")

    return {
        "screening_columns": screening,
        "extraction_columns": extraction,
    }


def _parse_simple_yaml_lists(path: Path) -> dict[str, list[str]]:
    if not path.exists():
        raise FileNotFoundError(f"Metadata config not found: {path}")

    parsed: dict[str, list[str]] = {}
    current_key: str | None = None

    for lineno, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        if not raw_line.startswith((" ", "\t")) and stripped.endswith(":"):
            current_key = stripped[:-1].strip()
            parsed[current_key] = []
            continue

        if stripped.startswith("- "):
            if current_key is None:
                raise ValueError(
                    f"Invalid metadata config at line {lineno}: list item without section."
                )
            value = stripped[2:].strip().strip("'").strip('"')
            parsed[current_key].append(value)
            continue

        raise ValueError(
            f"Invalid metadata config at line {lineno}: unsupported syntax '{raw_line}'."
        )

    return parsed


def _validate_column_keys(keys: list[str], section: str) -> None:
    unknown = [key for key in keys if key not in COLUMN_DEFINITIONS]
    if unknown:
        raise ValueError(
            f"Unknown columns in {section}: {', '.join(unknown)}. "
            "Update metadata-columns.yaml or COLUMN_DEFINITIONS."
        )


def headers_for_columns(keys: list[str]) -> list[str]:
    return [COLUMN_DEFINITIONS[key].header for key in keys]


def render_markdown_header(headers: list[str]) -> list[str]:
    return [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join("---" for _ in headers) + "|",
    ]


def screening_template_row(keys: list[str]) -> list[str]:
    values: list[str] = []
    for key in keys:
        values.append(COLUMN_DEFINITIONS[key].screening_placeholder)
    values.extend(
        [
            "Incluir/Excluir/Dudoso",
            "",
            "",
            "Si/No",
            "Texto completo / Sin texto completo accesible",
            "",
        ]
    )
    return values


def extraction_template_row(keys: list[str]) -> list[str]:
    return [COLUMN_DEFINITIONS[key].extraction_placeholder for key in keys]
