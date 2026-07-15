#!/usr/bin/env python3
"""Audit source/evidence links and Markdown paragraph formatting in a synthesis."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


LINK_RE = re.compile(r"\[`(?P<label>[ML]\d+)`\]\((?P<target>[^)]+)\)")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate M/L links in narrative synthesis Markdown.")
    parser.add_argument("--synthesis", required=True)
    parser.add_argument("--report", help="JSON audit report.")
    return parser.parse_args()


def is_structural(line: str) -> bool:
    stripped = line.lstrip()
    return (
        not stripped
        or stripped.startswith(("#", "- ", "* ", ">", "|", "```", "~~~"))
        or bool(re.match(r"\d+\.\s", stripped))
    )


def audit(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8")
    links: list[dict[str, object]] = []
    errors: list[str] = []
    by_code: dict[str, set[str]] = {}
    for match in LINK_RE.finditer(text):
        label = match.group("label")
        target_raw = match.group("target").split("#", 1)[0]
        target = (path.parent / target_raw).resolve() if not Path(target_raw).is_absolute() else Path(target_raw)
        exists = target.is_file()
        suffix = target.suffix.casefold()
        expected_suffix = suffix in {".pdf", ".html", ".htm"} if label.startswith("M") else suffix == ".txt"
        code = re.match(r"M\d+", target.name)
        target_code = code.group(0) if code else ""
        line_valid: bool | None = None
        if label.startswith("L") and exists:
            line_number = int(label[1:])
            line_valid = 1 <= line_number <= len(target.read_text(encoding="utf-8", errors="ignore").splitlines())
        if not exists:
            errors.append(f"Missing target for {label}: {target_raw}")
        if not expected_suffix:
            errors.append(f"Wrong target type for {label}: {target_raw}")
        if line_valid is False:
            errors.append(f"Line locator outside target for {label}: {target_raw}")
        if target_code:
            by_code.setdefault(target_code, set()).add(label[0])
        links.append({
            "label": label, "target": target_raw, "resolved": str(target), "exists": exists,
            "target_type_valid": expected_suffix, "target_code": target_code, "line_valid": line_valid,
        })
    hard_wrap_lines: list[int] = []
    lines = text.splitlines()
    for index in range(len(lines) - 1):
        if not is_structural(lines[index]) and not is_structural(lines[index + 1]):
            hard_wrap_lines.append(index + 2)
    incomplete_pairs = sorted(code for code, kinds in by_code.items() if kinds != {"M", "L"})
    if incomplete_pairs:
        errors.append(f"Incomplete M/L pairs: {', '.join(incomplete_pairs)}")
    if hard_wrap_lines:
        errors.append(f"Possible hard-wrapped paragraphs at lines: {hard_wrap_lines[:20]}")
    return {
        "synthesis": str(path),
        "links": links,
        "link_count": len(links),
        "study_codes": len(by_code),
        "incomplete_pairs": incomplete_pairs,
        "possible_hard_wrap_lines": hard_wrap_lines,
        "errors": errors,
        "valid": not errors,
    }


def main() -> int:
    args = parse_args()
    path = Path(args.synthesis).expanduser().resolve()
    if not path.exists():
        raise SystemExit(f"Synthesis not found: {path}")
    result = audit(path)
    report = Path(args.report).expanduser().resolve() if args.report else path.parent / "study_link_audit.json"
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Links: {result['link_count']}; study codes: {result['study_codes']}; valid: {result['valid']}")
    print(f"Report: {report}")
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
