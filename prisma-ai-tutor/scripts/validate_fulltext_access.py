#!/usr/bin/env python3
"""Validate full-text accessibility for a screened subset and update the matrix."""

from __future__ import annotations

import argparse
import csv
import os
from pathlib import Path
from urllib import error, request

from openalex_search import WORKSPACE_ROOT_KEY, resolve_workspace_path
from run_outputs import refresh_run_outputs


DEFAULT_TIMEOUT = 12.0
DEFAULT_DECISIONS = {"Incluir", "Dudoso"}


def is_matrix_data_row(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("|") and not stripped.startswith("|---")


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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate full-text accessibility for a screened subset and update the "
            "screening matrix in place."
        )
    )
    parser.add_argument(
        "--matrix",
        required=True,
        help="Path to the screening matrix Markdown file.",
    )
    parser.add_argument(
        "--decisions",
        required=True,
        help="CSV file with screening decisions used to define the subset to validate.",
    )
    parser.add_argument(
        "--mailto",
        help="Contact email used in the User-Agent during validation.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help=f"Timeout in seconds for each validation request. Default: {DEFAULT_TIMEOUT}.",
    )
    parser.add_argument(
        "--workspace-root",
        help=(
            "Optional workspace root used to resolve relative CLI paths. "
            f"Equivalent to {WORKSPACE_ROOT_KEY} for CLI-only scripts."
        ),
    )
    return parser.parse_args()


def load_decision_subset(path: Path) -> set[str]:
    with path.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    return {
        row.get("code", "").strip()
        for row in rows
        if row.get("decision", "").strip() in DEFAULT_DECISIONS and row.get("code", "").strip()
    }


def build_user_agent(mailto: str | None) -> str:
    return (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
    )


def build_headers(mailto: str | None) -> dict[str, str]:
    headers = {
        "User-Agent": build_user_agent(mailto),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/pdf,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "max-age=0",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-User": "?1",
        "Sec-Fetch-Dest": "document",
    }
    if mailto:
        headers["From"] = mailto
    return headers


def is_validated_fulltext_url(url: str, mailto: str | None, timeout: float) -> bool:
    headers = build_headers(mailto)
    req = request.Request(url, headers=headers)

    try:
        with request.urlopen(req, timeout=timeout) as response:
            final_url = response.geturl().lower()
            content_type = response.headers.get("Content-Type", "").lower()
            if response.status not in (200, 203):
                return False

            if "application/pdf" in content_type or final_url.endswith(".pdf"):
                return True

            known_fulltext_hosts = (
                "pmc.ncbi.nlm.nih.gov",
                "arxiv.org",
                "scielo.",
                "zenodo.org",
                "osf.io",
                "hal.science",
            )
            if any(host in final_url for host in known_fulltext_hosts):
                return True

            fulltext_markers = (
                "/pdf",
                "/article/",
                "/full",
                "/fulltext",
                "/download",
                "/viewcontent.cgi",
            )
            return "text/html" in content_type and any(marker in final_url for marker in fulltext_markers)
    except Exception:  # noqa: BLE001
        return False


def update_matrix(matrix_path: Path, target_codes: set[str], mailto: str | None, timeout: float) -> int:
    lines = matrix_path.read_text(encoding="utf-8").splitlines()
    updated: list[str] = []
    fulltext_idx: int | None = None
    access_url_idx: int | None = None
    changed = 0

    for line in lines:
        if line.startswith("| Codigo |") or line.startswith("| Código |"):
            parts = [part.strip() for part in line.strip().split("|")]
            columns = parts[1:-1]
            fulltext_idx = columns.index("Texto completo accesible") + 1
            access_url_idx = columns.index("URL de acceso") + 1
            updated.append(line)
            continue

        if not is_matrix_data_row(line):
            updated.append(line)
            continue

        parts = [part.strip() for part in line.strip().split("|")]
        code = parts[1]
        if code not in target_codes or fulltext_idx is None or access_url_idx is None:
            updated.append(line)
            continue

        access_url = parts[access_url_idx]
        if not access_url:
            parts[fulltext_idx] = "No"
        else:
            parts[fulltext_idx] = (
                "Si" if is_validated_fulltext_url(access_url, mailto, timeout) else "No confirmado"
            )
        changed += 1
        updated.append("| " + " | ".join(parts[1:-1]) + " |")

    matrix_path.write_text("\n".join(updated) + "\n", encoding="utf-8")
    return changed


def main() -> int:
    args = parse_args()
    env_config = {WORKSPACE_ROOT_KEY: args.workspace_root} if args.workspace_root else None
    matrix_path = resolve_workspace_path(args.matrix, None, env_config)
    decisions_path = resolve_workspace_path(args.decisions, None, env_config)

    if not matrix_path.exists():
        raise SystemExit(f"Matrix not found: {matrix_path}")
    if not decisions_path.exists():
        raise SystemExit(f"Decisions CSV not found: {decisions_path}")

    mailto = args.mailto or os.getenv("OPENALEX_MAILTO")
    target_codes = load_decision_subset(decisions_path)
    changed = update_matrix(matrix_path, target_codes, mailto, args.timeout)
    csv_path = matrix_path.with_suffix(".csv")
    export_matrix_csv(matrix_path, csv_path)
    run_dir = matrix_path.parent.parent if matrix_path.parent.name == "screening" else matrix_path.parent
    refresh_run_outputs(run_dir)
    print(f"Updated full-text accessibility for {changed} records in: {matrix_path}")
    print(f"Updated screening matrix CSV: {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
