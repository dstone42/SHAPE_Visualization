# SHAPE Metadata Backlog

This file is the local stand-in for issue tracking until the project is connected to a hosted git remote with real issues.

## What Is Working Now

- The pipeline entrypoint runs with `./export.sh` or `python3 -m shape_metadata --root .`.
- The metadata schema is defined and normalized in `shape_metadata/models.py`.
- The pipeline loads three layers:
  - observed metadata
  - imported reference metadata
  - reviewed registry
- The merge rules are implemented:
  - observed/database wins for structural fields
  - reviewed registry wins for descriptive fields
- Validation warnings are generated for common drift and review conditions.
- The generated site is data-driven and derives filter options from the dataset.
- Tests cover artifact generation, warning generation, and data-driven filters.

## Placeholder Or Partial Pieces

- The database adapter is generic and currently supports:
  - a JSON snapshot
  - a simple SQLite table shape
- The real SHAPE database introspection query has not been implemented yet.
- The Box import path is scaffolded, but it still needs:
  - approval to use the Box SDK in the runtime environment
  - working runtime credentials and the actual file ID
  - final wiring from the Box download step into the pipeline
- Codebook ingestion is only a simple structured merge right now.
- There is no hosted issue tracker, remote repository, CI, or scheduled job yet.
- The reviewed registry still contains seeded sample content based on the initial HTML and sample placeholders.

## Priority Issues

### Issue 1: Wire up the real SHAPE database source

Status: Open

Goal:
Replace the sample or SQLite observed loader with the real SHAPE database connection and source discovery logic.

Definition of done:
- The pipeline can connect to the actual SHAPE database.
- It can enumerate source-level records.
- It can infer available years, geography levels, and source systems from the real schema.
- `artifacts/observed_metadata.json` is produced from live data instead of sample files.

## Issue 2: Map the Box spreadsheet into the imported metadata layer

Status: In progress

Goal:
Use the Box SDK path with the real spreadsheet and normalize its columns into `SourceRecord`.

Current status:
- The pipeline can now parse the real `.xlsx` workbook structure directly.
- The workbook-to-`SourceRecord` mapping is implemented for the current spreadsheet layout.
- The remaining blocker is Box SDK approval and runtime authentication, so the automatic download step is still pending.

Definition of done:
- The runtime can authenticate to Box.
- The spreadsheet is downloaded automatically.
- Source IDs are mapped consistently to the reviewed registry.
- Imported domains, descriptions, notes, and document references appear in `artifacts/imported_metadata.json`.

## Issue 3: Replace seeded reviewed data with the real reviewed registry

Status: Open

Goal:
Turn `data/reviewed_registry.json` into the real human-maintained metadata registry.

Definition of done:
- Each real SHAPE source has a reviewed entry.
- Descriptive fields are curated deliberately instead of copied from sample data.
- Domain names are standardized.
- Review dates and confidence values are meaningful.

## Issue 4: Add source-to-source ID mapping rules

Status: Open

Goal:
Handle cases where the database, spreadsheet, and codebooks use different naming conventions.

Definition of done:
- One mapping layer translates source names into canonical `source_id` values.
- Mismatched aliases no longer create duplicate sources.
- Validation warnings clearly surface unmapped records.

## Issue 5: Improve validation rules for real-world drift

Status: Open

Goal:
Expand the warning system beyond the current basic checks.

Definition of done:
- Validation catches missing frequencies, empty domains, suspicious year gaps, and missing geographic coverage.
- Validation severity is meaningful enough for a review workflow.
- The HTML validation report stays readable with larger source counts.

## Issue 6: Set up publishing and scheduled refresh

Status: Open

Goal:
Run the pipeline on a schedule and publish the generated output from a repeatable process.

Definition of done:
- A scheduled job runs the pipeline in the right environment.
- Credentials are supplied securely.
- Generated artifacts are written to a known output location.
- The published HTML is updated from scheduled runs, not manual rebuilding alone.

## Issue 7: Move from local backlog to hosted issues

Status: Open

Goal:
Connect this repo to GitHub or another hosted git platform and migrate this file into real issues.

Definition of done:
- A remote repository exists.
- This repo has a remote configured.
- Each priority issue above exists as a hosted issue with labels and assignee/status tracking.

## Suggested Workflow For Now

- Update `data/reviewed_registry.json` when you want to change curated metadata.
- Update sample input files only for local simulation and development.
- Rebuild with `./export.sh`.
- Review:
  - `artifacts/reviewed_registry_draft.json`
  - `artifacts/validation_report.html`
  - `site/index.html`
