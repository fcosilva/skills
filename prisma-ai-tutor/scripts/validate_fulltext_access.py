#!/usr/bin/env python3
"""Validate full-text accessibility for a screened subset and update the matrix."""

from __future__ import annotations

import argparse
import csv
import os
from pathlib import Path
from urllib import error, request

from fulltext_utils import classify_payload
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
    parser.add_argument("--log", help="Incremental CSV validation log.")
    parser.add_argument("--resume", action="store_true", help="Reuse completed URL checks from the log.")
    parser.add_argument("--progress-every", type=int, default=25)
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
    return validate_fulltext_url(url, mailto, timeout)[0]


def validate_fulltext_url(url: str, mailto: str | None, timeout: float) -> tuple[bool, str, str, str]:
    headers = build_headers(mailto)
    req = request.Request(url, headers=headers)

    try:
        with request.urlopen(req, timeout=timeout) as response:
            final_url = response.geturl()
            content_type = response.headers.get("Content-Type", "").split(";")[0].strip().lower()
            if response.status not in (200, 203):
                return False, "", f"http_{response.status}", final_url
            payload = response.read(2_000_000)
            status, access_kind, evidence = classify_payload(final_url, content_type, payload)
            return access_kind in {"pdf_fulltext", "html_fulltext"}, access_kind, f"{status}: {evidence}", final_url
    except Exception as exc:  # noqa: BLE001
        return False, "", f"request_error: {exc}", ""


def markdown_cell(value: str) -> str:
    return value.replace("\r", " ").replace("\n", " ").replace("|", r"\|")


def write_matrix_pair(csv_path: Path, md_path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    csv_tmp = csv_path.with_name(csv_path.name + ".tmp")
    md_tmp = md_path.with_name(md_path.name + ".tmp")
    with csv_tmp.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    with md_tmp.open("w", encoding="utf-8") as handle:
        handle.write("# Matriz de cribado (seleccion de estudios)\n\n")
        handle.write("| " + " | ".join(fields) + " |\n")
        handle.write("|" + "|".join("---" for _ in fields) + "|\n")
        for row in rows:
            handle.write("| " + " | ".join(markdown_cell(row.get(field, "")) for field in fields) + " |\n")
    os.replace(csv_tmp, csv_path)
    os.replace(md_tmp, md_path)


VALIDATION_FIELDS = ["code", "url", "final_url", "remote_fulltext", "access_kind", "message"]


def write_validation_log(path: Path, rows: list[dict[str, str]]) -> None:
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=VALIDATION_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temporary, path)


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
            parts[fulltext_idx] = "No confirmado"
        else:
            parts[fulltext_idx] = (
                "Por verificar" if is_validated_fulltext_url(access_url, mailto, timeout) else "No confirmado"
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
    csv_path = matrix_path if matrix_path.suffix.lower() == ".csv" else matrix_path.with_suffix(".csv")
    md_path = matrix_path if matrix_path.suffix.lower() == ".md" else matrix_path.with_suffix(".md")
    log_path = (
        resolve_workspace_path(args.log, None, env_config)
        if args.log
        else matrix_path.parent.parent / "fulltext" / "fulltext_access_validation_log.csv"
    )

    if not matrix_path.exists():
        raise SystemExit(f"Matrix not found: {matrix_path}")
    if not decisions_path.exists():
        raise SystemExit(f"Decisions CSV not found: {decisions_path}")
    if not csv_path.exists():
        if matrix_path.suffix.lower() == ".md":
            export_matrix_csv(matrix_path, csv_path)
        else:
            raise SystemExit(f"Screening matrix CSV not found: {csv_path}")

    mailto = args.mailto or os.getenv("OPENALEX_MAILTO")
    target_codes = load_decision_subset(decisions_path)
    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames or []
        rows = list(reader)
    if "Codigo" not in fields or "URL de acceso" not in fields or "Texto completo accesible" not in fields:
        raise SystemExit("Unexpected screening matrix schema.")
    if any(None in row for row in rows):
        raise SystemExit("Malformed screening matrix CSV: one or more rows have extra columns.")

    log_path.parent.mkdir(parents=True, exist_ok=True)
    previous: dict[str, dict[str, str]] = {}
    if args.resume and log_path.exists():
        with log_path.open(encoding="utf-8-sig", newline="") as handle:
            previous = {row.get("code", ""): row for row in csv.DictReader(handle)}
    results: list[dict[str, str]] = []
    changed = 0
    targets_seen: set[str] = set()
    for row in rows:
        code = row.get("Codigo", "").strip()
        if code not in target_codes:
            continue
        targets_seen.add(code)
        url = row.get("URL de acceso", "").strip()
        cached = previous.get(code) if args.resume else None
        if cached and cached.get("url") == url:
            result = cached
            verified = cached.get("remote_fulltext") == "Si"
        elif not url:
            verified = False
            result = {
                "code": code, "url": "", "final_url": "", "remote_fulltext": "No",
                "access_kind": "", "message": "missing_access_url",
            }
        else:
            verified, kind, message, final_url = validate_fulltext_url(url, mailto, args.timeout)
            result = {
                "code": code, "url": url, "final_url": final_url,
                "remote_fulltext": "Si" if verified else "No",
                "access_kind": kind, "message": message,
            }
        # Remote validation is only a retrieval lead. Final "Si" is reserved
        # for locally prepared text with confirmed bibliographic identity.
        value = "Por verificar" if verified else "No confirmado"
        if row.get("Texto completo accesible", "") != value:
            row["Texto completo accesible"] = value
            changed += 1
        results.append(result)
        write_validation_log(log_path, results)
        if args.progress_every and len(results) % max(args.progress_every, 1) == 0:
            print(f"Validated {len(results)} / {len(target_codes)} access URLs...", flush=True)
    missing = sorted(target_codes - targets_seen)
    if missing:
        raise SystemExit(f"Decision codes missing from screening matrix: {', '.join(missing[:10])}")
    write_matrix_pair(csv_path, md_path, fields, rows)
    run_dir = matrix_path.parent.parent if matrix_path.parent.name == "screening" else matrix_path.parent
    refresh_run_outputs(run_dir)
    print(f"Updated provisional full-text accessibility for {changed} records in: {matrix_path}")
    print(f"Updated screening matrix CSV: {csv_path}")
    print(f"Validation log: {log_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
