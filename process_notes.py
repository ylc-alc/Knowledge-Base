from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests
import yaml

NOTION_VERSION = "2022-06-28"
ALLOWED_CATEGORIES = {
    "Technical Tip",
    "Book Recommendation",
    "SEO",
    "AEO",
    "GEO",
    "AI/LLM",
    "Automation",
    "Productivity",
    "General",
}
DEFAULT_STATUS = "Not started"
SECTION_ORDER = [
    "Knowledge Summary",
    "Extracted Details",
    "Key Takeaways",
    "Actionable Tips",
]
MAX_RICH_TEXT = 2000
MAX_CHILDREN_PER_APPEND = 100


@dataclass
class ParsedNote:
    path: Path
    metadata: Dict[str, Any]
    sections: Dict[str, str]
    body: str
    content_hash: str


class ValidationError(Exception):
    pass


def repo_root() -> Path:
    return Path(os.environ.get("GITHUB_WORKSPACE", Path.cwd())).resolve()


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def pending_files(root: Path) -> List[Path]:
    candidates: set[Path] = set()
    for rel in ("pending", "pending/md"):
        base = root / rel
        if base.exists():
            for path in base.rglob("*.md"):
                if path.is_file():
                    candidates.add(path)
    return sorted(candidates)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def parse_markdown_note(path: Path) -> ParsedNote:
    text = read_text(path)
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", text, flags=re.DOTALL)
    if not match:
        raise ValidationError("Missing YAML frontmatter")

    raw_meta, body = match.groups()
    metadata = yaml.safe_load(raw_meta) or {}
    if not isinstance(metadata, dict):
        raise ValidationError("Frontmatter must be a YAML object")

    metadata = normalise_metadata(metadata, path)
    sections = split_sections(body)

    knowledge_summary = sections.get("Knowledge Summary", "").strip()
    if not knowledge_summary:
        raise ValidationError("Missing required '# Knowledge Summary' section")

    return ParsedNote(
        path=path,
        metadata=metadata,
        sections=sections,
        body=body.strip(),
        content_hash=sha256_text(text),
    )


def normalise_metadata(metadata: Dict[str, Any], path: Path) -> Dict[str, Any]:
    required = ["title", "category", "tags", "created_at"]
    missing = [key for key in required if key not in metadata or metadata[key] in (None, "")]
    if missing:
        raise ValidationError(f"Missing required frontmatter fields: {', '.join(missing)}")

    title = str(metadata["title"]).strip()
    if not title:
        raise ValidationError("Frontmatter field 'title' cannot be empty")

    category = str(metadata["category"]).strip()
    if category not in ALLOWED_CATEGORIES:
        allowed = ", ".join(sorted(ALLOWED_CATEGORIES))
        raise ValidationError(f"Invalid category '{category}'. Allowed values: {allowed}")

    tags = metadata["tags"]
    if isinstance(tags, str):
        tags = [part.strip() for part in tags.split(",") if part.strip()]
    if not isinstance(tags, list) or not tags:
        raise ValidationError("Frontmatter field 'tags' must be a non-empty list or comma-separated string")
    clean_tags: List[str] = []
    for tag in tags:
        tag_str = str(tag).strip()
        if not tag_str:
            continue
        clean_tags.append(tag_str)
    if not clean_tags:
        raise ValidationError("Frontmatter field 'tags' does not contain any usable values")

    created_at = str(metadata["created_at"]).strip()
    try:
        date.fromisoformat(created_at)
    except ValueError as exc:
        raise ValidationError("Frontmatter field 'created_at' must use YYYY-MM-DD") from exc

    status = str(metadata.get("status") or DEFAULT_STATUS).strip() or DEFAULT_STATUS
    filename = str(metadata.get("filename") or path.name).strip() or path.name

    return {
        "title": title,
        "category": category,
        "tags": clean_tags,
        "created_at": created_at,
        "status": status,
        "filename": filename,
    }


def split_sections(body: str) -> Dict[str, str]:
    sections: Dict[str, str] = {}
    current_heading: Optional[str] = None
    buffer: List[str] = []

    for line in body.splitlines():
        heading_match = re.match(r"^#\s+(.+?)\s*$", line)
        if heading_match:
            if current_heading is not None:
                sections[current_heading] = "\n".join(buffer).strip()
            current_heading = heading_match.group(1).strip()
            buffer = []
        else:
            buffer.append(line)

    if current_heading is not None:
        sections[current_heading] = "\n".join(buffer).strip()

    return sections


def notion_headers(token: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def notion_request(method: str, url: str, token: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    response = requests.request(
        method=method,
        url=url,
        headers=notion_headers(token),
        json=payload,
        timeout=60,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"Notion API error {response.status_code}: {response.text}")
    return response.json() if response.content else {}


def fetch_database_schema(token: str, database_id: str) -> Dict[str, Any]:
    return notion_request("GET", f"https://api.notion.com/v1/databases/{database_id}", token)


def get_title_property_name(schema: Dict[str, Any]) -> str:
    for name, config in schema.get("properties", {}).items():
        if config.get("type") == "title":
            return name
    raise RuntimeError("Could not find the title property in the Notion database schema")


def build_properties(note: ParsedNote, schema: Dict[str, Any]) -> Dict[str, Any]:
    meta = note.metadata
    properties_schema = schema.get("properties", {})
    title_name = get_title_property_name(schema)

    props: Dict[str, Any] = {
        title_name: {
            "title": [rich_text_item(meta["title"])],
        }
    }

    for prop_name, prop_config in properties_schema.items():
        if prop_name == title_name:
            continue
        prop_type = prop_config.get("type")

        if prop_name == "Category":
            if prop_type == "select":
                props[prop_name] = {"select": {"name": meta["category"]}}
            elif prop_type == "rich_text":
                props[prop_name] = {"rich_text": rich_text_array(meta["category"])}
        elif prop_name == "Created At":
            if prop_type == "date":
                props[prop_name] = {"date": {"start": meta["created_at"]}}
            elif prop_type == "rich_text":
                props[prop_name] = {"rich_text": rich_text_array(meta["created_at"])}
        elif prop_name == "Status":
            if prop_type == "status":
                props[prop_name] = {"status": {"name": meta["status"]}}
            elif prop_type == "select":
                props[prop_name] = {"select": {"name": meta["status"]}}
            elif prop_type == "rich_text":
                props[prop_name] = {"rich_text": rich_text_array(meta["status"])}
        elif prop_name == "Tag":
            if prop_type == "multi_select":
                props[prop_name] = {"multi_select": [{"name": tag} for tag in meta["tags"]]}
            elif prop_type == "select" and meta["tags"]:
                props[prop_name] = {"select": {"name": meta["tags"][0]}}
            elif prop_type == "rich_text":
                props[prop_name] = {"rich_text": rich_text_array(", ".join(meta["tags"]))}

    return props


def rich_text_item(text: str) -> Dict[str, Any]:
    return {
        "type": "text",
        "text": {
            "content": text[:MAX_RICH_TEXT],
        },
    }


def rich_text_array(text: str) -> List[Dict[str, Any]]:
    if not text:
        return []
    chunks = [text[i : i + MAX_RICH_TEXT] for i in range(0, len(text), MAX_RICH_TEXT)]
    return [rich_text_item(chunk) for chunk in chunks]


def blocks_from_note(note: ParsedNote) -> List[Dict[str, Any]]:
    blocks: List[Dict[str, Any]] = []
    sections = note.sections

    ordered_headings = [heading for heading in SECTION_ORDER if heading in sections]
    remaining_headings = [heading for heading in sections.keys() if heading not in ordered_headings]

    for heading in ordered_headings + remaining_headings:
        content = sections.get(heading, "").strip()
        if not content:
            continue
        blocks.append(heading_block(heading))
        blocks.extend(parse_section_content(content))

    if not blocks:
        blocks.append(paragraph_block(note.body))
    return blocks


def heading_block(text: str) -> Dict[str, Any]:
    return {
        "object": "block",
        "type": "heading_2",
        "heading_2": {
            "rich_text": rich_text_array(text),
        },
    }


def paragraph_block(text: str) -> Dict[str, Any]:
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {
            "rich_text": rich_text_array(text.strip()),
        },
    }


def bulleted_block(text: str) -> Dict[str, Any]:
    return {
        "object": "block",
        "type": "bulleted_list_item",
        "bulleted_list_item": {
            "rich_text": rich_text_array(text.strip()),
        },
    }


def numbered_block(text: str) -> Dict[str, Any]:
    return {
        "object": "block",
        "type": "numbered_list_item",
        "numbered_list_item": {
            "rich_text": rich_text_array(text.strip()),
        },
    }


def parse_section_content(content: str) -> List[Dict[str, Any]]:
    blocks: List[Dict[str, Any]] = []
    paragraph_buffer: List[str] = []

    def flush_paragraph() -> None:
        nonlocal paragraph_buffer
        text = " ".join(part.strip() for part in paragraph_buffer if part.strip()).strip()
        if text:
            blocks.append(paragraph_block(text))
        paragraph_buffer = []

    for raw_line in content.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()

        if not stripped:
            flush_paragraph()
            continue

        bullet_match = re.match(r"^\s*[-*+]\s+(.*)$", line)
        if bullet_match:
            flush_paragraph()
            blocks.append(bulleted_block(bullet_match.group(1)))
            continue

        numbered_match = re.match(r"^\s*\d+[.)]\s+(.*)$", line)
        if numbered_match:
            flush_paragraph()
            blocks.append(numbered_block(numbered_match.group(1)))
            continue

        paragraph_buffer.append(stripped)

    flush_paragraph()
    return blocks


def append_children(token: str, block_id: str, children: List[Dict[str, Any]]) -> None:
    for idx in range(0, len(children), MAX_CHILDREN_PER_APPEND):
        batch = children[idx : idx + MAX_CHILDREN_PER_APPEND]
        notion_request(
            "PATCH",
            f"https://api.notion.com/v1/blocks/{block_id}/children",
            token,
            payload={"children": batch},
        )


def create_page(token: str, database_id: str, properties: Dict[str, Any]) -> Dict[str, Any]:
    payload = {
        "parent": {"database_id": database_id},
        "properties": properties,
    }
    return notion_request("POST", "https://api.notion.com/v1/pages", token, payload)


def manifest_path(root: Path) -> Path:
    return root / "manifests" / "ingest_log.jsonl"


def read_processed_hashes(path: Path) -> set[str]:
    hashes: set[str] = set()
    if not path.exists():
        return hashes
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("status") == "success" and record.get("content_hash"):
                hashes.add(record["content_hash"])
    return hashes


def append_manifest(path: Path, record: Dict[str, Any]) -> None:
    ensure_dir(path.parent)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def move_processed(root: Path, source: Path, outcome: str) -> Path:
    pending_root = root / "pending"
    relative = source.relative_to(pending_root)
    destination = root / outcome / relative
    ensure_dir(destination.parent)
    if destination.exists():
        destination.unlink()
    shutil.move(str(source), str(destination))
    cleanup_empty_dirs(source.parent, stop_at=pending_root)
    return destination


def cleanup_empty_dirs(path: Path, stop_at: Path) -> None:
    current = path
    while current != stop_at and current.exists():
        try:
            current.rmdir()
        except OSError:
            break
        current = current.parent


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def main() -> int:
    root = repo_root()
    token = os.environ.get("NOTION_TOKEN")
    database_id = os.environ.get("NOTION_DATABASE_ID")

    if not token or not database_id:
        raise RuntimeError("Missing NOTION_TOKEN or NOTION_DATABASE_ID environment variable")

    notes = pending_files(root)
    if not notes:
        print("No markdown notes found under pending/ or pending/md/")
        return 0

    schema = fetch_database_schema(token, database_id)
    log_path = manifest_path(root)
    processed_hashes = read_processed_hashes(log_path)

    failures = 0
    for path in notes:
        record: Dict[str, Any] = {
            "timestamp": now_iso(),
            "source_path": str(path.relative_to(root)),
        }
        try:
            note = parse_markdown_note(path)
            record.update(
                {
                    "title": note.metadata["title"],
                    "created_at": note.metadata["created_at"],
                    "filename": note.metadata.get("filename", path.name),
                    "content_hash": note.content_hash,
                }
            )

            if note.content_hash in processed_hashes:
                record.update(
                    {
                        "status": "skipped_duplicate",
                        "reason": "Matching content hash already ingested successfully",
                    }
                )
                moved = move_processed(root, path, "processed")
                record["destination_path"] = str(moved.relative_to(root))
                append_manifest(log_path, record)
                print(f"Skipped duplicate: {path}")
                continue

            properties = build_properties(note, schema)
            page = create_page(token, database_id, properties)
            page_id = page["id"]
            blocks = blocks_from_note(note)
            if blocks:
                append_children(token, page_id, blocks)

            moved = move_processed(root, path, "processed")
            record.update(
                {
                    "status": "success",
                    "page_id": page_id,
                    "destination_path": str(moved.relative_to(root)),
                }
            )
            append_manifest(log_path, record)
            processed_hashes.add(note.content_hash)
            print(f"Ingested: {path}")

        except Exception as exc:
            failures += 1
            record.update(
                {
                    "status": "failed",
                    "error": str(exc),
                }
            )
            if path.exists():
                moved = move_processed(root, path, "failed")
                record["destination_path"] = str(moved.relative_to(root))
            append_manifest(log_path, record)
            print(f"Failed: {path} -> {exc}")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
