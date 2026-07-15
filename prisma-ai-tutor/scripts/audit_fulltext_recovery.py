#!/usr/bin/env python3
"""Reclassify locally saved recovery artifacts by their actual content."""

from __future__ import annotations

import argparse
import csv
import os
from collections import Counter
from pathlib import Path

from fulltext_utils import classify_payload
from openalex_search import WORKSPACE_ROOT_KEY, resolve_workspace_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit saved PDF/HTML artifacts and identify false full-text/landing classifications."
    )
    parser.add_argument("--download-log", required=True)
    parser.add_argument("--audit-log", help="Detailed CSV audit output.")
    parser.add_argument("--summary", help="Markdown audit summary.")
    parser.add_argument("--apply", action="store_true", help="Apply verified classifications to the download log.")
    parser.add_argument("--workspace-root")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    env = {WORKSPACE_ROOT_KEY: args.workspace_root} if args.workspace_root else None
    download_log = resolve_workspace_path(args.download_log, None, env)
    audit_log = (
        resolve_workspace_path(args.audit_log, None, env)
        if args.audit_log else download_log.with_name("fulltext_content_audit.csv")
    )
    summary = (
        resolve_workspace_path(args.summary, None, env)
        if args.summary else download_log.with_name("fulltext_content_audit.md")
    )
    with download_log.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames
        rows = list(reader)
    if not fields:
        raise SystemExit("Download log has no header.")

    audit_rows: list[dict[str, str]] = []
    for row in rows:
        path_value = row.get("local_path", "").strip()
        if not path_value or not Path(path_value).exists():
            continue
        payload = Path(path_value).read_bytes()
        status, kind, evidence = classify_payload(
            row.get("final_url", ""), row.get("content_type", ""), payload,
        )
        old_kind = row.get("access_kind", "")
        changed = old_kind != kind
        audit_rows.append({
            "code": row.get("code", ""),
            "local_path": path_value,
            "old_status": row.get("status", ""),
            "old_access_kind": old_kind,
            "audited_status": status,
            "audited_access_kind": kind,
            "changed": "Si" if changed else "No",
            "evidence": evidence,
        })
        if args.apply:
            row["status"] = status
            row["access_kind"] = kind
            row["message"] = "Content audit: " + evidence

    audit_fields = [
        "code", "local_path", "old_status", "old_access_kind",
        "audited_status", "audited_access_kind", "changed", "evidence",
    ]
    audit_log.parent.mkdir(parents=True, exist_ok=True)
    with audit_log.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=audit_fields)
        writer.writeheader()
        writer.writerows(audit_rows)
    if args.apply:
        tmp = download_log.with_suffix(".csv.tmp")
        with tmp.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        os.replace(tmp, download_log)

    old_counts = Counter(row["old_access_kind"] for row in audit_rows)
    audited_counts = Counter(row["audited_access_kind"] for row in audit_rows)
    changed_codes = [row["code"] for row in audit_rows if row["changed"] == "Si"]
    lines = [
        "# Auditoría de contenido recuperado", "",
        f"- Archivos auditados: {len(audit_rows)}",
        f"- Clasificaciones modificadas: {len(changed_codes)}",
        f"- Cambios aplicados al log: {'Si' if args.apply else 'No'}",
        "", "## Antes", "",
    ]
    for key in sorted(old_counts):
        lines.append(f"- {key or 'sin_clasificar'}: {old_counts[key]}")
    lines.extend(["", "## Después", ""])
    for key in sorted(audited_counts):
        lines.append(f"- {key or 'sin_clasificar'}: {audited_counts[key]}")
    lines.extend(["", "## Códigos reclasificados", "", ", ".join(changed_codes) if changed_codes else "ninguno", ""])
    summary.write_text("\n".join(lines), encoding="utf-8")
    print(f"Audited {len(audit_rows)} local artifacts; changed={len(changed_codes)}; applied={args.apply}.")
    print(f"Audit log: {audit_log}")
    print(f"Audit summary: {summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
