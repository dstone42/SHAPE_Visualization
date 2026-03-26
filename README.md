# SHAPE Metadata Pipeline

This workspace now treats SHAPE source metadata as data, not as hand-authored HTML.

## What it produces

Running the pipeline generates:

- `artifacts/observed_metadata.json`
- `artifacts/imported_metadata.json`
- `artifacts/reviewed_registry_draft.json`
- `artifacts/validation_report.json`
- `artifacts/validation_report.html`
- `site/index.html`
- `site/styles.css`
- `site/app.js`
- `site/metadata.json`

## Default behavior

Without credentials or source-specific configuration, the pipeline uses the seeded sample inputs in `data/inputs/` and the reviewed registry in `data/reviewed_registry.json`.

This makes the workspace immediately runnable while keeping the ingestion layer pluggable.

## Run

```bash
./export.sh
```

Or:

```bash
python3 -m shape_metadata --root .
```

## Real source integration

### Observed metadata

Supported modes:

- `SHAPE_OBSERVED_SNAPSHOT=/path/to/file.json`
- `SHAPE_SQLITE_PATH=/path/to/file.sqlite`

If `SHAPE_SQLITE_PATH` is set, the loader expects a table with rows that can be grouped by source:

- `source_id`
- `display_name` (optional)
- `year` (optional)
- `geographic_level` (optional)
- `source_system` (optional)

It defaults to table `shape_metadata_inventory`. Override with `SHAPE_SQLITE_TABLE`.

### Imported metadata

Supported modes:

- `SHAPE_IMPORTED_SNAPSHOT=/path/to/file.json`
- `SHAPE_IMPORTED_SNAPSHOT=/path/to/file.xlsx`
- `BOX_DEVELOPER_TOKEN=...` and `BOX_FILE_ID=...`

The import layer now expects the spreadsheet in `.xlsx` form. The Box adapter downloads an Excel workbook by default, or JSON if `BOX_FILE_FORMAT=json` is set.

### Local environment variables

If a `.env` file exists at the workspace root, the pipeline loads it automatically before reading inputs.

Example:

```dotenv
SHAPE_IMPORTED_SNAPSHOT=data/inputs/Metrics captured by database_ACTIVE.xlsx
```

### Optional codebook import

Set `SHAPE_CODEBOOK_SNAPSHOT=/path/to/file.json` to merge codebook-derived fields into the imported reference layer.

## Canonical review workflow

1. The pipeline loads observed metadata from the database layer.
2. It loads imported reference metadata from spreadsheet and optional codebook inputs.
3. It reconciles those records against `data/reviewed_registry.json`.
4. It writes a draft canonical registry plus a validation report.
5. It publishes the generated HTML site.

## Notes

- The reviewed registry remains the human-edited source for descriptive and interpretive fields.
- Database-derived structural facts win for years, geography levels, and source systems.
- The site builds its filters dynamically from the published dataset.
- Share or archive the generated `site/` directory when you need to hand off the web output.
