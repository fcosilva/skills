#!/usr/bin/env python3
"""Synchronize confirmed screening results to Zotero through zotero-mcp."""

from __future__ import annotations

import argparse
import csv
import fcntl
import hashlib
import json
import os
import tempfile
from contextlib import contextmanager
from urllib.error import HTTPError
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from openalex_search import load_env_config, resolve_workspace_path
from prepare_zotero_import import prepare_import, ZoteroConfig, resolve_required
from run_outputs import refresh_run_outputs
from zotero_mcp_client import ZoteroMCPClient


DEFAULT_MCP_URL = "http://127.0.0.1:23120/mcp"


@dataclass
class SyncConfig:
    zotero: ZoteroConfig
    mcp_url: str
    dry_run: bool


def parse_args() -> SyncConfig:
    parser = argparse.ArgumentParser(
        description=(
            "Synchronize the confirmed final screening to Zotero via zotero-mcp. "
            "This creates or updates bibliographic items and adds them to the "
            "configured collection."
        )
    )
    parser.add_argument(
        "--config-file",
        required=True,
        help="Env-style configuration file for the case, for example cases/<slug>/case.env.",
    )
    parser.add_argument(
        "--mcp-url",
        default=None,
        help="Override ZOTERO_MCP_URL.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Prepare and report actions without writing to Zotero.",
    )
    parser.add_argument(
        "--out-dir",
        default=None,
        help="Directory for sync logs. Default: outputs/<run>/zotero.",
    )

    args = parser.parse_args()
    config_file = Path(args.config_file).expanduser().resolve()
    env_config = load_env_config(config_file)

    zotero = ZoteroConfig(
        config_file=config_file,
        library=resolve_required(None, env_config, "ZOTERO_LIBRARY"),
        collection=resolve_required(None, env_config, "ZOTERO_COLLECTION"),
        attachments_dir=resolve_workspace_path(
            resolve_required(None, env_config, "ZOTERO_ATTACHMENTS_DIR"),
            config_file,
            env_config,
        ),
        library_files_dir=resolve_workspace_path(
            resolve_required(None, env_config, "ZOTERO_LIBRARY_FILES_DIR"),
            config_file,
            env_config,
        ),
        screening_decisions=resolve_workspace_path(
            resolve_required(None, env_config, "ZOTERO_SCREENING_DECISIONS"),
            config_file,
            env_config,
        ),
        screening_matrix=resolve_workspace_path(
            resolve_required(None, env_config, "ZOTERO_SCREENING_MATRIX"),
            config_file,
            env_config,
        ),
        out_dir=(
            resolve_workspace_path(args.out_dir, config_file, env_config)
            if args.out_dir
            else resolve_workspace_path(
                resolve_required(None, env_config, "ZOTERO_SCREENING_DECISIONS"),
                config_file,
                env_config,
            ).parent.parent / "zotero"
        ),
    )
    mcp_url = args.mcp_url or env_config.get("ZOTERO_MCP_URL", DEFAULT_MCP_URL).strip() or DEFAULT_MCP_URL
    return SyncConfig(zotero=zotero, mcp_url=mcp_url, dry_run=args.dry_run)


def parse_authors(raw_authors: str) -> list[dict[str, str]]:
    creators: list[dict[str, str]] = []
    for raw_name in [part.strip() for part in raw_authors.split(";") if part.strip()]:
        if "," in raw_name:
            last_name, first_name = [part.strip() for part in raw_name.split(",", 1)]
        else:
            parts = raw_name.split()
            if len(parts) == 1:
                creators.append({"creatorType": "author", "name": raw_name})
                continue
            first_name = " ".join(parts[:-1]).strip()
            last_name = parts[-1].strip()
        creators.append(
            {
                "creatorType": "author",
                "firstName": first_name,
                "lastName": last_name,
            }
        )
    return creators


def map_item_type(document_type: str) -> str:
    mapping = {
        "article": "journalArticle",
        "book-chapter": "bookSection",
        "dissertation": "thesis",
        "preprint": "preprint",
        "report": "report",
        "dataset": "report",
    }
    return mapping.get(document_type.strip().lower(), "journalArticle")


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def build_item_fields(row: dict[str, Any]) -> dict[str, str]:
    fields: dict[str, str] = {
        "title": normalize_text(row.get("title")),
        "abstractNote": normalize_text(row.get("abstract")),
        "date": normalize_text(row.get("publication_date") or row.get("year")),
        "url": normalize_text(row.get("source_url")),
        "DOI": normalize_text(row.get("doi")),
        "language": normalize_text(row.get("language")),
        "extra": build_extra_field(row),
    }
    journal = normalize_text(row.get("journal"))
    item_type = map_item_type(normalize_text(row.get("document_type")))
    if journal and item_type == "journalArticle":
        fields["publicationTitle"] = journal
    if item_type == "journalArticle":
        for source, target in (("volume", "volume"), ("issue", "issue"), ("pages", "pages")):
            value = normalize_text(row.get(source))
            if value:
                fields[target] = value
    if item_type == "preprint":
        repository = normalize_text(row.get("repository") or journal)
        if repository:
            fields["repository"] = repository
    if item_type in {"bookSection", "report", "thesis"}:
        publisher = normalize_text(row.get("publisher"))
        if publisher:
            fields["publisher"] = publisher
    return {key: value for key, value in fields.items() if value}


@contextmanager
def exclusive_collection_lock(library: str, collection: str, enabled: bool = True):
    """Prevent two CLI processes from racing search-before-create for one collection."""
    if not enabled:
        yield None
        return
    digest = hashlib.sha256(f"{library}\0{collection}".encode()).hexdigest()[:16]
    lock_path = Path(tempfile.gettempdir()) / f"prisma-zotero-{digest}.lock"
    with lock_path.open("a+", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError(
                f"Another Zotero synchronization is active for {library}/{collection}."
            ) from exc
        handle.seek(0)
        handle.truncate()
        handle.write(f"pid={os.getpid()}\n")
        handle.flush()
        try:
            yield lock_path
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def build_extra_field(row: dict[str, Any]) -> str:
    lines = [
        f"PRISMA-AI Tutor code: {normalize_text(row.get('code'))}",
        f"First affiliation: {normalize_text(row.get('first_affiliation'))}",
        f"Country: {normalize_text(row.get('country'))}",
        f"Document type: {normalize_text(row.get('document_type'))}",
        f"Final basis: {normalize_text(row.get('final_basis'))}",
        f"Final note: {normalize_text(row.get('final_note'))}",
        f"Local PDF path: {normalize_text(row.get('zotero_attachment_path'))}",
    ]
    return "\n".join(line for line in lines if not line.endswith(": "))


def ensure_collection_path(client: ZoteroMCPClient, collection_path: str, dry_run: bool) -> dict[str, Any]:
    current_parent: str | None = None
    current_collection: dict[str, Any] | None = None
    segments = [segment.strip() for segment in collection_path.split("/") if segment.strip()]

    for segment in segments:
        search_results = client.call_tool("search_collections", {"q": segment, "limit": 100})
        matches = [
            item for item in search_results
            if item.get("name") == segment
            and normalize_parent(item.get("parentCollection")) == normalize_parent(current_parent)
        ]
        if matches:
            current_collection = matches[0]
            current_parent = current_collection.get("key")
            continue

        if dry_run:
            current_collection = {
                "key": f"DRYRUN-{segment}",
                "name": segment,
                "path": build_collection_path(current_collection, segment),
                "parentCollection": current_parent or False,
            }
            current_parent = current_collection["key"]
            continue

        arguments = {"name": segment}
        if current_parent:
            arguments["parentCollection"] = current_parent
        created = client.call_tool("create_collection", arguments)
        created_key = extract_collection_key(created)
        current_collection = {
            "key": created_key,
            "name": segment,
            "path": build_collection_path(current_collection, segment),
            "parentCollection": current_parent or False,
        }
        current_parent = created_key

    if current_collection is None:
        raise ValueError(f"Invalid collection path: {collection_path!r}")
    return current_collection


def build_collection_path(current_collection: dict[str, Any] | None, segment: str) -> str:
    if current_collection and current_collection.get("path"):
        return f"{current_collection['path']} > {segment}"
    return segment


def normalize_parent(value: Any) -> str | None:
    if value in (None, False, "", "false"):
        return None
    return str(value)


def extract_collection_key(payload: Any) -> str:
    if isinstance(payload, dict):
        for key in ("key", "collectionKey"):
            if payload.get(key):
                return str(payload[key])
    raise ValueError(f"Unable to determine collection key from payload: {payload}")


def find_existing_item(client: ZoteroMCPClient, row: dict[str, Any]) -> dict[str, Any] | None:
    doi = normalize_text(row.get("doi"))
    if doi:
        results = client.call_tool(
            "search_library",
            {"q": doi, "limit": 10, "mode": "preview"},
        )
        for candidate in results.get("results", []):
            if candidate.get("key"):
                return candidate

    title = normalize_text(row.get("title"))
    if title:
        results = client.call_tool(
            "search_library",
            {"title": title, "titleOperator": "exact", "limit": 10, "mode": "preview"},
        )
        for candidate in results.get("results", []):
            if normalize_text(candidate.get("title")).casefold() == title.casefold():
                return candidate
    return None


def merge_metadata_updates(existing_details: dict[str, Any], row: dict[str, Any]) -> tuple[dict[str, str], list[dict[str, str]] | None]:
    desired_fields = build_item_fields(row)
    updates: dict[str, str] = {}

    for key, desired_value in desired_fields.items():
        current_value = normalize_text(existing_details.get(key))
        if not current_value:
            updates[key] = desired_value

    creators: list[dict[str, str]] | None = None
    existing_creators = existing_details.get("creators") or []
    if not existing_creators and normalize_text(row.get("authors")):
        creators = parse_authors(normalize_text(row.get("authors")))

    return updates, creators


def create_item_payload(row: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "action": "create",
        "itemType": map_item_type(normalize_text(row.get("document_type"))),
        "fields": build_item_fields(row),
        "tags": [
            "prisma-ai-tutor",
            "openalex",
            "final-confirmed",
        ],
    }
    authors = normalize_text(row.get("authors"))
    if authors:
        payload["creators"] = parse_authors(authors)
    return payload


def create_minimal_item_payload(row: dict[str, Any]) -> dict[str, Any]:
    fields = {
        key: value
        for key, value in build_item_fields(row).items()
        if key in {"title", "date", "url", "DOI", "language", "publicationTitle"}
    }
    payload = {
        "action": "create",
        "itemType": map_item_type(normalize_text(row.get("document_type"))),
        "fields": fields,
        "tags": [
            "prisma-ai-tutor",
            "openalex",
            "final-confirmed",
        ],
    }
    authors = normalize_text(row.get("authors"))
    if authors:
        payload["creators"] = parse_authors(authors)
    return payload


def create_item_with_fallback(client: ZoteroMCPClient, row: dict[str, Any]) -> tuple[str, str]:
    payload = create_item_payload(row)
    try:
        created = client.call_tool("write_item", payload)
        return extract_item_key(created), "full"
    except HTTPError:
        fallback = client.call_tool("write_item", create_minimal_item_payload(row))
        return extract_item_key(fallback), "minimal_fallback"


def extract_item_key(payload: Any) -> str:
    if isinstance(payload, dict):
        for key in ("key", "itemKey"):
            if payload.get(key):
                return str(payload[key])
        data = payload.get("data")
        if isinstance(data, dict):
            for key in ("key", "itemKey"):
                if data.get(key):
                    return str(data[key])
        if payload.get("successful"):
            successful = payload["successful"]
            if isinstance(successful, dict):
                first_value = next(iter(successful.values()), {})
                if isinstance(first_value, dict):
                    for key in ("key", "itemKey"):
                        if first_value.get(key):
                            return str(first_value[key])
    raise ValueError(f"Unable to determine item key from payload: {payload}")


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row.keys():
            if key not in seen:
                seen.add(key)
                fieldnames.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def sync(config: SyncConfig) -> dict[str, Any]:
    prepared = prepare_import(config.zotero)
    manifest_rows = prepared["manifest_rows"]

    client = ZoteroMCPClient(config.mcp_url)
    client.initialize()
    collection = ensure_collection_path(client, config.zotero.collection, config.dry_run)
    collection_key = collection["key"]

    action_rows: list[dict[str, Any]] = []

    for row in manifest_rows:
        existing = find_existing_item(client, row)
        if existing:
            item_key = normalize_text(existing.get("key"))
            action = "update_existing"
            if not config.dry_run:
                details = client.call_tool(
                    "get_item_details",
                    {"itemKey": item_key, "mode": "complete"},
                )
                field_updates, creators = merge_metadata_updates(details, row)
                if field_updates or creators:
                    arguments: dict[str, Any] = {"itemKey": item_key}
                    if field_updates:
                        arguments["fields"] = field_updates
                    if creators:
                        arguments["creators"] = creators
                    client.call_tool("write_metadata", arguments)
                client.call_tool(
                    "add_items_to_collection",
                    {"collectionKey": collection_key, "itemKeys": [item_key]},
                )
            else:
                field_updates, creators = {}, None
            action_rows.append(
                {
                    "code": row["code"],
                    "title": row["title"],
                    "item_key": item_key,
                    "action": action,
                    "collection_key": collection_key,
                    "attachment_status": row.get("attachment_status", ""),
                    "zotero_attachment_path": row.get("zotero_attachment_path", ""),
                }
            )
            continue

        if config.dry_run:
            item_key = f"DRYRUN-{row['code']}"
            create_mode = "dry_run"
        else:
            item_key, create_mode = create_item_with_fallback(client, row)
            client.call_tool(
                "add_items_to_collection",
                {"collectionKey": collection_key, "itemKeys": [item_key]},
            )
        action_rows.append(
            {
                "code": row["code"],
                "title": row["title"],
                "item_key": item_key,
                "action": "create_new",
                "create_mode": create_mode,
                "collection_key": collection_key,
                "attachment_status": row.get("attachment_status", ""),
                "zotero_attachment_path": row.get("zotero_attachment_path", ""),
            }
        )

    return {
        "prepared_summary": prepared["summary"],
        "collection": collection,
        "actions": action_rows,
        "dry_run": config.dry_run,
        "mcp_url": config.mcp_url,
        "attachment_limitation": (
            "zotero-mcp currently exposes item and collection operations, but not "
            "a direct tool to import local PDFs as Zotero attachment items. PDFs "
            "were copied to ZOTERO_LIBRARY_FILES_DIR during manifest preparation, "
            "but attachment linking may still require a future MCP capability or a "
            "manual/auxiliary step."
        ),
    }


def main() -> int:
    config = parse_args()
    with exclusive_collection_lock(
        config.zotero.library,
        config.zotero.collection,
        enabled=not config.dry_run,
    ):
        result = sync(config)

    config.zotero.out_dir.mkdir(parents=True, exist_ok=True)
    summary_json = config.zotero.out_dir / "zotero_sync_summary.json"
    actions_csv = config.zotero.out_dir / "zotero_sync_actions.csv"
    write_json(summary_json, result)
    write_csv(actions_csv, result["actions"])
    refresh_run_outputs(config.zotero.out_dir.parent)

    print(
        f"Zotero sync {'preview' if config.dry_run else 'completed'} for "
        f"{len(result['actions'])} items."
    )
    print(f"Collection: {result['collection'].get('path', config.zotero.collection)}")
    print(f"Summary JSON: {summary_json}")
    print(f"Actions CSV: {actions_csv}")
    if result["attachment_limitation"]:
        print(result["attachment_limitation"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
