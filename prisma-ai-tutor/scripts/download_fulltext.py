#!/usr/bin/env python3
"""Download locally accessible full-text files for a screened subset."""

from __future__ import annotations

import argparse
import csv
import http.cookiejar
import os
import re
from collections import Counter
from pathlib import Path
from urllib import error, request

from openalex_search import WORKSPACE_ROOT_KEY, load_env_config, resolve_workspace_path
from run_outputs import refresh_run_outputs


DEFAULT_TIMEOUT = 20.0
DEFAULT_DECISIONS = ("Incluir", "Dudoso")
PROGRESS_EVERY = 10
PROGRESS_EVERY_ENV = "PRISMA_PROGRESS_DOWNLOAD_EVERY"


def is_matrix_data_row(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("|") and not stripped.startswith("|---")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Download accessible full-text files for a screened subset using the "
            "screening matrix and decisions CSV."
        )
    )
    parser.add_argument("--matrix", required=True, help="Path to screening/screening_matrix.md.")
    parser.add_argument("--decisions", required=True, help="Path to screening decisions CSV.")
    parser.add_argument(
        "--decision",
        action="append",
        dest="decision_filters",
        help=(
            "Decision label to include in the recovery subset. Can be passed multiple "
            "times. Default: Incluir and Dudoso."
        ),
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory where downloaded full-text files will be stored.",
    )
    parser.add_argument(
        "--log",
        help="Optional CSV log path. Default: outputs/<run>/fulltext/fulltext_download_log.csv.",
    )
    parser.add_argument(
        "--summary",
        help="Optional Markdown summary path. Default: outputs/<run>/fulltext/fulltext_recovery_summary.md.",
    )
    parser.add_argument(
        "--cookies-file",
        help=(
            "Optional Netscape/Mozilla cookies file exported from a browser session. "
            "Useful for sites protected by challenges or authenticated sessions."
        ),
    )
    parser.add_argument(
        "--config-file",
        help="Optional .env-style config file to read OPENALEX_MAILTO from.",
    )
    parser.add_argument("--mailto", help="Optional contact email for the User-Agent.")
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help=f"Timeout in seconds per download. Default: {DEFAULT_TIMEOUT}.",
    )
    parser.add_argument(
        "--progress-every",
        type=int,
        default=None,
        help=(
            "Show recovery progress every N processed records. "
            f"Default: {PROGRESS_EVERY_ENV} or {PROGRESS_EVERY}."
        ),
    )
    parser.add_argument(
        "--workspace-root",
        help=(
            "Optional workspace root used to resolve relative CLI paths. "
            f"Overrides {WORKSPACE_ROOT_KEY} for this run."
        ),
    )
    return parser.parse_args()


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


def build_opener(mailto: str | None, cookies_file: Path | None) -> request.OpenerDirector:
    handlers: list[request.BaseHandler] = []
    if cookies_file:
        jar = http.cookiejar.MozillaCookieJar(str(cookies_file))
        jar.load(ignore_discard=True, ignore_expires=True)
        handlers.append(request.HTTPCookieProcessor(jar))
    opener = request.build_opener(*handlers)
    opener.addheaders = list(build_headers(mailto).items())
    return opener


def load_target_codes(path: Path, allowed_decisions: set[str]) -> list[dict[str, str]]:
    with path.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    return [
        row
        for row in rows
        if row.get("decision", "").strip() in allowed_decisions and row.get("code", "").strip()
    ]


def resolve_progress_every(cli_value: int | None, env_values: dict[str, str]) -> int:
    if cli_value is not None:
        return max(cli_value, 0)
    raw = env_values.get(PROGRESS_EVERY_ENV, "").strip()
    if not raw:
        return PROGRESS_EVERY
    try:
        return max(int(raw), 0)
    except ValueError:
        return PROGRESS_EVERY


def parse_markdown_matrix(path: Path) -> dict[str, dict[str, str]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    header: list[str] | None = None
    rows: dict[str, dict[str, str]] = {}

    for line in lines:
        if line.startswith("| Codigo |") or line.startswith("| Código |"):
            parts = [part.strip() for part in line.strip().split("|")]
            header = parts[1:-1]
            continue
        if not is_matrix_data_row(line) or header is None:
            continue
        parts = [part.strip() for part in line.strip().split("|")]
        values = parts[1:-1]
        if len(values) != len(header):
            continue
        row = dict(zip(header, values, strict=False))
        code = row.get("Codigo", "").strip() or row.get("Código", "").strip()
        if code:
            rows[code] = row
    return rows


def choose_source_url(row: dict[str, str]) -> str:
    access_url = row.get("URL de acceso", "").strip()
    doi_url = row.get("URL DOI", "").strip()
    if access_url:
        return access_url
    return doi_url


def has_open_access(row: dict[str, str]) -> bool:
    return row.get("Acceso abierto", "").strip().lower() == "si"


def is_known_fulltext_html(final_url: str) -> bool:
    final = final_url.lower()
    known_hosts = (
        "pmc.ncbi.nlm.nih.gov",
        "arxiv.org",
        "scielo.",
        "zenodo.org",
        "osf.io",
        "hal.science",
        "link.springer.com",
    )
    if any(host in final for host in known_hosts):
        return True
    html_markers = (
        "/article/",
        "/full",
        "/fulltext",
        "/viewcontent.cgi",
        "/record/",
    )
    return any(marker in final for marker in html_markers)


def is_blocked_or_error_html(text_snippet: str, final_url: str) -> bool:
    blocked_markers = (
        "access denied",
        "forbidden",
        "sign in",
        "institutional access",
        "purchase access",
        "buy article",
        "captcha",
        "cloudflare",
        "temporarily unavailable",
        "checking your browser",
        "login",
        "error",
    )
    if any(marker in text_snippet for marker in blocked_markers):
        return True
    return any(marker in final_url for marker in ("/login", "/signin", "/access", "/error"))


def has_article_like_html(text_snippet: str) -> bool:
    article_markers = (
        "<article",
        'name="citation_title"',
        "citation_pdf_url",
        "dc.type",
        "abstract",
        "references",
        "introduction",
        "method",
        "results",
        "discussion",
    )
    return any(marker in text_snippet for marker in article_markers)


def classify_download(final_url: str, content_type: str, payload: bytes) -> tuple[str, str]:
    final = final_url.lower()
    text_snippet = payload[:3000].decode("utf-8", errors="ignore").lower()
    if "application/pdf" in content_type or final.endswith(".pdf"):
        return "downloaded_pdf", "pdf_fulltext"
    if "text/html" in content_type:
        if is_blocked_or_error_html(text_snippet, final):
            return "downloaded_blocked_page", "blocked_or_error"
        if is_known_fulltext_html(final) and has_article_like_html(text_snippet):
            return "downloaded_fulltext_html", "html_fulltext"
        if has_article_like_html(text_snippet):
            return "downloaded_fulltext_html", "html_fulltext"
        return "downloaded_landing_page", "landing_metadata_only"
    return "downloaded_binary", "binary"


def guess_extension(final_url: str, content_type: str) -> str:
    final = final_url.lower()
    if "application/pdf" in content_type or final.endswith(".pdf"):
        return ".pdf"
    if "text/html" in content_type or final.endswith(".html") or final.endswith(".htm"):
        return ".html"
    return ".bin"


def slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")[:80] or "document"


def download_one(
    code: str,
    title: str,
    url: str,
    output_dir: Path,
    opener: request.OpenerDirector,
    mailto: str | None,
    timeout: float,
) -> dict[str, str]:
    result = {
        "code": code,
        "title": title,
        "source_url": url,
        "final_url": "",
        "status": "",
        "access_kind": "",
        "content_type": "",
        "local_path": "",
        "message": "",
    }
    if not url:
        result["status"] = "missing_url"
        result["message"] = "No source URL available."
        return result

    req = request.Request(url, headers=build_headers(mailto))

    try:
        with opener.open(req, timeout=timeout) as response:
            final_url = response.geturl()
            content_type = response.headers.get("Content-Type", "").split(";")[0].strip().lower()
            payload = response.read()
            status, access_kind = classify_download(final_url, content_type, payload)
            ext = guess_extension(final_url, content_type)
            filename = f"{code}_{slugify(title)}{ext}"
            destination = output_dir / filename
            destination.write_bytes(payload)
            result.update(
                {
                    "final_url": final_url,
                    "status": status,
                    "access_kind": access_kind,
                    "content_type": content_type,
                    "local_path": str(destination),
                    "message": f"Saved {len(payload)} bytes.",
                }
            )
            return result
    except error.HTTPError as exc:
        result["status"] = f"http_{exc.code}"
        result["message"] = str(exc)
    except error.URLError as exc:
        result["status"] = "url_error"
        result["message"] = str(exc.reason)
    except Exception as exc:  # noqa: BLE001
        result["status"] = "error"
        result["message"] = str(exc)
    return result


def write_log(path: Path, rows: list[dict[str, str]]) -> None:
    fieldnames = [
        "code",
        "title",
        "source_url",
        "final_url",
        "status",
        "access_kind",
        "content_type",
        "local_path",
        "message",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_summary(path: Path, output_dir: Path, rows: list[dict[str, str]]) -> None:
    status_counts = Counter(row.get("status", "").strip() for row in rows)
    kind_counts = Counter(row.get("access_kind", "").strip() for row in rows if row.get("access_kind", "").strip())
    downloaded_codes = [row["code"] for row in rows if row.get("status", "").startswith("downloaded_")]
    fulltext_codes = [
        row["code"]
        for row in rows
        if row.get("access_kind") in {"pdf_fulltext", "html_fulltext"}
    ]
    landing_codes = [row["code"] for row in rows if row.get("access_kind") == "landing_metadata_only"]
    blocked_codes = [
        row["code"]
        for row in rows
        if row.get("access_kind") == "blocked_or_error" or row.get("status", "").startswith("http_")
    ]
    skipped_codes = [row["code"] for row in rows if row.get("status") == "skipped_non_oa"]
    lines = [
        "# Resumen de recuperación de texto completo",
        "",
        f"- Directorio local: `{output_dir}`",
        f"- Total intentos: `{len(rows)}`",
        f"- Descargas guardadas: `{len(downloaded_codes)}`",
        f"- Full text claro (`pdf_fulltext` o `html_fulltext`): `{len(fulltext_codes)}`",
        f"- Landing con metadata solamente: `{len(landing_codes)}`",
        f"- Bloqueados o error: `{len(blocked_codes)}`",
        f"- Omitidos por no ser open access: `{len(skipped_codes)}`",
        "",
        "## Conteo por estado",
        "",
    ]
    for key in sorted(status_counts):
        lines.append(f"- `{key}`: `{status_counts[key]}`")
    if kind_counts:
        lines.extend(["", "## Conteo por tipo de acceso", ""])
        for key in sorted(kind_counts):
            lines.append(f"- `{key}`: `{kind_counts[key]}`")
    lines.extend(
        [
            "",
            "## Identificadores clave",
            "",
            f"- Full text claro: `{', '.join(fulltext_codes) if fulltext_codes else 'ninguno'}`",
            f"- Landing con metadata solamente: `{', '.join(landing_codes) if landing_codes else 'ninguno'}`",
            f"- Bloqueados o error: `{', '.join(blocked_codes) if blocked_codes else 'ninguno'}`",
            f"- Omitidos por no ser open access: `{', '.join(skipped_codes) if skipped_codes else 'ninguno'}`",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = parse_args()
    config_file = Path(args.config_file).expanduser().resolve() if args.config_file else None
    env_values = load_env_config(config_file) if config_file else {}
    if args.workspace_root:
        env_values[WORKSPACE_ROOT_KEY] = args.workspace_root

    matrix_path = resolve_workspace_path(args.matrix, config_file, env_values)
    decisions_path = resolve_workspace_path(args.decisions, config_file, env_values)
    output_dir = resolve_workspace_path(args.output_dir, config_file, env_values)
    log_path = (
        resolve_workspace_path(args.log, config_file, env_values)
        if args.log
        else decisions_path.parent.parent / "fulltext" / "fulltext_download_log.csv"
    )
    summary_path = (
        resolve_workspace_path(args.summary, config_file, env_values)
        if args.summary
        else decisions_path.parent.parent / "fulltext" / "fulltext_recovery_summary.md"
    )
    cookies_path = (
        resolve_workspace_path(args.cookies_file, config_file, env_values)
        if args.cookies_file
        else None
    )

    if not matrix_path.exists():
        raise SystemExit(f"Matrix not found: {matrix_path}")
    if not decisions_path.exists():
        raise SystemExit(f"Decisions CSV not found: {decisions_path}")
    if cookies_path and not cookies_path.exists():
        raise SystemExit(f"Cookies file not found: {cookies_path}")

    mailto = args.mailto or env_values.get("OPENALEX_MAILTO") or os.getenv("OPENALEX_MAILTO")
    opener = build_opener(mailto, cookies_path)
    progress_every = resolve_progress_every(args.progress_every, env_values)
    allowed_decisions = {
        value.strip()
        for value in (args.decision_filters or DEFAULT_DECISIONS)
        if value.strip()
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)

    matrix_rows = parse_markdown_matrix(matrix_path)
    target_rows = load_target_codes(decisions_path, allowed_decisions)
    results: list[dict[str, str]] = []

    for row in target_rows:
        code = row.get("code", "").strip()
        matrix_row = matrix_rows.get(code)
        if not matrix_row:
            results.append(
                {
                    "code": code,
                    "title": "",
                    "source_url": "",
                    "final_url": "",
                    "status": "missing_matrix_row",
                    "content_type": "",
                    "local_path": "",
                    "message": "Code not found in matrix.",
                }
            )
            continue
        if not has_open_access(matrix_row):
            results.append(
                {
                    "code": code,
                    "title": matrix_row.get("Titulo", "").strip(),
                    "source_url": "",
                    "final_url": "",
                    "status": "skipped_non_oa",
                    "access_kind": "metadata_only",
                    "content_type": "",
                    "local_path": "",
                    "message": "Skipped automatic recovery because Acceso abierto != Si.",
                }
            )
            if progress_every and len(results) % progress_every == 0:
                print(f"Processed {len(results)} / {len(target_rows)} recovery targets...")
            continue
        title = matrix_row.get("Titulo", "").strip()
        url = choose_source_url(matrix_row)
        results.append(download_one(code, title, url, output_dir, opener, mailto, args.timeout))
        if progress_every and len(results) % progress_every == 0:
            print(f"Processed {len(results)} / {len(target_rows)} recovery targets...")

    write_log(log_path, results)
    write_summary(summary_path, output_dir, results)
    refresh_run_outputs(summary_path.parent.parent)
    downloaded = sum(1 for row in results if row["status"].startswith("downloaded_"))
    print(f"Downloaded {downloaded} files to: {output_dir}")
    print(f"Included decisions: {', '.join(sorted(allowed_decisions))}")
    print(f"Download log: {log_path}")
    print(f"Recovery summary: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
