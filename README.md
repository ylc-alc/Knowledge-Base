# Knowledge Base Automation

Turn screenshots into structured knowledge notes and publish them to Notion through a lightweight GitHub-based workflow.

## What this project does

This project connects three tools into one practical pipeline:

* **Gem** extracts knowledge from screenshots and returns standardised Markdown
* **GitHub** stores notes, runs validation, and triggers ingestion
* **Notion** receives the final database entry and formatted page content

The workflow is designed to keep interpretation flexible and publishing reliable.

## How it works

```text
Screenshot(s)
  -> Gem
  -> Markdown note(s)
  -> GitHub pending folder
  -> GitHub Actions
  -> process_notes.py
  -> Notion database
```

## Why this approach

Instead of relying on a second LLM pass during ingestion, this project separates responsibilities clearly:

* **Gem** handles semantic extraction
* **GitHub Actions** handles automation
* **Python** handles parsing, validation, and Notion formatting
* **Notion** acts as the final knowledge base

This makes the workflow easier to audit, easier to troubleshoot, and more stable over time.

## Features

* Screenshot-to-Markdown workflow through a custom Gem
* Standardised Markdown contract for notes
* GitHub Actions-based ingestion pipeline
* Automatic publishing to a Notion database
* Structured Notion page content with basic inline formatting support
* File movement for success and failure handling
* JSONL ingest logging for traceability
* Local duplicate protection based on content hash

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

## Quick start

### 1. Create and configure your Notion integration

Create a Notion integration and make sure the target database is shared with it.

### 2. Add GitHub repository secrets

Set these repository secrets:

* `NOTION_TOKEN`
* `NOTION_DATABASE_ID`

Use the actual **database ID**, not the view ID.

### 3. Install dependencies locally if needed

```bash
pip install -r requirements.txt
```

### 4. Generate Markdown notes from screenshots

Use your Gem to turn screenshot content into Markdown notes following the project contract.

### 5. Add notes to the pending folder

Place note files into:

* `pending/`
* or `pending/md/`

### 6. Trigger ingestion

Either:

* push the files to GitHub
* or run the workflow manually with `workflow_dispatch`

## Markdown format

Each screenshot should be converted into one Markdown note with YAML frontmatter and standard sections.

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

## Example output

Below is a sample Markdown note generated from a screenshot and prepared for ingestion.

```markdown
---
title: "How to win with AI in 2026"
category: "AI/LLM"
tags: ["ai-strategy", "productivity", "career-growth", "automation"]
created_at: "2026-04-03"
status: "Not started"
filename: "20260403_02.md"
---

# Knowledge Summary
A practical summary of how to use AI as a force multiplier in day-to-day work, with emphasis on task decomposition, prompt quality, rapid iteration, and balancing automation with human value.

# Extracted Details
- **Work Deconstruction**: Break jobs into smaller tasks and identify which parts AI can handle efficiently.
- **Training AI**: Better outputs come from clear instructions, examples, and iteration.
- **AI as a Multiplier**: One person using AI effectively can increase output significantly.
- **Bias Toward Action**: Learning by doing is more effective than waiting for certainty.
- **The Power of the Question**: Prompt quality strongly shapes output quality.

# Key Takeaways
- AI creates the most value when used to redesign work rather than simply speed up existing habits.
- Prompting, iteration, and task framing are becoming core practical skills.

# Actionable Tips
- Pick one repetitive task and test whether AI can complete the first draft.
- Improve results by refining prompts with structure, examples, and constraints.
```

### What happens next

When this file is placed into `pending/` or `pending/md/`:

1. GitHub Actions runs the ingestion workflow
2. `process_notes.py` validates the frontmatter and sections
3. A new page is created in Notion
4. Frontmatter fields are mapped to database properties
5. The body content is published as formatted Notion blocks

### Result in Notion

The workflow will create:

* a database item with:

  * **Name** = `How to win with AI in 2026`
  * **Category** = `AI/LLM`
  * **Created At** = `2026-04-03`
  * **Status** = `Not started`
  * **Tag** = `ai-strategy`, `productivity`, `career-growth`, `automation`

* a page body containing:

  * `Knowledge Summary`
  * `Extracted Details`
  * optional `Key Takeaways`
  * optional `Actionable Tips`

### Required frontmatter

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

The workflow uses a controlled category list:

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

## Notion database mapping

The workflow is designed for a Notion database with these properties:

* **Name**
* **Category**
* **Created At**
* **Status**
* **Tag**

Markdown to Notion mapping:

* `title` -> **Name**
* `category` -> **Category**
* `created_at` -> **Created At**
* `status` -> **Status**
* `tags` -> **Tag**

The `filename` field is used for workflow handling and logging only.

## What the ingestion script does

`process_notes.py` is responsible for:

* scanning Markdown files from `pending/` and `pending/md/`
* parsing YAML frontmatter and body sections
* validating required fields and sections
* creating a page in the target Notion database
* converting content into Notion blocks
* preserving supported inline formatting in page content
* moving successful files to `processed/`
* moving failed files to `failed/`
* writing results to `manifests/ingest_log.jsonl`
* skipping exact duplicates using a local content hash log

## Workflow behaviour

The GitHub Actions workflow:

1. checks out the repository
2. sets up Python
3. installs dependencies
4. runs `process_notes.py`
5. commits file movements and manifest updates

This gives you a simple intake-to-publish loop without any manual Notion entry work.

## Recommended operating model

1. Upload screenshot(s) to the Gem
2. Review the Markdown output
3. Save each note as a `.md` file
4. Place the files in `pending/md/`
5. Let GitHub Actions publish them to Notion

The design principle is simple:

**interpret once, publish deterministically**

## Common issues

### Notion API returns `object_not_found`

Usually this means one of the following:

* the database ID is incorrect
* the integration does not have access to the database
* a page or view ID was used instead of the database ID

### Formatting does not appear correctly in Notion

Notion does not interpret raw Markdown markers automatically through the API. Inline formatting such as bold must be converted into Notion rich text annotations during ingestion.

### A file is skipped unexpectedly

It may already have been ingested and logged as a duplicate based on its content hash.

## Limitations

This project is intentionally narrow in scope:

* designed for screenshot-derived Markdown notes
* not a full general-purpose Markdown importer
* duplicate detection is local-log based
* formatting support is practical rather than full Markdown parity

## Future improvements

Possible enhancements include:

* richer inline Markdown support
* link parsing
* duplicate detection against Notion itself
* malformed note repair path
* stronger category and tag normalisation
* batch QA reporting

## Status

End-to-end workflow tested successfully:

**Gem -> GitHub -> Notion**

## License

Add a license here if you plan to make the repository public.
