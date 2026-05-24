#!/usr/bin/env python3
"""Run PRISMA phase 3 sequentially across multiple sources and merge results."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from openalex_search import load_env_config, resolve_bool_flag, resolve_str, resolve_workspace_path


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_SOURCE_ORDER = ["openalex", "doaj", "redalyc"]
SOURCE_TO_SCRIPT = {
    "openalex": SCRIPT_DIR / "openalex_search.py",
    "doaj": SCRIPT_DIR / "doaj_search.py",
    "redalyc": SCRIPT_DIR / "redalyc_search.py",
}
SOURCE_OUT_DIR_KEYS = {
    "openalex": ("OPENALEX_OUT_DIR", "outputs/openalex-search"),
    "doaj": ("DOAJ_OUT_DIR", "outputs/doaj-search"),
    "redalyc": ("REDALYC_OUT_DIR", "outputs/redalyc-search"),
}
PHASE3_SOURCES_KEY = "PRISMA_PHASE3_SOURCES"
PHASE3_MERGE_KEY = "PRISMA_PHASE3_AUTO_MERGE"


@dataclass
class Phase3Config:
    config_file: Path | None
    sources: list[str]
    merge_after_search: bool
    run_dir: Path


def parse_args() -> Phase3Config:
    parser = argparse.ArgumentParser(
        description=(
            "Execute phase 3 sequentially for multiple PRISMA sources and, "
            "when applicable, merge the normalized results into one screening set."
        )
    )
    parser.add_argument(
        "--config-file",
        help="Path to the case .env file used by the individual source scripts.",
    )
    parser.add_argument(
        "--source",
        action="append",
        dest="sources",
        help=(
            "Source to execute in phase 3. Repeat to keep a specific order. "
            "Supported: openalex, doaj, redalyc."
        ),
    )
    parser.add_argument(
        "--merge",
        dest="merge_after_search",
        action="store_true",
        help="Force the post-search merge step when more than one source is executed.",
    )
    parser.add_argument(
        "--no-merge",
        dest="merge_after_search",
        action="store_false",
        help="Skip the post-search merge step even when several sources are executed.",
    )
    parser.set_defaults(merge_after_search=None)

    args = parser.parse_args()
    config_file = Path(args.config_file).expanduser().resolve() if args.config_file else None
    env_config = load_env_config(config_file)

    source_values = args.sources or parse_sources_env(env_config.get(PHASE3_SOURCES_KEY, ""))
    sources = normalize_sources(source_values or DEFAULT_SOURCE_ORDER)
    invalid = [source for source in sources if source not in SOURCE_TO_SCRIPT]
    if invalid:
        raise ValueError(
            f"Unsupported phase 3 sources: {', '.join(invalid)}. "
            f"Expected only: {', '.join(DEFAULT_SOURCE_ORDER)}."
        )

    merge_after_search = resolve_bool_flag(
        args.merge_after_search,
        env_config.get(PHASE3_MERGE_KEY),
        True,
    )
    run_dir = resolve_common_run_dir(sources, env_config, config_file)
    return Phase3Config(
        config_file=config_file,
        sources=sources,
        merge_after_search=merge_after_search,
        run_dir=run_dir,
    )


def parse_sources_env(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def normalize_sources(values: list[str]) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for source in values:
        item = source.strip().lower()
        if not item or item in seen:
            continue
        seen.add(item)
        normalized.append(item)
    return normalized


def resolve_source_run_dir(source: str, env_config: dict[str, str], config_file: Path | None) -> Path:
    key, default = SOURCE_OUT_DIR_KEYS[source]
    out_dir_raw = resolve_str(None, env_config.get(key), default)
    return resolve_workspace_path(out_dir_raw, config_file, env_config)


def resolve_common_run_dir(sources: list[str], env_config: dict[str, str], config_file: Path | None) -> Path:
    run_dirs = {source: resolve_source_run_dir(source, env_config, config_file) for source in sources}
    unique = {path.resolve() for path in run_dirs.values()}
    if len(unique) != 1:
        lines = [
            "Phase 3 multi-source requires every active source to write into the same run directory.",
            "Align the following *_OUT_DIR values before rerunning:",
        ]
        for source, path in run_dirs.items():
            lines.append(f"- {source}: {path}")
        raise ValueError("\n".join(lines))
    return next(iter(unique))


def run_source_script(source: str, config: Phase3Config) -> dict[str, str]:
    script = SOURCE_TO_SCRIPT[source]
    command = [sys.executable, str(script)]
    if config.config_file:
        command.extend(["--config-file", str(config.config_file)])
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or f"{source} search failed."
        raise RuntimeError(f"{source}: {message}")
    return {
        "source": source,
        "script": str(script),
        "status": "completed",
        "stdout": result.stdout.strip(),
    }


def run_merge(config: Phase3Config) -> dict[str, str]:
    command = [
        sys.executable,
        str(SCRIPT_DIR / "merge_search_results.py"),
        "--run-dir",
        str(config.run_dir),
    ]
    if config.config_file:
        command.extend(["--config-file", str(config.config_file)])
    for source in config.sources:
        command.extend(["--source", source])
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or "merge failed."
        raise RuntimeError(f"merge: {message}")
    return {
        "source": "merge",
        "script": str(SCRIPT_DIR / "merge_search_results.py"),
        "status": "completed",
        "stdout": result.stdout.strip(),
    }


def write_phase3_summary(run_dir: Path, config: Phase3Config, steps: list[dict[str, str]]) -> None:
    search_dir = run_dir / "search"
    search_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "phase": 3,
        "sources": config.sources,
        "merge_after_search": config.merge_after_search,
        "run_dir": str(config.run_dir),
        "config_file": str(config.config_file) if config.config_file else None,
        "steps": steps,
    }
    (search_dir / "phase3_multisource_summary.json").write_text(
        json.dumps(summary, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )
    lines = [
        "# Resumen de Fase 3 multi-fuente",
        "",
        f"- Corrida: `{config.run_dir}`",
        f"- Fuentes ejecutadas en orden: `{', '.join(config.sources)}`",
        f"- Fusion posterior: `{'si' if config.merge_after_search and len(config.sources) > 1 else 'no'}`",
        "",
        "## Pasos ejecutados",
        "",
    ]
    for step in steps:
        lines.append(f"- `{step['source']}`: `{step['status']}`")
    lines.append("")
    (search_dir / "phase3_multisource_log.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    try:
        config = parse_args()
    except Exception as exc:  # noqa: BLE001
        print(f"Phase 3 multi-source configuration failed: {exc}", file=sys.stderr)
        return 2

    steps: list[dict[str, str]] = []
    try:
        for source in config.sources:
            steps.append(run_source_script(source, config))
        if config.merge_after_search and len(config.sources) > 1:
            steps.append(run_merge(config))
        write_phase3_summary(config.run_dir, config, steps)
    except Exception as exc:  # noqa: BLE001
        write_phase3_summary(config.run_dir, config, steps)
        print(f"Phase 3 multi-source execution failed: {exc}", file=sys.stderr)
        return 1

    print(f"Fase 3 multi-fuente completada en: {config.run_dir}")
    print(json.dumps({"sources": config.sources, "merge_after_search": config.merge_after_search}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
