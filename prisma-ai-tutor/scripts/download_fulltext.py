#!/usr/bin/env python3
"""Recover screened full text through multiple legitimate open-access routes."""

from __future__ import annotations

import argparse
import csv
import http.cookiejar
import json
import os
import re
import time
from collections import Counter, deque
from pathlib import Path
from urllib import error, parse, request

from fulltext_utils import (
    candidate_document_links,
    classify_payload,
    deduplicate,
    is_pdf_payload,
    looks_like_html,
    normalize_doi,
)
from openalex_search import WORKSPACE_ROOT_KEY, load_env_config, resolve_workspace_path
from run_outputs import refresh_run_outputs

DEFAULT_TIMEOUT = 20.0
DEFAULT_DECISIONS = ("Incluir", "Dudoso")
DEFAULT_DISCOVERY_SOURCES = ("openalex", "unpaywall", "europepmc")
PROGRESS_EVERY = 10
PROGRESS_EVERY_ENV = "PRISMA_PROGRESS_DOWNLOAD_EVERY"
DISCOVERY_SOURCES_ENV = "PRISMA_FULLTEXT_DISCOVERY_SOURCES"
REQUEST_DELAY_ENV = "PRISMA_FULLTEXT_REQUEST_DELAY"
MAX_LINKED_ENV = "PRISMA_FULLTEXT_MAX_LINKED_CANDIDATES"
TRY_NON_OA_DIRECT_ENV = "PRISMA_FULLTEXT_TRY_NON_OA_DIRECT"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Recover PDF/HTML using matrix URLs, DOI discovery APIs, and links declared in HTML."
    )
    parser.add_argument("--matrix", required=True, help="Screening matrix Markdown or CSV.")
    parser.add_argument("--decisions", required=True, help="Screening decisions CSV.")
    parser.add_argument("--decision", action="append", dest="decision_filters")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--log", help="Final per-record recovery log.")
    parser.add_argument("--attempt-log", help="Detailed per-URL attempt log.")
    parser.add_argument("--summary", help="Markdown recovery summary.")
    parser.add_argument("--cookies-file", help="Authorized Netscape/Mozilla browser cookies file.")
    parser.add_argument("--config-file", help=".env-style configuration file.")
    parser.add_argument("--mailto", help="Contact email for polite API requests and Unpaywall.")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument("--progress-every", type=int)
    parser.add_argument("--request-delay", type=float)
    parser.add_argument("--max-linked-candidates", type=int)
    parser.add_argument(
        "--discovery-source", action="append", choices=DEFAULT_DISCOVERY_SOURCES,
        help="OA discovery source; repeat as needed.",
    )
    parser.add_argument("--no-discovery", action="store_true")
    parser.add_argument(
        "--try-non-oa-direct", action="store_true",
        help="Try DOI/publisher URLs even when matrix metadata says the work is not OA.",
    )
    parser.add_argument("--resume", action="store_true", help="Reuse previously verified local full text.")
    parser.add_argument("--workspace-root")
    return parser.parse_args()


def build_user_agent(mailto: str | None) -> str:
    contact = f"mailto:{mailto}" if mailto else "no-contact"
    return f"PRISMA-AI-Tutor/1.2 ({contact})"


def build_headers(mailto: str | None) -> dict[str, str]:
    headers = {
        "User-Agent": build_user_agent(mailto),
        "Accept": "text/html,application/xhtml+xml,application/pdf,application/json;q=0.9,*/*;q=0.7",
        "Accept-Language": "en,es;q=0.8,pt;q=0.7",
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


def load_target_codes(path: Path, allowed: set[str]) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return [
            row for row in csv.DictReader(handle)
            if row.get("decision", "").strip() in allowed and row.get("code", "").strip()
        ]


def load_matrix_rows(path: Path) -> dict[str, dict[str, str]]:
    csv_path = path if path.suffix.lower() == ".csv" else path.with_suffix(".csv")
    if csv_path.exists():
        with csv_path.open(encoding="utf-8-sig", newline="") as handle:
            return {row["Codigo"].strip(): row for row in csv.DictReader(handle) if row.get("Codigo", "").strip()}
    lines = path.read_text(encoding="utf-8").splitlines()
    table = [line for line in lines if line.startswith("|")]
    if len(table) < 3:
        return {}
    splitter = re.compile(r"(?<!\\)\|")
    def cells(line: str) -> list[str]:
        return [part.strip().replace(r"\|", "|") for part in splitter.split(line[1:-1])]
    header = cells(table[0])
    rows: dict[str, dict[str, str]] = {}
    for line in table[2:]:
        values = cells(line)
        if len(values) == len(header):
            row = dict(zip(header, values))
            code = row.get("Codigo", "").strip()
            if code:
                rows[code] = row
    return rows


def resolve_progress_every(value: int | None, env_values: dict[str, str]) -> int:
    if value is not None:
        return max(value, 0)
    try:
        return max(int(env_values.get(PROGRESS_EVERY_ENV, PROGRESS_EVERY)), 0)
    except ValueError:
        return PROGRESS_EVERY


def env_bool(value: str | None) -> bool:
    return (value or "").strip().casefold() in {"1", "true", "yes", "si", "sí", "on"}


def resolve_runtime_options(args: argparse.Namespace, env_values: dict[str, str]) -> tuple[tuple[str, ...], float, int, bool]:
    if args.no_discovery:
        sources: tuple[str, ...] = ()
    elif args.discovery_source:
        sources = tuple(args.discovery_source)
    else:
        raw_sources = env_values.get(DISCOVERY_SOURCES_ENV, ",".join(DEFAULT_DISCOVERY_SOURCES))
        configured = tuple(part.strip().casefold() for part in raw_sources.split(",") if part.strip())
        invalid = sorted(set(configured) - set(DEFAULT_DISCOVERY_SOURCES))
        if invalid:
            raise SystemExit(
                f"Invalid {DISCOVERY_SOURCES_ENV}: {', '.join(invalid)}. "
                f"Allowed: {', '.join(DEFAULT_DISCOVERY_SOURCES)}."
            )
        sources = configured
    try:
        request_delay = args.request_delay if args.request_delay is not None else float(
            env_values.get(REQUEST_DELAY_ENV, "0") or 0
        )
        max_linked = args.max_linked_candidates if args.max_linked_candidates is not None else int(
            env_values.get(MAX_LINKED_ENV, "6") or 6
        )
    except ValueError as exc:
        raise SystemExit(f"Invalid full-text recovery configuration: {exc}") from exc
    try_non_oa_direct = args.try_non_oa_direct or env_bool(env_values.get(TRY_NON_OA_DIRECT_ENV))
    return sources, max(request_delay, 0.0), max(max_linked, 0), try_non_oa_direct


def has_open_access(row: dict[str, str]) -> bool:
    return row.get("Acceso abierto", "").strip().casefold() == "si"


def row_doi(row: dict[str, str]) -> str:
    return normalize_doi(row.get("DOI", "") or row.get("URL DOI", ""))


def fetch_json(opener: request.OpenerDirector, url: str, timeout: float) -> dict:
    req = request.Request(url, headers={"Accept": "application/json"})
    with opener.open(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def discover_openalex(doi: str, opener: request.OpenerDirector, mailto: str | None, timeout: float) -> list[str]:
    if not doi:
        return []
    url = "https://api.openalex.org/works/https://doi.org/" + parse.quote(doi, safe="/:")
    if mailto:
        url += "?mailto=" + parse.quote(mailto)
    data = fetch_json(opener, url, timeout)
    best = data.get("best_oa_location") or {}
    locations = [best] if best else []
    locations.extend(
        location for location in (data.get("locations") or [])
        if isinstance(location, dict) and location.get("is_oa") is True
    )
    pdf_values: list[str] = []
    landing_values: list[str] = []
    for location in locations:
        if isinstance(location, dict):
            pdf_values.append(location.get("pdf_url") or "")
            landing_values.append(location.get("landing_page_url") or "")
    return deduplicate(pdf_values + landing_values)


def discover_unpaywall(doi: str, opener: request.OpenerDirector, mailto: str | None, timeout: float) -> list[str]:
    if not doi or not mailto:
        return []
    url = f"https://api.unpaywall.org/v2/{parse.quote(doi, safe='')}?email={parse.quote(mailto)}"
    data = fetch_json(opener, url, timeout)
    locations = [data.get("best_oa_location") or {}]
    locations.extend(data.get("oa_locations") or [])
    values: list[str] = []
    for location in locations:
        if isinstance(location, dict):
            values.extend([location.get("url_for_pdf") or "", location.get("url") or ""])
    return deduplicate(values)


def discover_europepmc(doi: str, opener: request.OpenerDirector, timeout: float) -> list[str]:
    if not doi:
        return []
    query = parse.quote(f'DOI:"{doi}"')
    url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/search?query={query}&format=json"
    results = (fetch_json(opener, url, timeout).get("resultList") or {}).get("result") or []
    values: list[str] = []
    for result in results[:3]:
        pmcid = result.get("pmcid")
        if pmcid:
            values.extend([
                f"https://europepmc.org/articles/{pmcid}",
                f"https://europepmc.org/articles/{pmcid}?pdf=render",
            ])
    return deduplicate(values)


def discover_urls(
    doi: str, sources: tuple[str, ...], opener: request.OpenerDirector,
    mailto: str | None, timeout: float,
) -> list[tuple[str, str]]:
    discovered: list[tuple[str, str]] = []
    for source in sources:
        try:
            if source == "openalex":
                urls = discover_openalex(doi, opener, mailto, timeout)
            elif source == "unpaywall":
                urls = discover_unpaywall(doi, opener, mailto, timeout)
            else:
                urls = discover_europepmc(doi, opener, timeout)
            discovered.extend((source, url) for url in urls)
        except Exception:
            continue
    seen: set[str] = set()
    output: list[tuple[str, str]] = []
    for route, url in discovered:
        if url and url not in seen:
            seen.add(url)
            output.append((route, url))
    return output


def initial_candidates(
    row: dict[str, str], discovery_sources: tuple[str, ...],
    opener: request.OpenerDirector, mailto: str | None, timeout: float,
    try_non_oa_direct: bool,
) -> list[tuple[str, str]]:
    values: list[tuple[str, str]] = []
    access_url = row.get("URL de acceso", "").strip()
    doi_url = row.get("URL DOI", "").strip()
    doi = row_doi(row)
    if access_url:
        values.append(("matrix_access", access_url))
    values.extend(discover_urls(doi, discovery_sources, opener, mailto, timeout))
    if has_open_access(row) or try_non_oa_direct:
        if doi_url:
            values.append(("matrix_doi", doi_url))
        elif doi:
            values.append(("doi", f"https://doi.org/{doi}"))
    seen: set[str] = set()
    output: list[tuple[str, str]] = []
    for route, url in values:
        if url and url not in seen:
            seen.add(url)
            output.append((route, url))
    return output


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.casefold()).strip("-")[:80] or "document"


def save_payload(code: str, title: str, payload: bytes, content_type: str, output_dir: Path) -> Path:
    suffix = ".pdf" if is_pdf_payload(payload) else ".html" if looks_like_html(payload, content_type) else ".bin"
    destination = output_dir / f"{code}_{slugify(title)}{suffix}"
    destination.write_bytes(payload)
    return destination


def attempt_url(
    code: str, route: str, url: str, opener: request.OpenerDirector,
    mailto: str | None, timeout: float,
) -> tuple[dict[str, str], bytes]:
    result = {
        "code": code, "route": route, "url": url, "final_url": "", "status": "",
        "access_kind": "", "content_type": "", "message": "",
    }
    try:
        req = request.Request(url, headers=build_headers(mailto))
        with opener.open(req, timeout=timeout) as response:
            payload = response.read()
            final_url = response.geturl()
            content_type = response.headers.get("Content-Type", "").split(";")[0].strip().lower()
            status, kind, evidence = classify_payload(final_url, content_type, payload)
            result.update(
                final_url=final_url, status=status, access_kind=kind,
                content_type=content_type, message=evidence,
            )
            return result, payload
    except error.HTTPError as exc:
        result.update(status=f"http_{exc.code}", message=str(exc))
    except error.URLError as exc:
        result.update(status="url_error", message=str(exc.reason))
    except Exception as exc:
        result.update(status="error", message=str(exc))
    return result, b""


def final_result(
    code: str, title: str, candidates: list[tuple[str, str]],
    attempt: dict[str, str], payload: bytes, output_dir: Path, attempt_count: int,
) -> dict[str, str]:
    path = save_payload(code, title, payload, attempt["content_type"], output_dir) if payload else None
    return {
        "code": code,
        "title": title,
        "source_url": candidates[0][1] if candidates else "",
        "final_url": attempt.get("final_url", ""),
        "status": attempt.get("status", "missing_url"),
        "access_kind": attempt.get("access_kind", ""),
        "content_type": attempt.get("content_type", ""),
        "local_path": str(path) if path else "",
        "message": attempt.get("message", "No candidate URL available."),
        "route": attempt.get("route", ""),
        "attempt_count": str(attempt_count),
    }


def recover_one(
    code: str, title: str, candidates: list[tuple[str, str]], output_dir: Path,
    opener: request.OpenerDirector, mailto: str | None, timeout: float,
    max_linked: int, request_delay: float,
) -> tuple[dict[str, str], list[dict[str, str]]]:
    queue = deque(candidates)
    seen: set[str] = set()
    attempts: list[dict[str, str]] = []
    best: tuple[dict[str, str], bytes] | None = None
    linked_added = 0
    priority = {"landing_metadata_only": 3, "blocked_or_error": 2, "binary": 1}
    while queue:
        route, url = queue.popleft()
        if url in seen:
            continue
        seen.add(url)
        if request_delay and attempts:
            time.sleep(request_delay)
        attempt, payload = attempt_url(code, route, url, opener, mailto, timeout)
        attempts.append(attempt)
        if attempt["access_kind"] in {"pdf_fulltext", "html_fulltext"}:
            return final_result(code, title, candidates, attempt, payload, output_dir, len(attempts)), attempts
        if payload and looks_like_html(payload, attempt["content_type"]) and linked_added < max_linked:
            for link in candidate_document_links(payload, attempt["final_url"] or url):
                if link not in seen and linked_added < max_linked:
                    queue.append((f"{route}:html_link", link))
                    linked_added += 1
        score = priority.get(attempt["access_kind"], 0)
        best_score = priority.get(best[0]["access_kind"], 0) if best else -1
        if payload and score > best_score:
            best = (attempt, payload)
    if best:
        return final_result(code, title, candidates, best[0], best[1], output_dir, len(attempts)), attempts
    last = attempts[-1] if attempts else {
        "status": "missing_url", "message": "No candidate URL available.", "route": "",
    }
    return final_result(code, title, candidates, last, b"", output_dir, len(attempts)), attempts


FINAL_FIELDS = [
    "code", "title", "source_url", "final_url", "status", "access_kind",
    "content_type", "local_path", "message", "route", "attempt_count",
]
ATTEMPT_FIELDS = [
    "code", "route", "url", "final_url", "status", "access_kind", "content_type", "message",
]


def write_csv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temporary, path)


def cached_fulltext_is_valid(row: dict[str, str]) -> bool:
    local_path = Path(row.get("local_path", ""))
    if not local_path.is_file():
        return False
    try:
        payload = local_path.read_bytes()
    except OSError:
        return False
    _, kind, _ = classify_payload(
        row.get("final_url", "") or local_path.as_uri(),
        row.get("content_type", ""),
        payload,
    )
    return kind in {"pdf_fulltext", "html_fulltext"}


def write_summary(
    path: Path, output_dir: Path,
    rows: list[dict[str, str]], attempts: list[dict[str, str]],
) -> None:
    status_counts = Counter(row["status"] for row in rows)
    kind_counts = Counter(row["access_kind"] for row in rows if row["access_kind"])
    route_counts = Counter(
        row["route"].split(":", 1)[0]
        for row in rows if row["access_kind"] in {"pdf_fulltext", "html_fulltext"}
    )
    fulltext = [row["code"] for row in rows if row["access_kind"] in {"pdf_fulltext", "html_fulltext"}]
    lines = [
        "# Resumen de recuperación de texto completo", "",
        f"- Directorio local: {output_dir}",
        f"- Registros evaluados: {len(rows)}",
        f"- Intentos por URL: {len(attempts)}",
        f"- Full text verificado por contenido: {len(fulltext)}",
        f"- Landing sin cuerpo completo: {kind_counts.get('landing_metadata_only', 0)}",
        f"- Bloqueados o challenge: {kind_counts.get('blocked_or_error', 0)}",
        "", "## Rutas que produjeron full text", "",
    ]
    for key in sorted(route_counts):
        lines.append(f"- {key}: {route_counts[key]}")
    lines.extend(["", "## Conteo por estado", ""])
    for key in sorted(status_counts):
        lines.append(f"- {key}: {status_counts[key]}")
    lines.extend(["", "## Conteo por tipo de acceso", ""])
    for key in sorted(kind_counts):
        lines.append(f"- {key}: {kind_counts[key]}")
    lines.extend(["", "## Identificadores con full text", "", ", ".join(fulltext) if fulltext else "ninguno", ""])
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
        if args.log else output_dir / "fulltext_download_log.csv"
    )
    attempt_log = (
        resolve_workspace_path(args.attempt_log, config_file, env_values)
        if args.attempt_log else output_dir / "fulltext_attempt_log.csv"
    )
    summary_path = (
        resolve_workspace_path(args.summary, config_file, env_values)
        if args.summary else output_dir / "fulltext_recovery_summary.md"
    )
    cookies = (
        resolve_workspace_path(args.cookies_file, config_file, env_values)
        if args.cookies_file else None
    )
    if not matrix_path.exists() or not decisions_path.exists():
        raise SystemExit("Matrix or decisions file not found.")
    if cookies and not cookies.exists():
        raise SystemExit(f"Cookies file not found: {cookies}")

    mailto = args.mailto or env_values.get("OPENALEX_MAILTO") or os.getenv("OPENALEX_MAILTO")
    opener = build_opener(mailto, cookies)
    sources, request_delay, max_linked, try_non_oa_direct = resolve_runtime_options(args, env_values)
    allowed = {
        value.strip() for value in (args.decision_filters or DEFAULT_DECISIONS) if value.strip()
    }
    progress_every = resolve_progress_every(args.progress_every, env_values)
    output_dir.mkdir(parents=True, exist_ok=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    attempt_log.parent.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    matrix = load_matrix_rows(matrix_path)
    targets = load_target_codes(decisions_path, allowed)

    previous: dict[str, dict[str, str]] = {}
    if args.resume and log_path.exists():
        with log_path.open(encoding="utf-8-sig", newline="") as handle:
            previous = {row["code"]: row for row in csv.DictReader(handle)}

    results: list[dict[str, str]] = []
    attempts: list[dict[str, str]] = []
    if args.resume and attempt_log.exists():
        with attempt_log.open(encoding="utf-8-sig", newline="") as handle:
            attempts = list(csv.DictReader(handle))
    for item in targets:
        code = item["code"].strip()
        cached = previous.get(code)
        if (
            cached
            and cached.get("access_kind") in {"pdf_fulltext", "html_fulltext"}
            and cached_fulltext_is_valid(cached)
        ):
            resumed = {key: cached.get(key, "") for key in FINAL_FIELDS}
            resumed["status"] = "resumed_verified_fulltext"
            results.append(resumed)
        else:
            row = matrix.get(code)
            if not row:
                result = {key: "" for key in FINAL_FIELDS}
                result.update(code=code, status="missing_matrix_row", message="Code not found in matrix.")
                results.append(result)
            else:
                candidates = initial_candidates(
                    row, sources, opener, mailto, args.timeout, try_non_oa_direct,
                )
                result, row_attempts = recover_one(
                    code=code,
                    title=row.get("Titulo", "").strip(),
                    candidates=candidates,
                    output_dir=output_dir,
                    opener=opener,
                    mailto=mailto,
                    timeout=args.timeout,
                    max_linked=max_linked,
                    request_delay=request_delay,
                )
                results.append(result)
                attempts.extend(row_attempts)
        # Persist a restart-safe checkpoint after every record. Successful
        # verified files are reused by --resume; failed records are retried.
        write_csv(log_path, results, FINAL_FIELDS)
        write_csv(attempt_log, attempts, ATTEMPT_FIELDS)
        if progress_every and len(results) % progress_every == 0:
            print(f"Processed {len(results)} / {len(targets)} recovery targets...", flush=True)

    write_csv(log_path, results, FINAL_FIELDS)
    write_csv(attempt_log, attempts, ATTEMPT_FIELDS)
    write_summary(summary_path, output_dir, results, attempts)
    run_dir = output_dir.parent if output_dir.name == "fulltext" else output_dir
    refresh_run_outputs(run_dir)
    verified = sum(row["access_kind"] in {"pdf_fulltext", "html_fulltext"} for row in results)
    print(f"Verified {verified} full texts.")
    print(f"Download log: {log_path}")
    print(f"Attempt log: {attempt_log}")
    print(f"Recovery summary: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
