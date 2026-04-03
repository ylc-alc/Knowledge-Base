import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import frontmatter
from notion_client import Client


# -------- Configuration --------

PENDING_DIR = Path("pending/md")
PROCESSED_DIR = Path("processed/md")
FAILED_DIR = Path("failed/md")
MANIFEST_PATH = Path("manifests/ingest_log.jsonl")

NOTION_TOKEN = os.environ["NOTION_TOKEN"]
NOTION_DATABASE_ID = os.environ["NOTION_DATABASE_ID"]

NOTION_TITLE_PROPERTY = os.getenv("NOTION_TITLE_PROPERTY", "Name")
NOTION_CATEGORY_PROPERTY = os.getenv("NOTION_CATEGORY_PROPERTY", "Category")
NOTION_TAG_PROPERTY = os.getenv("NOTION_TAG_PROPERTY", "Tag")

# Optional properties. Only used if set.
NOTION_SOURCE_FILE_PROPERTY = os.getenv("NOTION_SOURCE_FILE_PROPERTY")
NOTION_SOURCE_MODEL_PROPERTY = os.getenv("NOTION_SOURCE_MODEL_PROPERTY")

SECTION_ORDER = [
    "Knowledge Summary",
    "Key Takeaways",
    "Actionable Tips",
]

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

CATEGORY_ALIASES = {
    "technical tips": "Technical Tip",
    "technical tip": "Technical Tip",
    "book recommendations": "Book Recommendation",
    "book recommendation": "Book Recommendation",
    "book": "Book Recommendation",
    "seo": "SEO",
    "aeo": "AEO",
    "geo": "GEO",
    "ai": "AI/LLM",
    "llm": "AI/LLM",
    "ai/llm": "AI/LLM",
    "automation": "Automation",
    "productivity": "Productivity",
    "general": "General",
}


# -------- Models --------

@dataclass
class ParsedNote:
    file_path: Path
    title: str
    category: str
    tags: list[str]
    source_file: str | None
    source_model: str | None
    knowledge_summary: str
    key_takeaways: list[str]
    actionable_tips: list[str]


# -------- Helpers --------

def ensure_dirs() -> None:
    for path in [PENDING_DIR, PROCESSED_DIR, FAILED_DIR, MANIFEST_PATH.parent]:
        path.mkdir(parents=True, exist_ok=True)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalise_category(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Missing or invalid 'category' in frontmatter.")

    raw = value.strip()
    alias_key = raw.lower()
    normalised = CATEGORY_ALIASES.get(alias_key, raw)

    if normalised not in ALLOWED_CATEGORIES:
        raise ValueError(
            f"Unsupported category '{raw}'. Allowed values: {sorted(ALLOWED_CATEGORIES)}"
        )

    return normalised


def normalise_tags(value: Any) -> list[str]:
    if isinstance(value, str):
        raw_tags = [part.strip() for part in value.split(",")]
    elif isinstance(value, list):
        raw_tags = [str(part).strip() for part in value]
    else:
        raise ValueError("Missing or invalid 'tags' in frontmatter.")

    tags: list[str] = []
    for tag in raw_tags:
        if not tag:
            continue
        cleaned = tag.strip().lower()
        cleaned = re.sub(r"\s+", "-", cleaned)
        cleaned = re.sub(r"[^a-z0-9\-_\/]+", "", cleaned)
        if cleaned:
            tags.append(cleaned)

    deduped: list[str] = []
    seen = set()
    for tag in tags:
        if tag not in seen:
            deduped.append(tag)
            seen.add(tag)

    if not deduped:
        raise ValueError("At least one valid tag is required.")

    return deduped[:10]


def extract_sections(content: str) -> dict[str, str]:
    """
    Expects markdown headings exactly:
    # Knowledge Summary
    # Key Takeaways
    # Actionable Tips

    Also accepts ## or ###.
    """
    heading_pattern = re.compile(
        r"(?m)^(#{1,3})\s+(Knowledge Summary|Key Takeaways|Actionable Tips)\s*$"
    )
    matches = list(heading_pattern.finditer(content))

    if len(matches) < 3:
        raise ValueError(
            "Markdown must include the headings: Knowledge Summary, Key Takeaways, Actionable Tips."
        )

    sections: dict[str, str] = {}

    for idx, match in enumerate(matches):
        heading = match.group(2)
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(content)
        body = content[start:end].strip()
        sections[heading] = body

    missing = [section for section in SECTION_ORDER if section not in sections]
    if missing:
        raise ValueError(f"Missing required sections: {missing}")

    return sections


def parse_bullets(section_text: str, section_name: str) -> list[str]:
    lines = section_text.splitlines()
    bullets: list[str] = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        bullet_match = re.match(r"^(?:[-*]|\d+\.)\s+(.+)$", line)
        if bullet_match:
            bullets.append(bullet_match.group(1).strip())

    if not bullets:
        raise ValueError(f"Section '{section_name}' must contain bullet points.")

    return bullets


def parse_markdown_note(file_path: Path) -> ParsedNote:
    post = frontmatter.load(file_path)
    metadata = post.metadata
    body = post.content.strip()

    title = str(metadata.get("title", "")).strip()
    if not title:
        raise ValueError("Missing or invalid 'title' in frontmatter.")

    category = normalise_category(metadata.get("category"))
    tags = normalise_tags(metadata.get("tags"))

    source_file = metadata.get("source_file")
    source_model = metadata.get("source_model")

    if source_file is not None:
        source_file = str(source_file).strip() or None
    if source_model is not None:
        source_model = str(source_model).strip() or None

    sections = extract_sections(body)

    knowledge_summary = sections["Knowledge Summary"].strip()
    if not knowledge_summary:
        raise ValueError("Section 'Knowledge Summary' must not be empty.")

    key_takeaways = parse_bullets(sections["Key Takeaways"], "Key Takeaways")
    actionable_tips = parse_bullets(sections["Actionable Tips"], "Actionable Tips")

    return ParsedNote(
        file_path=file_path,
        title=title,
        category=category,
        tags=tags,
        source_file=source_file,
        source_model=source_model,
        knowledge_summary=knowledge_summary,
        key_takeaways=key_takeaways,
        actionable_tips=actionable_tips,
    )


def text_chunks(text: str, size: int = 1800) -> list[str]:
    text = text.strip()
    if not text:
        return []

    chunks: list[str] = []
    while text:
        if len(text) <= size:
            chunks.append(text)
            break

        split_at = text.rfind(" ", 0, size)
        if split_at == -1:
            split_at = size

        chunks.append(text[:split_at].strip())
        text = text[split_at:].strip()

    return chunks


def rich_text(text: str) -> list[dict[str, Any]]:
    return [{"type": "text", "text": {"content": chunk}} for chunk in text_chunks(text)]


def paragraph_blocks(text: str) -> list[dict[str, Any]]:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    blocks: list[dict[str, Any]] = []

    for paragraph in paragraphs:
        blocks.append(
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": rich_text(paragraph)},
            }
        )

    return blocks


def bullet_blocks(items: list[str]) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for item in items:
        blocks.append(
            {
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {"rich_text": rich_text(item)},
            }
        )
    return blocks


def build_page_properties(note: ParsedNote) -> dict[str, Any]:
    properties: dict[str, Any] = {
        NOTION_TITLE_PROPERTY: {
            "title": [
                {
                    "text": {
                        "content": note.title
                    }
                }
            ]
        },
        NOTION_CATEGORY_PROPERTY: {
            "select": {"name": note.category}
        },
        NOTION_TAG_PROPERTY: {
            "multi_select": [{"name": tag} for tag in note.tags]
        },
    }

    if NOTION_SOURCE_FILE_PROPERTY and note.source_file:
        properties[NOTION_SOURCE_FILE_PROPERTY] = {
            "rich_text": [{"text": {"content": note.source_file}}]
        }

    if NOTION_SOURCE_MODEL_PROPERTY and note.source_model:
        properties[NOTION_SOURCE_MODEL_PROPERTY] = {
            "rich_text": [{"text": {"content": note.source_model}}]
        }

    return properties


def build_page_children(note: ParsedNote) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []

    meta_parts = []
    if note.source_file:
        meta_parts.append(f"Source file: {note.source_file}")
    if note.source_model:
        meta_parts.append(f"Source model: {note.source_model}")

    if meta_parts:
        blocks.append(
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": rich_text(" | ".join(meta_parts))
                },
            }
        )

    blocks.append(
        {
            "object": "block",
            "type": "heading_2",
            "heading_2": {"rich_text": rich_text("Knowledge Summary")},
        }
    )
    blocks.extend(paragraph_blocks(note.knowledge_summary))

    blocks.append(
        {
            "object": "block",
            "type": "heading_2",
            "heading_2": {"rich_text": rich_text("Key Takeaways")},
        }
    )
    blocks.extend(bullet_blocks(note.key_takeaways))

    blocks.append(
        {
            "object": "block",
            "type": "heading_2",
            "heading_2": {"rich_text": rich_text("Actionable Tips")},
        }
    )
    blocks.extend(bullet_blocks(note.actionable_tips))

    return blocks


def move_file(src: Path, src_root: Path, dest_root: Path) -> Path:
    relative_path = src.relative_to(src_root)
    dest = dest_root / relative_path
    dest.parent.mkdir(parents=True, exist_ok=True)

    if dest.exists():
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        dest = dest.with_name(f"{dest.stem}_{timestamp}{dest.suffix}")

    src.rename(dest)
    return dest


def append_manifest(record: dict[str, Any]) -> None:
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    with MANIFEST_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


# -------- Main --------

def main() -> None:
    ensure_dirs()
    notion = Client(auth=NOTION_TOKEN)

    files = sorted(
        path for path in PENDING_DIR.rglob("*.md")
        if path.is_file() and not path.name.startswith("_")
    )

    if not files:
        print("No pending markdown notes found.")
        return

    print(f"Found {len(files)} markdown note(s) to process.")

    for file_path in files:
        print(f"Processing: {file_path}")

        try:
            note = parse_markdown_note(file_path)

            response = notion.pages.create(
                parent={"database_id": NOTION_DATABASE_ID},
                properties=build_page_properties(note),
                children=build_page_children(note),
            )

            archived_path = move_file(file_path, PENDING_DIR, PROCESSED_DIR)

            append_manifest(
                {
                    "timestamp": now_iso(),
                    "status": "success",
                    "file": str(file_path),
                    "archived_to": str(archived_path),
                    "title": note.title,
                    "category": note.category,
                    "tags": note.tags,
                    "notion_page_id": response["id"],
                }
            )

            print(f"Success: {file_path}")

        except Exception as exc:
            failed_path = move_file(file_path, PENDING_DIR, FAILED_DIR)

            append_manifest(
                {
                    "timestamp": now_iso(),
                    "status": "failed",
                    "file": str(file_path),
                    "failed_to": str(failed_path),
                    "error": str(exc),
                }
            )

            print(f"Failed: {file_path} | {exc}")


if __name__ == "__main__":
    main()
