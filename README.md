# Knowledge Base Automation

A lightweight workflow for turning screenshot-based knowledge into structured notes and publishing them to a Notion knowledge base.

## Overview

This project connects three stages into one practical pipeline:

1. **Gem** extracts knowledge from screenshots and returns standardised Markdown
2. **GitHub** stores the Markdown files and runs the ingestion workflow
3. **Notion** receives the parsed content as database entries with formatted page content

The design deliberately keeps the semantic extraction in the Gem, while keeping the publishing pipeline deterministic.

## Workflow

### End-to-end flow

```text
Screenshot(s)
  -> Gem
  -> standard Markdown note(s)
  -> GitHub pending folder
  -> GitHub Actions workflow
  -> process_notes.py parser
  -> Notion database entry + page content
```

### Why this approach

This project uses a hybrid model rather than a fully automated screenshot-to-Notion LLM flow.

* **Gem** handles interpretation and summarisation
* **GitHub** acts as the intake, audit, and automation layer
* **Python parser** handles validation and Notion formatting
* **Notion** stores the final knowledge base entries

This keeps the flexible part where it is useful and the repetitive part where it is reliable.

## Repository structure

```text
.
├── .github/
│   └── workflows/
│       └── main.yml
├── pending/
│   └── md/
├── processed/
│   └── md/
├── failed/
│   └── md/
├── manifests/
│   └── ingest_log.jsonl
├── process_notes.py
└── requirements.txt
```

## Markdown contract

Each screenshot should be converted into one Markdown note using this structure:

```markdown
---
title: "Short, specific title"
category: "General"
tags: ["tag-one", "tag-two"]
created_at: "2026-04-03"
status: "Not started"
filename: "20260403_01.md"
---

# Knowledge Summary
Concise summary of the useful content.

# Extracted Details
- Important point
- Important point

# Key Takeaways
- Optional takeaway
- Optional takeaway

# Actionable Tips
- Optional action
- Optional action
```

### Required frontmatter fields

* `title`
* `category`
* `tags`
* `created_at`
* `status`
* `filename`

### Required section

* `# Knowledge Summary`

### Expected section

* `# Extracted Details`

### Optional sections

* `# Key Takeaways`
* `# Actionable Tips`

## Supported categories

The project uses a controlled category list:

* Technical Tip
* Book Recommendation
* SEO
* AEO
* GEO
* AI/LLM
* Automation
* Productivity
* General

If uncertain, use `General`.

## Notion schema

The workflow is currently designed for a Notion database with these properties:

* **Name** (title)
* **Category**
* **Created At**
* **Status**
* **Tag**

Mapping from Markdown to Notion:

* `title` -> **Name**
* `category` -> **Category**
* `created_at` -> **Created At**
* `status` -> **Status**
* `tags` -> **Tag**

The `filename` field is used for workflow handling and logging, not as a Notion property.

## What the ingestion script does

`process_notes.py` is responsible for:

* scanning Markdown files from `pending/` and `pending/md/`
* parsing YAML frontmatter and body sections
* validating required fields and sections
* creating a page in the target Notion database
* converting page content into Notion blocks
* preserving basic inline formatting such as bold markers in supported content
* moving successful files to `processed/`
* moving failed files to `failed/`
* recording results in `manifests/ingest_log.jsonl`
* skipping exact duplicates using a local content hash log

## GitHub Actions workflow

The workflow is triggered by:

* pushes affecting Markdown files in `pending/`
* manual runs via `workflow_dispatch`

The workflow performs these steps:

1. check out the repository
2. set up Python
3. install dependencies
4. run `process_notes.py`
5. commit repository updates for processed, failed, and manifest changes

## Setup

### 1. Create the Notion integration

Create a Notion integration and make sure the target database is shared with it.

### 2. Configure GitHub secrets

Set the following repository secrets:

* `NOTION_TOKEN`
* `NOTION_DATABASE_ID`

Use the actual database ID, not the view ID.

### 3. Install dependencies locally if needed

```bash
pip install -r requirements.txt
```

### 4. Add Markdown notes for ingestion

Place generated Markdown files into one of these locations:

* `pending/`
* `pending/md/`

### 5. Trigger the workflow

Either:

* push the files to GitHub, or
* run the workflow manually from GitHub Actions

## Operating model

### Recommended usage

1. upload screenshot(s) to the Gem
2. get standard Markdown output in chat
3. save each note as a `.md` file
4. place the files into `pending/md/`
5. let GitHub Actions publish them to Notion

### Design principle

The LLM should interpret the screenshot once.

After that, the pipeline should be deterministic.

## Validation behaviour

The parser validates:

* frontmatter exists
* required frontmatter fields are present
* `created_at` is in the expected format
* category is allowed
* `Knowledge Summary` exists
* Markdown can be transformed into valid Notion content blocks

Optional sections are allowed to be absent.

## Logging and file movement

After processing:

* successful notes move to `processed/` or `processed/md/`
* failed notes move to `failed/` or `failed/md/`
* results are written to `manifests/ingest_log.jsonl`

This makes the workflow easier to audit and troubleshoot.

## Common issues

### Notion API returns `object_not_found`

Usually one of these:

* the database ID is wrong
* the integration does not have access to the database
* the ID used is a page or view ID rather than the database ID

### Formatting does not appear correctly in Notion

Notion does not render raw Markdown markers automatically through the API. Inline formatting must be converted into Notion rich text annotations by the ingestion script.

### Workflow skips a file unexpectedly

The file may already have been ingested and logged as a duplicate based on its content hash.

## Limitations

Current scope is intentionally narrow:

* designed for Markdown generated from screenshots
* not a general-purpose Markdown importer
* duplicate detection is local-log based, not a full Notion lookup
* formatting support is practical rather than full Markdown parity

## Future improvements

Possible next steps include:

* link parsing and richer inline Markdown support
* stronger duplicate detection against Notion itself
* malformed note repair path
* category and tag normalisation helpers
* batch QA reporting for ingested notes

## Status

Project complete and working across:

**Gem -> GitHub -> Notion**

The end-to-end integration has been tested successfully.

## License

Add the project license here if you decide to publish the repository publicly.
