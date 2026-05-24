#!/usr/bin/env python3
"""Search OpenAlex works and export normalized results for PRISMA-style workflows."""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib import error, parse, request

from metadata_config import (
    DEFAULT_METADATA_CONFIG_PATH,
    SCREENING_DECISION_COLUMNS,
    headers_for_columns,
    load_metadata_config,
    render_markdown_header,
)
from run_outputs import refresh_run_outputs


API_URL = "https://api.openalex.org/works"
DEFAULT_PER_PAGE = 50
MAX_PER_PAGE = 200
DEFAULT_LARGE_FETCH_THRESHOLD = 2000
DEFAULT_MAX_RETRIES = 4
DEFAULT_RETRY_DELAY = 2.0
DEFAULT_MAX_RETRY_WAIT = 60.0
DEFAULT_MAX_RESULTS_THRESHOLD = 500
COUNTRY_NAMES = {
    "AR": "Argentina",
    "AT": "Austria",
    "AU": "Australia",
    "BD": "Bangladesh",
    "BE": "Belgium",
    "BR": "Brazil",
    "CA": "Canada",
    "CH": "Switzerland",
    "CL": "Chile",
    "CN": "China",
    "CO": "Colombia",
    "CZ": "Czech Republic",
    "DE": "Germany",
    "DK": "Denmark",
    "EC": "Ecuador",
    "EG": "Egypt",
    "ES": "Spain",
    "FI": "Finland",
    "FR": "France",
    "GB": "United Kingdom",
    "GR": "Greece",
    "HK": "Hong Kong",
    "HU": "Hungary",
    "ID": "Indonesia",
    "IE": "Ireland",
    "IL": "Israel",
    "IN": "India",
    "IR": "Iran",
    "IT": "Italy",
    "JP": "Japan",
    "KR": "South Korea",
    "MX": "Mexico",
    "MY": "Malaysia",
    "NG": "Nigeria",
    "NL": "Netherlands",
    "NO": "Norway",
    "NZ": "New Zealand",
    "PE": "Peru",
    "PH": "Philippines",
    "PK": "Pakistan",
    "PL": "Poland",
    "PT": "Portugal",
    "RO": "Romania",
    "RU": "Russia",
    "SA": "Saudi Arabia",
    "SE": "Sweden",
    "SG": "Singapore",
    "SI": "Slovenia",
    "TH": "Thailand",
    "TR": "Turkey",
    "TW": "Taiwan",
    "UA": "Ukraine",
    "US": "United States",
    "UY": "Uruguay",
    "VN": "Vietnam",
    "ZA": "South Africa",
}
@dataclass
class SearchConfig:
    query: str
    search_mode: str
    no_stem: bool
    from_date: str | None
    to_date: str | None
    language: str | None
    work_type: str | None
    include_types: list[str]
    exclude_types: list[str]
    is_oa: bool | None
    source_in_doaj: bool | None
    per_page: int
    max_results: int
    fetch_all: bool
    allow_large_fetch: bool
    require_abstract: bool
    sampling_threshold: int
    quiet_progress: bool
    max_retries: int
    retry_delay: float
    max_retry_wait: float
    api_key: str | None
    mailto: str | None
    out_dir: Path
    query_output_name: str
    config_file: Path | None
    metadata_config_file: Path


def parse_args() -> SearchConfig:
    parser = argparse.ArgumentParser(
        description=(
            "Run an OpenAlex literature search and export normalized results "
            "for screening and traceability."
        )
    )
    parser.add_argument(
        "query",
        nargs="?",
        help="Text query for the search. Optional when --query-file is used.",
    )
    parser.add_argument(
        "--query-file",
        help="Path to a text file containing the search query.",
    )
    parser.add_argument(
        "--config-file",
        help=(
            "Path to an env-style configuration file. Supported keys: "
            "OPENALEX_API_KEY, OPENALEX_MAILTO, OPENALEX_QUERY_FILE, "
            "OPENALEX_SEARCH_MODE, OPENALEX_NO_STEM, OPENALEX_FROM_DATE, "
            "OPENALEX_TO_DATE, OPENALEX_LANGUAGE, OPENALEX_TYPE, "
            "OPENALEX_INCLUDE_TYPES, OPENALEX_EXCLUDE_TYPES, OPENALEX_IS_OA, "
            "OPENALEX_SOURCE_IN_DOAJ, OPENALEX_MAX_RESULTS, OPENALEX_PER_PAGE, "
            "OPENALEX_REQUIRE_ABSTRACT, PRISMA_MAX_RESULTS_THRESHOLD, "
            "OPENALEX_MAX_RETRIES, OPENALEX_RETRY_DELAY, OPENALEX_MAX_RETRY_WAIT, "
            "OPENALEX_OUT_DIR, OPENALEX_QUERY_OUTPUT_NAME, OPENALEX_METADATA_CONFIG."
        ),
    )
    parser.add_argument(
        "--api-key",
        help="OpenAlex API key. If omitted, the script checks config file and OPENALEX_API_KEY.",
    )
    parser.add_argument(
        "--api-key-file",
        help="Legacy option: path to a file containing only the OpenAlex API key.",
    )
    parser.add_argument(
        "--search-mode",
        choices=("search", "title_abstract"),
        default=None,
        help=(
            "Use OpenAlex general search or restrict the query to title and "
            "abstract. Default: title_abstract."
        ),
    )
    parser.add_argument(
        "--no-stem",
        action="store_true",
        help=(
            "Disable stemming and stop-word removal for title/abstract searches. "
            "Only applies to title_abstract mode."
        ),
    )
    parser.add_argument(
        "--from-date",
        help="Lower publication date bound in YYYY-MM-DD format.",
    )
    parser.add_argument(
        "--to-date",
        help="Upper publication date bound in YYYY-MM-DD format.",
    )
    parser.add_argument(
        "--language",
        help="ISO language code filter, for example en, es, pt.",
    )
    parser.add_argument(
        "--type",
        dest="work_type",
        help=(
            "OpenAlex work type filter, for example article, book-chapter, "
            "dataset, dissertation, preprint."
        ),
    )
    parser.add_argument(
        "--include-type",
        action="append",
        default=None,
        help=(
            "Include only this OpenAlex work type. Repeat the flag to allow "
            "multiple document types."
        ),
    )
    parser.add_argument(
        "--exclude-type",
        action="append",
        default=None,
        help=(
            "Exclude this OpenAlex work type. Repeat the flag to exclude "
            "multiple document types."
        ),
    )
    parser.add_argument(
        "--is-oa",
        choices=("true", "false"),
        help="Filter works by open access status.",
    )
    parser.add_argument(
        "--source-in-doaj",
        choices=("true", "false"),
        help="Filter works whose primary source is listed in DOAJ.",
    )
    parser.add_argument(
        "--require-abstract",
        action="store_true",
        help=(
            "Keep only works with abstract available. Default: true unless "
            "OPENALEX_REQUIRE_ABSTRACT=false in the config file."
        ),
    )
    parser.add_argument(
        "--per-page",
        type=int,
        default=None,
        help=(
            f"Results per API page. Default: {DEFAULT_PER_PAGE}. Max: {MAX_PER_PAGE}. "
            "Can also be set as OPENALEX_PER_PAGE in the config file."
        ),
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=None,
        help="Maximum number of results to export. Default: 100.",
    )
    parser.add_argument(
        "--sampling-threshold",
        type=int,
        default=None,
        help=(
            "Recommended upper bound for max_results before warning about latency. "
            f"Default: {DEFAULT_MAX_RESULTS_THRESHOLD}. Can also be set as "
            "PRISMA_MAX_RESULTS_THRESHOLD in the config file."
        ),
    )
    parser.add_argument(
        "--fetch-all",
        action="store_true",
        help=(
            "Fetch all available results from OpenAlex for the current query. "
            "Use with care because large result sets can take time and generate "
            "large output files."
        ),
    )
    parser.add_argument(
        "--allow-large-fetch",
        action="store_true",
        help=(
            "Allow --fetch-all to continue even when OpenAlex reports a very "
            f"large result set (more than {DEFAULT_LARGE_FETCH_THRESHOLD} results)."
        ),
    )
    parser.add_argument(
        "--quiet-progress",
        action="store_true",
        help="Hide per-page progress messages during download.",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=None,
        help=(
            f"Maximum retries for transient HTTP failures. Default: {DEFAULT_MAX_RETRIES}. "
            "Can also be set as OPENALEX_MAX_RETRIES in the config file."
        ),
    )
    parser.add_argument(
        "--retry-delay",
        type=float,
        default=None,
        help=(
            f"Initial retry delay in seconds for transient HTTP failures. Default: {DEFAULT_RETRY_DELAY}. "
            "Can also be set as OPENALEX_RETRY_DELAY in the config file."
        ),
    )
    parser.add_argument(
        "--max-retry-wait",
        type=float,
        default=None,
        help=(
            "Maximum time in seconds to honor a single Retry-After or backoff wait. "
            f"Default: {DEFAULT_MAX_RETRY_WAIT}. Can also be set as "
            "OPENALEX_MAX_RETRY_WAIT in the config file."
        ),
    )
    parser.add_argument(
        "--mailto",
        help=(
            "Contact email to identify your client to OpenAlex. Recommended "
            "by the provider for polite pool usage. If omitted, the script checks "
            "config file and OPENALEX_MAILTO."
        ),
    )
    parser.add_argument(
        "--out-dir",
        default=None,
        help="Directory for exported files. Default: outputs/openalex-search.",
    )
    parser.add_argument(
        "--query-output-name",
        default=None,
        help="Filename used to persist the effective query inside out-dir. Default: query.txt.",
    )
    parser.add_argument(
        "--metadata-config",
        default=None,
        help=(
            "Path to the YAML file that defines screening/extraction metadata columns. "
            f"Default: {DEFAULT_METADATA_CONFIG_PATH}."
        ),
    )

    args = parser.parse_args()

    config_file = Path(args.config_file).expanduser().resolve() if args.config_file else None
    env_config = load_env_config(config_file)
    query = resolve_query(args.query, args.query_file, env_config, config_file)
    api_key = resolve_api_key(args.api_key, args.api_key_file, env_config)
    mailto = resolve_mailto(args.mailto, env_config)

    per_page = min(max(resolve_int(args.per_page, env_config.get("OPENALEX_PER_PAGE"), DEFAULT_PER_PAGE), 1), MAX_PER_PAGE)
    max_results = max(resolve_int(args.max_results, env_config.get("OPENALEX_MAX_RESULTS"), 100), 1)
    max_retries = max(resolve_int(args.max_retries, env_config.get("OPENALEX_MAX_RETRIES"), DEFAULT_MAX_RETRIES), 0)
    retry_delay = max(resolve_float(args.retry_delay, env_config.get("OPENALEX_RETRY_DELAY"), DEFAULT_RETRY_DELAY), 0.1)
    max_retry_wait = max(resolve_float(args.max_retry_wait, env_config.get("OPENALEX_MAX_RETRY_WAIT"), DEFAULT_MAX_RETRY_WAIT), 0.1)
    search_mode = resolve_choice(
        args.search_mode,
        env_config.get("OPENALEX_SEARCH_MODE"),
        "title_abstract",
        {"search", "title_abstract"},
        "search mode",
    )
    no_stem = resolve_bool_flag(args.no_stem, env_config.get("OPENALEX_NO_STEM"), False)
    from_date = resolve_str(args.from_date, env_config.get("OPENALEX_FROM_DATE"))
    to_date = resolve_str(args.to_date, env_config.get("OPENALEX_TO_DATE"))
    language = resolve_str(args.language, env_config.get("OPENALEX_LANGUAGE"))
    work_type = resolve_str(args.work_type, env_config.get("OPENALEX_TYPE"))
    include_types = merge_type_list(args.include_type, env_config.get("OPENALEX_INCLUDE_TYPES"))
    exclude_types = merge_type_list(args.exclude_type, env_config.get("OPENALEX_EXCLUDE_TYPES"))
    is_oa = resolve_optional_bool(args.is_oa, env_config.get("OPENALEX_IS_OA"))
    source_in_doaj = resolve_optional_bool(
        args.source_in_doaj,
        env_config.get("OPENALEX_SOURCE_IN_DOAJ"),
    )
    require_abstract = resolve_bool_flag(
        args.require_abstract,
        env_config.get("OPENALEX_REQUIRE_ABSTRACT"),
        True,
    )
    sampling_threshold = max(
        resolve_int(
            args.sampling_threshold,
            env_config.get("PRISMA_MAX_RESULTS_THRESHOLD"),
            DEFAULT_MAX_RESULTS_THRESHOLD,
        ),
        1,
    )
    out_dir = resolve_workspace_path(
        resolve_str(args.out_dir, env_config.get("OPENALEX_OUT_DIR"), "outputs/openalex-search"),
        config_file,
        env_config,
    )
    query_output_name = resolve_str(args.query_output_name, env_config.get("OPENALEX_QUERY_OUTPUT_NAME"), "query.txt")
    metadata_config_raw = resolve_str(args.metadata_config, env_config.get("OPENALEX_METADATA_CONFIG"))
    metadata_config_file = (
        resolve_workspace_path(metadata_config_raw, config_file, env_config)
        if metadata_config_raw
        else DEFAULT_METADATA_CONFIG_PATH
    )

    return SearchConfig(
        query=query,
        search_mode=search_mode,
        no_stem=no_stem,
        from_date=from_date,
        to_date=to_date,
        language=language,
        work_type=work_type,
        include_types=include_types,
        exclude_types=exclude_types,
        is_oa=is_oa,
        source_in_doaj=source_in_doaj,
        per_page=per_page,
        max_results=max_results,
        fetch_all=args.fetch_all,
        allow_large_fetch=args.allow_large_fetch,
        require_abstract=require_abstract,
        sampling_threshold=sampling_threshold,
        quiet_progress=args.quiet_progress,
        max_retries=max_retries,
        retry_delay=retry_delay,
        max_retry_wait=max_retry_wait,
        api_key=api_key,
        mailto=mailto,
        out_dir=out_dir,
        query_output_name=query_output_name,
        config_file=config_file,
        metadata_config_file=metadata_config_file,
    )


def resolve_query(
    cli_query: str | None,
    query_file: str | None,
    env_config: dict[str, str],
    config_file: Path | None,
) -> str:
    config_query_file = env_config.get("OPENALEX_QUERY_FILE", "").strip() or None
    effective_query_file = query_file or config_query_file

    if cli_query and query_file:
        raise ValueError("Use either a positional query or --query-file, not both.")
    if cli_query and config_query_file:
        raise ValueError(
            "Use either a positional query or OPENALEX_QUERY_FILE/--query-file, not both."
        )
    if effective_query_file:
        query_path = (
            Path(effective_query_file).expanduser().resolve()
            if query_file
            else resolve_workspace_path(effective_query_file, config_file, env_config)
        )
        return query_path.read_text(encoding="utf-8").strip()
    if cli_query:
        return cli_query.strip()
    raise ValueError(
        "A query is required. Provide it directly or with --query-file/OPENALEX_QUERY_FILE."
    )


BASE_CONFIG_KEY = "PRISMA_AI_TUTOR_BASE_CONFIG"
WORKSPACE_ROOT_KEY = "PRISMA_AI_TUTOR_WORKSPACE_ROOT"


def load_env_config(path: Path | None) -> dict[str, str]:
    return _load_env_config(path, seen=set())


def _load_env_config(path: Path | None, seen: set[Path]) -> dict[str, str]:
    if path is None:
        return {}

    resolved_path = path.resolve()
    if resolved_path in seen:
        raise ValueError(f"Recursive env inheritance detected: {resolved_path}")
    seen.add(resolved_path)

    current = _parse_env_file(resolved_path)
    base_config_raw = current.get(BASE_CONFIG_KEY, "").strip()
    if not base_config_raw:
        return current

    base_path = Path(base_config_raw)
    if not base_path.is_absolute():
        base_path = resolved_path.parent / base_path
    base_config = _load_env_config(base_path, seen=seen)
    merged = dict(base_config)
    merged.update(current)
    return merged


def _parse_env_file(path: Path) -> dict[str, str]:
    config: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        config[key.strip()] = value.strip().strip('"').strip("'")
    return config


def resolve_workspace_root(path: Path | None, env_config: dict[str, str] | None = None) -> Path:
    raw = (env_config or {}).get(WORKSPACE_ROOT_KEY, "").strip()
    if raw:
        root = Path(raw).expanduser()
        if not root.is_absolute():
            anchor = path.parent if path is not None else Path.cwd()
            root = anchor / root
        return root.resolve()
    return Path.cwd().resolve()


def resolve_workspace_path(
    value: str | Path,
    config_file: Path | None,
    env_config: dict[str, str] | None = None,
) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (resolve_workspace_root(config_file, env_config) / path).resolve()


def resolve_api_key(cli_key: str | None, key_file: str | None, env_config: dict[str, str]) -> str | None:
    if cli_key and key_file:
        raise ValueError("Use either --api-key or --api-key-file, not both.")
    if key_file:
        return Path(key_file).read_text(encoding="utf-8").strip()
    if cli_key:
        return cli_key.strip()
    config_value = env_config.get("OPENALEX_API_KEY", "").strip()
    if config_value:
        return config_value
    env_value = os.getenv("OPENALEX_API_KEY", "").strip()
    return env_value or None


def resolve_mailto(cli_value: str | None, env_config: dict[str, str]) -> str | None:
    if cli_value:
        return cli_value.strip()
    config_value = env_config.get("OPENALEX_MAILTO", "").strip()
    if config_value:
        return config_value
    env_value = os.getenv("OPENALEX_MAILTO", "").strip()
    return env_value or None


def resolve_int(cli_value: int | None, config_value: str | None, default: int) -> int:
    if cli_value is not None:
        return cli_value
    if config_value:
        return int(config_value)
    return default


def resolve_float(cli_value: float | None, config_value: str | None, default: float) -> float:
    if cli_value is not None:
        return cli_value
    if config_value:
        return float(config_value)
    return default


def resolve_str(cli_value: str | None, config_value: str | None, default: str | None = None) -> str | None:
    if cli_value is not None:
        return cli_value.strip()
    if config_value:
        return config_value.strip()
    return default


def resolve_choice(
    cli_value: str | None,
    config_value: str | None,
    default: str,
    allowed: set[str],
    label: str,
) -> str:
    value = resolve_str(cli_value, config_value, default)
    if value not in allowed:
        choices = ", ".join(sorted(allowed))
        raise ValueError(f"Invalid {label}: {value!r}. Expected one of: {choices}.")
    return value


def parse_bool_string(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"true", "1", "yes", "y", "on"}:
        return True
    if normalized in {"false", "0", "no", "n", "off"}:
        return False
    raise ValueError(f"Invalid boolean value: {value!r}. Use true or false.")


def resolve_bool_flag(cli_flag: bool, config_value: str | None, default: bool) -> bool:
    if cli_flag:
        return True
    if config_value:
        return parse_bool_string(config_value)
    return default


def resolve_optional_bool(cli_value: str | None, config_value: str | None) -> bool | None:
    if cli_value is not None:
        return coerce_bool(cli_value)
    if config_value:
        return parse_bool_string(config_value)
    return None


def coerce_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    return value.lower() == "true"


def normalize_type_list(values: list[str]) -> list[str]:
    normalized: list[str] = []
    for value in values:
        item = value.strip()
        if item and item not in normalized:
            normalized.append(item)
    return normalized


def split_csv_list(raw_value: str | None) -> list[str]:
    if not raw_value:
        return []
    return [item.strip() for item in raw_value.split(",") if item.strip()]


def merge_type_list(cli_values: list[str] | None, config_value: str | None) -> list[str]:
    if cli_values is not None:
        return normalize_type_list(cli_values)
    return normalize_type_list(split_csv_list(config_value))


def validate_date(value: str | None) -> None:
    if value is None:
        return
    date.fromisoformat(value)


def build_params(config: SearchConfig, cursor: str) -> dict[str, str]:
    filters: list[str] = []

    if config.search_mode == "title_abstract":
        field = "title_and_abstract.search.no_stem" if config.no_stem else "title_and_abstract.search"
        filters.append(f"{field}:{config.query}")
    else:
        filters.append(f"default.search:{config.query}")

    if config.from_date:
        filters.append(f"from_publication_date:{config.from_date}")
    if config.to_date:
        filters.append(f"to_publication_date:{config.to_date}")
    if config.language:
        filters.append(f"language:{config.language}")
    if config.work_type:
        filters.append(f"type:{config.work_type}")
    elif config.include_types:
        filters.append(f"type:{'|'.join(config.include_types)}")
    if config.exclude_types:
        filters.append(f"type:!{'|'.join(config.exclude_types)}")
    if config.is_oa is not None:
        filters.append(f"open_access.is_oa:{str(config.is_oa).lower()}")
    if config.source_in_doaj is not None:
        filters.append(
            f"primary_location.source.is_in_doaj:{str(config.source_in_doaj).lower()}"
        )

    params = {
        "filter": ",".join(filters),
        "per-page": str(config.per_page),
        "cursor": cursor,
        "sort": "relevance_score:desc",
    }

    if config.mailto:
        params["mailto"] = config.mailto
    if config.api_key:
        params["api_key"] = config.api_key

    return params


def fetch_results(config: SearchConfig) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    results: list[dict[str, Any]] = []
    cursor = "*"
    meta: dict[str, Any] | None = None
    page_number = 0

    while config.fetch_all or len(results) < config.max_results:
        url = f"{API_URL}?{parse.urlencode(build_params(config, cursor))}"
        payload = fetch_json_with_retries(url, config)

        page_number += 1

        if meta is None:
            meta = payload.get("meta", {})
            enforce_large_fetch_policy(config, meta)

        page_results = payload.get("results", [])
        if not page_results:
            break

        if config.fetch_all:
            results.extend(page_results)
        else:
            remaining = config.max_results - len(results)
            results.extend(page_results[:remaining])

        if not config.quiet_progress:
            total_hint = meta.get("count", "unknown")
            print(
                f"[OpenAlex] page {page_number} fetched, accumulated {len(results)} "
                f"records (OpenAlex reports about {total_hint}).",
                flush=True,
            )

        next_cursor = payload.get("meta", {}).get("next_cursor")
        if not next_cursor or len(page_results) < config.per_page:
            break
        cursor = next_cursor

    return results, meta or {}


def fetch_json_with_retries(url: str, config: SearchConfig) -> dict[str, Any]:
    attempt = 0
    delay = config.retry_delay

    while True:
        try:
            with request.urlopen(url) as response:
                return json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt >= config.max_retries:
                raise

            retry_after = exc.headers.get("Retry-After")
            sleep_seconds = parse_retry_after(retry_after) if retry_after else delay
            if sleep_seconds is None:
                sleep_seconds = delay
            if sleep_seconds > config.max_retry_wait:
                raise RuntimeError(
                    "OpenAlex requested a retry wait of "
                    f"{sleep_seconds:.1f}s, which exceeds the configured maximum of "
                    f"{config.max_retry_wait:.1f}s. Try again later, reduce request volume, "
                    "or check whether your IP or API usage has hit a temporary limit. "
                    "Using an OpenAlex API key may help if you are currently unauthenticated."
                ) from exc

            print(
                f"[OpenAlex] transient HTTP {exc.code}; retrying in {sleep_seconds:.1f}s "
                f"(attempt {attempt + 1} of {config.max_retries}).",
                flush=True,
            )
            time.sleep(sleep_seconds)
            attempt += 1
            delay *= 2
        except error.URLError:
            if attempt >= config.max_retries:
                raise
            print(
                f"[OpenAlex] transient network error; retrying in {delay:.1f}s "
                f"(attempt {attempt + 1} of {config.max_retries}).",
                flush=True,
            )
            time.sleep(delay)
            attempt += 1
            delay *= 2


def parse_retry_after(value: str) -> float | None:
    try:
        return max(float(value), 0.1)
    except ValueError:
        return None


def enforce_large_fetch_policy(config: SearchConfig, meta: dict[str, Any]) -> None:
    if not config.fetch_all:
        return

    count = meta.get("count")
    if not isinstance(count, int):
        return

    if count > DEFAULT_LARGE_FETCH_THRESHOLD and not config.allow_large_fetch:
        raise RuntimeError(
            "OpenAlex reports a large result set "
            f"({count} results). Re-run with --allow-large-fetch to continue "
            "or use --max-results N for a capped download."
        )


def invert_abstract(index: dict[str, list[int]] | None) -> str:
    if not index:
        return ""

    length = max(position for positions in index.values() for position in positions) + 1
    words = [""] * length
    for token, positions in index.items():
        for position in positions:
            words[position] = token
    return " ".join(words).strip()


def normalize_work(work: dict[str, Any], position: int) -> dict[str, Any]:
    primary_location = work.get("primary_location") or {}
    best_oa_location = work.get("best_oa_location") or {}
    source = primary_location.get("source") or {}
    authorships = work.get("authorships") or []
    authors = [
        (authorship.get("author") or {}).get("display_name", "")
        for authorship in authorships
        if (authorship.get("author") or {}).get("display_name")
    ]
    first_institution = ""
    first_country_code = ""
    for authorship in authorships:
        institutions = authorship.get("institutions") or []
        if not institutions:
            continue
        institution = institutions[0] or {}
        first_institution = institution.get("display_name", "") or first_institution
        first_country_code = institution.get("country_code", "") or first_country_code
        if first_institution or first_country_code:
            break
    doi = work.get("doi") or ""
    doi = doi.replace("https://doi.org/", "")
    access_url = (
        best_oa_location.get("pdf_url")
        or best_oa_location.get("landing_page_url")
        or primary_location.get("pdf_url")
        or primary_location.get("landing_page_url")
        or ""
    )

    normalized = {
        "code": f"E{position:03d}",
        "source": "OpenAlex",
        "source_id": work.get("id", ""),
        "title": work.get("display_name", ""),
        "authors": "; ".join(authors),
        "year": work.get("publication_year", ""),
        "first_affiliation": first_institution,
        "country_code": first_country_code,
        "country": country_name(first_country_code),
        "publication_date": work.get("publication_date", ""),
        "doi": doi,
        "abstract": invert_abstract(work.get("abstract_inverted_index")),
        "journal": source.get("display_name", ""),
        "journal_type": source.get("type", ""),
        "language": work.get("language", ""),
        "document_type": work.get("type", ""),
        "is_oa": (work.get("open_access") or {}).get("is_oa"),
        "oa_status": (work.get("open_access") or {}).get("oa_status", ""),
        "source_is_in_doaj": source.get("is_in_doaj"),
        "cited_by_count": work.get("cited_by_count", 0),
        "primary_url": access_url,
        "pdf_url": best_oa_location.get("pdf_url") or primary_location.get("pdf_url") or "",
        "openalex_url": work.get("id", ""),
        "fulltext_accessible": "Por verificar" if access_url else "No",
    }
    return normalized


def filter_raw_results(raw_results: list[dict[str, Any]], config: SearchConfig) -> list[dict[str, Any]]:
    filtered = raw_results
    if config.require_abstract:
        filtered = [work for work in filtered if work.get("abstract_inverted_index")]
    return filtered


def post_api_filter_descriptions(config: SearchConfig) -> list[str]:
    descriptions: list[str] = []
    if config.require_abstract:
        descriptions.append(
            "Se excluyen localmente los registros sin `abstract_inverted_index` porque el caso exige `require_abstract=true`."
        )
    return descriptions


def country_name(country_code: str) -> str:
    if not country_code:
        return ""
    return COUNTRY_NAMES.get(country_code.upper(), country_code.upper())


def compute_quality_snapshot(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    with_doi = sum(1 for row in rows if row.get("doi"))
    with_abstract = sum(
        1
        for row in rows
        if row.get("abstract") or row.get("abstract_available") is True
    )
    with_journal = sum(1 for row in rows if row.get("journal"))
    articles = sum(1 for row in rows if row.get("document_type") == "article")
    oa_items = sum(1 for row in rows if row.get("is_oa") is True)
    doaj_items = sum(1 for row in rows if row.get("source_is_in_doaj") is True)
    languages: dict[str, int] = {}
    work_types: dict[str, int] = {}

    for row in rows:
        language = row.get("language") or "unknown"
        work_type = row.get("document_type") or "unknown"
        languages[language] = languages.get(language, 0) + 1
        work_types[work_type] = work_types.get(work_type, 0) + 1

    return {
        "total_results": total,
        "with_doi": with_doi,
        "with_abstract": with_abstract,
        "with_journal": with_journal,
        "articles": articles,
        "open_access_items": oa_items,
        "source_in_doaj_items": doaj_items,
        "languages": sort_counts_desc(languages),
        "work_types": sort_counts_desc(work_types),
    }


def sort_counts_desc(counts: dict[str, int]) -> dict[str, int]:
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")


def write_query_file(path: Path, query: str) -> None:
    path.write_text(query.strip() + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_screening_matrix(
    path: Path, rows: list[dict[str, Any]], screening_column_keys: list[str]
) -> None:
    headers, data_rows = build_screening_matrix_table(rows, screening_column_keys)
    lines = [
        "# Matriz de cribado (seleccion de estudios)",
        "",
        *render_markdown_header(headers),
    ]

    for row in data_rows:
        values = [escape_pipe(row[header]) for header in headers]
        lines.append("| " + " | ".join(values) + " |")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_screening_matrix_csv(
    path: Path, rows: list[dict[str, Any]], screening_column_keys: list[str]
) -> None:
    headers, data_rows = build_screening_matrix_table(rows, screening_column_keys)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerows(data_rows)


def build_screening_matrix_table(
    rows: list[dict[str, Any]], screening_column_keys: list[str]
) -> tuple[list[str], list[dict[str, str]]]:
    headers = headers_for_columns(screening_column_keys) + SCREENING_DECISION_COLUMNS
    data_rows: list[dict[str, str]] = []
    for row in rows:
        values = [screening_value(key, row) for key in screening_column_keys]
        values.extend(
            [
                "Incluir/Excluir/Dudoso",
                "",
                "",
                "Si/No",
                "Texto completo/Sin texto completo accesible",
                "",
            ]
        )
        data_rows.append(dict(zip(headers, values, strict=True)))
    return headers, data_rows


def screening_value(key: str, row: dict[str, Any]) -> str:
    if key == "code":
        return row["code"]
    if key == "title":
        return row["title"]
    if key == "author_year":
        return build_author_year(row["authors"], row["year"])
    if key == "first_affiliation":
        return row.get("first_affiliation", "")
    if key == "country":
        return row.get("country", "")
    if key == "language":
        return row.get("language", "")
    if key == "source":
        return row.get("source", "")
    if key == "document_type":
        return row.get("document_type", "")
    if key == "doi":
        return row.get("doi", "") or ""
    if key == "open_access":
        return "Si" if row.get("is_oa") is True else "No"
    if key == "fulltext_accessible":
        return row.get("fulltext_accessible", "No")
    if key == "url_doi":
        doi_value = row.get("doi", "") or ""
        return f"https://doi.org/{doi_value}" if doi_value else ""
    if key == "url_access":
        return row.get("primary_url", "")
    if key == "url_openalex":
        return row.get("openalex_url", "")
    if key == "abstract_available":
        if row.get("abstract") or row.get("abstract_available") is True:
            return "Si"
        return "No"
    raise KeyError(f"Unsupported screening column key: {key}")


def build_search_log_text(
    config: SearchConfig,
    meta: dict[str, Any],
    result_count: int,
    snapshot: dict[str, Any],
    metadata_columns: dict[str, list[str]],
    warnings: list[str],
    filtered_out_count: int,
) -> str:
    run_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    filters = {
        "search_mode": config.search_mode,
        "no_stem": config.no_stem,
        "from_date": config.from_date,
        "to_date": config.to_date,
        "language": config.language,
        "work_type": config.work_type,
        "include_types": config.include_types,
        "exclude_types": config.exclude_types,
        "is_oa": config.is_oa,
        "source_in_doaj": config.source_in_doaj,
        "require_abstract": config.require_abstract,
        "sampling_threshold": config.sampling_threshold,
        "max_retries": config.max_retries,
        "retry_delay": config.retry_delay,
        "max_retry_wait": config.max_retry_wait,
        "api_key_used": bool(config.api_key),
        "config_file": str(config.config_file) if config.config_file else None,
        "metadata_config_file": str(config.metadata_config_file),
        "screening_columns": metadata_columns.get("screening_columns", []),
    }
    export_mode = "all_results" if config.fetch_all else f"max_results={config.max_results}"
    local_post_filters = post_api_filter_descriptions(config)
    fetched_before_post_filters = meta.get("count") if config.fetch_all else result_count + filtered_out_count

    lines = [
        "# Bitacora de busqueda OpenAlex",
        "",
        f"- Fecha de ejecucion: `{run_at}`",
        f"- Fuente: `OpenAlex`",
        f"- Consulta: `{config.query}`",
        f"- Modo de busqueda: `{config.search_mode}`",
        f"- Modo de exportacion: `{export_mode}`",
        f"- Resultados por pagina: `{config.per_page}`",
        f"- Permitir recuperacion grande: `{config.allow_large_fetch}`",
        f"- Requerir abstract: `{config.require_abstract}`",
        f"- Umbral operativo de muestra: `{config.sampling_threshold}`",
        f"- Filtros: `{json.dumps(filters, ensure_ascii=True)}`",
        f"- Resultados estimados por OpenAlex: `{meta.get('count', 'No reportado')}`",
        f"- Registros recuperados por esta ejecucion antes de filtros locales: `{fetched_before_post_filters}`",
        f"- Registros excluidos por reglas locales posteriores a la API: `{filtered_out_count}`",
        f"- Resultados exportados en esta ejecucion: `{result_count}`",
        "",
        "## Trazabilidad del filtrado local",
        "",
        "",
        "## Alertas de muestreo y volumen",
        "",
        render_warning_lines(warnings),
        "",
        "## Resumen rapido de calidad del conjunto",
        "",
        f"- Registros con DOI: `{snapshot['with_doi']}` de `{snapshot['total_results']}`",
        f"- Registros con abstract: `{snapshot['with_abstract']}` de `{snapshot['total_results']}`",
        f"- Registros con revista o fuente identificada: `{snapshot['with_journal']}` de `{snapshot['total_results']}`",
        f"- Registros tipo article: `{snapshot['articles']}` de `{snapshot['total_results']}`",
        f"- Registros open access: `{snapshot['open_access_items']}` de `{snapshot['total_results']}`",
        f"- Registros con fuente en DOAJ: `{snapshot['source_in_doaj_items']}` de `{snapshot['total_results']}`",
        "",
        "### Idiomas detectados",
        "",
        render_count_lines(snapshot["languages"]),
        "",
        "### Tipos documentales detectados",
        "",
        render_count_lines(snapshot["work_types"]),
        "",
        "## Nota metodologica",
        "",
        "Esta bitacora documenta una recuperacion automatizada inicial. La inclusion final de estudios",
        "debe realizarse mediante cribado humano con criterios explicitos.",
        "Si OpenAlex reporta mas resultados que `max_results`, el recorte se interpreta como una",
        "muestra operativa priorizada por OpenAlex, no como una seleccion metodologica final.",
        "",
    ]
    insert_at = lines.index("## Alertas de muestreo y volumen") - 1
    if local_post_filters:
        lines[insert_at:insert_at] = [f"- {item}" for item in local_post_filters]
    else:
        lines[insert_at:insert_at] = ["- `No se aplicaron filtros locales posteriores a la API.`"]
    return "\n".join(lines)


def write_search_log(
    path: Path,
    config: SearchConfig,
    meta: dict[str, Any],
    result_count: int,
    snapshot: dict[str, Any],
    metadata_columns: dict[str, list[str]],
    warnings: list[str],
    filtered_out_count: int,
) -> str:
    text = build_search_log_text(
        config,
        meta,
        result_count,
        snapshot,
        metadata_columns,
        warnings,
        filtered_out_count,
    )
    path.write_text(text, encoding="utf-8")
    return text


def render_count_lines(counts: dict[str, int]) -> str:
    if not counts:
        return "- No reportado"
    return "\n".join(f"- `{key}`: `{value}`" for key, value in counts.items())


def render_warning_lines(warnings: list[str]) -> str:
    if not warnings:
        return "- Sin alertas."
    return "\n".join(f"- {warning}" for warning in warnings)


def compute_sampling_warnings(config: SearchConfig, meta: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    if config.max_results > config.sampling_threshold:
        warnings.append(
            "max_results supera el umbral operativo configurado y puede introducir "
            "latencia o un subconjunto demasiado grande para cribado inicial."
        )

    count = meta.get("count")
    if not isinstance(count, int):
        return warnings

    if count > 1000:
        warnings.append(
            "OpenAlex reporta más de 1000 resultados estimados. Corresponde refinar "
            "la query antes del cribado inicial."
        )
    elif count > config.max_results:
        warnings.append(
            "OpenAlex reporta más resultados que max_results. Si el usuario no aprueba "
            "trabajar con una muestra acotada, corresponde refinar la query."
        )

    return warnings


def build_author_year(authors: str, year: Any) -> str:
    if not authors and not year:
        return ""
    first_author = authors.split(";")[0].strip() if authors else ""
    if first_author and year:
        return f"{first_author} / {year}"
    return str(first_author or year)


def escape_pipe(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ").strip()


def search_output_dir(run_dir: Path) -> Path:
    return run_dir / "search" / "openalex"


def screening_output_dir(run_dir: Path) -> Path:
    return run_dir / "screening"


def main() -> int:
    try:
        config = parse_args()
        validate_date(config.from_date)
        validate_date(config.to_date)
    except ValueError as exc:
        print(f"Invalid date: {exc}", file=sys.stderr)
        return 2

    ensure_dir(config.out_dir)
    search_dir = search_output_dir(config.out_dir)
    screening_dir = screening_output_dir(config.out_dir)
    ensure_dir(search_dir)
    ensure_dir(screening_dir)
    write_query_file(search_dir / config.query_output_name, config.query)
    try:
        metadata_columns = load_metadata_config(config.metadata_config_file)
    except Exception as exc:  # noqa: BLE001
        print(f"Metadata config failed: {exc}", file=sys.stderr)
        return 2

    try:
        raw_results, meta = fetch_results(config)
    except Exception as exc:  # noqa: BLE001
        print(f"OpenAlex request failed: {exc}", file=sys.stderr)
        return 1

    filtered_raw_results = filter_raw_results(raw_results, config)
    filtered_out_count = len(raw_results) - len(filtered_raw_results)
    normalized = [
        normalize_work(work, position=index + 1)
        for index, work in enumerate(filtered_raw_results)
    ]
    snapshot = compute_quality_snapshot(normalized)
    sampling_warnings = compute_sampling_warnings(config, meta)

    summary = {
        "source": "OpenAlex",
        "query": config.query,
        "config_file": str(config.config_file) if config.config_file else None,
        "search_mode": config.search_mode,
        "fetch_all": config.fetch_all,
        "max_results": config.max_results,
        "sampling_threshold": config.sampling_threshold,
        "require_abstract": config.require_abstract,
        "fetched_results_before_post_filters": len(raw_results),
        "exported_results": len(normalized),
        "filtered_out_after_fetch": filtered_out_count,
        "openalex_meta_count": meta.get("count"),
        "sampling_warnings": sampling_warnings,
        "snapshot": snapshot,
        "metadata_config_file": str(config.metadata_config_file),
        "screening_columns": metadata_columns.get("screening_columns", []),
        "extraction_columns": metadata_columns.get("extraction_columns", []),
    }

    write_json(search_dir / "raw_results.json", filtered_raw_results)
    write_json(search_dir / "normalized_results.json", normalized)
    write_json(search_dir / "summary.json", summary)
    write_csv(search_dir / "normalized_results.csv", normalized)
    write_screening_matrix(
        screening_dir / "screening_matrix.md",
        normalized,
        metadata_columns.get("screening_columns", []),
    )
    write_screening_matrix_csv(
        screening_dir / "screening_matrix.csv",
        normalized,
        metadata_columns.get("screening_columns", []),
    )
    search_log_text = write_search_log(
        search_dir / "search_log.md",
        config,
        meta,
        len(normalized),
        snapshot,
        metadata_columns,
        sampling_warnings,
        filtered_out_count,
    )

    print(search_log_text)
    refresh_run_outputs(config.out_dir)
    print(f"Archivos exportados en: {config.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
