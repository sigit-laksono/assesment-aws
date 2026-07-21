---
name: aws-assessment-tool
description: "Use when the user wants to run, extend, or debug this repo's AWS Account Assessment Tool — a Python CLI that inventories AWS resources across 27 services plus billing, and generates an HTML + JSON report. Covers how to invoke it (interactive wizard vs non-interactive CLI), its data flow, file layout, and output naming so an agent can operate or modify it correctly without re-reading the whole codebase."
---

# AWS Account Assessment Tool

A Python tool that connects to one AWS account, inventories resources across 27 services plus Cost Explorer billing, and produces:

1. A styled, filterable **HTML report** (`output/assessment_report_{customer_slug}_{timestamp}.html`)
2. A raw **JSON data dump** (`output/assessment_data_{customer_slug}_{timestamp}.json`) for downstream automation/AI use

It is **pure data collection** — no recommendations, no "cost optimization" scoring. It reports what exists and what it costs; it does not suggest what to do about it.

This file is a plain, agent-agnostic Markdown skill — no proprietary format. Any AI coding agent (Claude Code, Kiro, Cursor, Codex/Aider via AGENTS.md, etc.) can read it directly; there's nothing here tied to one tool's conventions.

## How to run it

There are two entry points — pick based on whether the caller is a human at a terminal or an automation/agent.

### Interactive (human-friendly wizard)

```bash
python aws_assessment.py
```

Prompts for customer name, AWS region, then shows a checklist of services (grouped Compute/Storage/Database/Networking/Security/Operations/Integration) with sensible defaults pre-checked. No CLI flags to remember.

### Non-interactive (automation / AI agent — prefer this one)

```bash
python cli.py --all --customer "PT Contoh Sejahtera" --region ap-southeast-3
python cli.py --services ec2,s3,rds --customer "Acme Corp"
python cli.py --list-services                     # print all valid service codes
python cli.py --all --customer "Acme" --no-report  # JSON only, skip HTML
python cli.py --all --customer "Acme" --output ./output/scan-juli  # custom output dir
```

`--customer` and `--services`/`--all` are the only things that matter for a normal run. `--region` defaults to `ap-southeast-1` — always pass the real region explicitly, since resources outside the target region won't be seen (this tool does not multi-region scan).

**Important:** `--customer` also drives the output filename (see below) — always pass a real, distinguishing customer name, not the default, or files from different assessments become impossible to tell apart.

### Credentials

Ambient AWS credential chain via boto3 (`boto3.Session(region_name=...)`) — environment variables, `~/.aws/credentials`, or an attached IAM role. **There is no `.env` file and no hardcoded key support** — if you see `.env` mentioned in `.kiro/steering/assesment.md`, that steering doc is stale/aspirational and does not reflect the actual code; do not implement `.env` loading based on it.

## Output file naming

Both outputs are slugified from the customer name (`utils/helpers.py::slugify` — lowercased, non-alphanumeric collapsed to `_`) plus a timestamp, so files from different customers/runs sort and grep cleanly:

```
output/assessment_data_pt_contoh_sejahtera_20260720_203056.json
output/assessment_report_pt_contoh_sejahtera_20260720_203044.html
```

`output/` is gitignored — nothing generated there is meant to be committed.

## Architecture / where to look

```
aws_assessment.py         # AWSAssessment class — orchestrator (interactive entry point + main())
cli.py                    # non-interactive argparse entry point, imports AWSAssessment
core/
  engine.py                # AssessmentEngine base class — boto3 session, assessment_data dict, save_data()
  reporter/
    html_report.py          # generate_html_report() — loads template, fills placeholders, writes output/*.html
    section_summary.py       # renders Executive Summary "Summary Services" table rows
    section_inventory.py     # renders one HTML block per AWS service (25+ hand-written blocks, one per service)
collectors/                # one function per service, each mutates assessment_data['services'][code]
  compute.py, storage.py, database.py, network.py, security.py, integration.py, operations.py, billing.py
utils/
  interactive.py            # SERVICE_GROUPS + run_interactive_setup() wizard
  helpers.py                 # DecimalEncoder (JSON), slugify()
templates/
  report_template.html      # static HTML shell — sidebar nav, header, section containers, {{PLACEHOLDER}} slots
  report_styles.css          # design tokens (accent orange #ED7D31, Archivo font) + all component styles
  report_scripts.js          # client-side: category filter, live search, per-table pagination, sortable columns, scroll-spy nav
```

### Data flow

1. `AWSAssessment.run_assessment(selected_services)` (in `aws_assessment.py`):
   validates credentials → `get_billing_data()` → runs each selected collector from `self.inventory_map` (each collector writes into `assessment_data['services'][code]`) → `self.save_data()` writes the JSON.
2. `AWSAssessment.generate_reports()` calls `generate_html_report(assessment_data, ...)`, which:
   loads `templates/report_template.html`, inlines `report_styles.css`/`report_scripts.js`, does literal `{{PLACEHOLDER}}` string replacement (not Jinja2 — plain `str.replace`), and delegates per-section HTML generation to `section_summary.py` / `section_inventory.py`.

### Adding a new AWS service to inventory

Touch **four** places, in this order:
1. `collectors/<category>.py` — write `inventory_<service>(session, assessment_data)`, store results at `assessment_data['services']['<code>']`
2. `aws_assessment.py` — import it and add `'<code>': inventory_<service>` to `self.inventory_map`
3. `cli.py` — add `'<code>'` to `ALL_SERVICES`
4. `core/reporter/section_inventory.py` — add an `if '<code>' in assessment_data['services']:` block rendering its table
   (optionally `utils/interactive.py` `SERVICE_GROUPS` if it should be selectable/visible in the interactive wizard — note IAM currently is *not* in `SERVICE_GROUPS`, only reachable via `cli.py --services iam` or `--all`, which is a known gap, not a bug to silently "fix" without being asked)

### Report template mechanics — do not assume Jinja2

`templates/report_template.html` uses literal `{{UPPER_CASE}}` tokens replaced via `str.replace()` in `html_report.py` — there is no template engine, no loops/conditionals in the HTML itself. Repeated rows (tables) are built by string-concatenation in the `section_*.py` files and injected as one big HTML blob per placeholder. When editing the template, preserve this contract: every `{{PLACEHOLDER}}` referenced in `html_report.py`'s `replacements` dict (or a later explicit `.replace()` call) must still exist exactly once in the HTML.

### JS is real, not a mockup

`report_scripts.js` implements working client-side search/category-filter/sort/pagination/scroll-spy directly against the rendered static HTML (no framework, no build step). If asked to restyle the report visually, change CSS/HTML only — this JS does not need to change and should not be replaced with a component framework.

## What this tool intentionally does NOT do

- No cost-optimization suggestions, waste findings, or "recommended actions" — that feature (`collectors/cost_optimization.py`, `utils/pricing.py`, `core/reporter/section_cost.py`) was deliberately removed. Do not re-add a suggestion/recommendation engine unless explicitly asked.
- No multi-region scanning in one run — region is a single required input.
- No credential storage of any kind — always the ambient boto3 chain.
