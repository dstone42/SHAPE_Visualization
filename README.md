# SHAPE Metadata Pipeline

This workspace now treats SHAPE source metadata as data, not as hand-authored HTML.

## Project notes

Important architecture and handoff context lives in `docs/PROJECT_NOTES.md`.

That file captures the current decision points, the two portal distinction, source-of-truth files, generated files, local dependencies, and move/copy notes.

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

Without source-specific configuration, the pipeline uses the reviewed registry in `data/reviewed_registry.json` and leaves the observed/imported layers empty.

This keeps the workspace runnable while requiring live sources or explicit snapshots for observed/imported data.

## Run

```bash
./export.sh
```

Or:

```bash
python3 -m shape_metadata --root .
```

## Manual registry editor

The reviewed registry is still stored in `data/reviewed_registry.json`, but there is now a local editor for it:

```bash
python3 -m shape_metadata.manual_editor --root .
```

That starts a small local server for the editor at `http://127.0.0.1:8765`.

The editor:

- loads and saves `data/reviewed_registry.json`
- keeps the JSON schema the pipeline already expects
- shows spreadsheet and database context side-by-side when those inputs are configured
- lets you add missing manual entries from the merged upstream source list

## Real source integration

### Observed metadata

Supported modes:

- `SHAPE_OBSERVED_SNAPSHOT=/path/to/file.json`
- `SHAPE_MSSQL_USER=...` and `SHAPE_MSSQL_PASSWORD=...`

If the SQL Server credentials are set, the loader connects to the `SHAPE` database on host `HCI-DB`
by default and reads schema-level documentation rows from `adm.shapeDoc`.

Expected columns in `adm.shapeDoc`:

- `schema`
- `table`
- `column`
- `description`
- `updated_at`

For now, the loader only uses rows where `table` and `column` are null, which treats each schema row as
source-level documentation. Override the defaults with:

- `SHAPE_MSSQL_HOST`
- `SHAPE_MSSQL_DATABASE`
- `SHAPE_MSSQL_TABLE`
- `SHAPE_MSSQL_DRIVER`
- `SHAPE_MSSQL_DRIVER_PATH`
- `SHAPE_MSSQL_ENCRYPT`
- `SHAPE_MSSQL_TRUST_SERVER_CERTIFICATE`

### Imported metadata

Supported modes:

- `SHAPE_IMPORTED_SNAPSHOT=/path/to/file.json`
- `SHAPE_IMPORTED_SNAPSHOT=/path/to/file.xlsx`
- `BOX_JWT_CONFIG_PATH=/path/to/shape_box.json` and `BOX_FILE_ID=...`

The import layer now expects the spreadsheet in `.xlsx` form. When Box is configured, the pipeline tries to refresh from Box first. If the live import parses successfully, it atomically updates `SHAPE_IMPORTED_SNAPSHOT` and uses the refreshed workbook. If Box refresh fails, the pipeline warns and falls back to the cached snapshot when one exists. Keeping the Box app config as JSON is recommended because it preserves the multiline private key and nested Box app settings without `.env` escaping.

### Local environment variables

If a `.env` file exists at the workspace root, the pipeline loads it automatically before reading inputs.

Cached snapshot:

```dotenv
SHAPE_IMPORTED_SNAPSHOT=data/inputs/Metrics captured by database_ACTIVE.xlsx
```

Live Box refresh:

```dotenv
BOX_JWT_CONFIG_PATH=config/shape_box.json
BOX_FILE_ID=1438504655299
```

Database connection settings:

```dotenv
SHAPE_MSSQL_HOST=HCI-DB
SHAPE_MSSQL_DATABASE=SHAPE
SHAPE_MSSQL_DRIVER=/opt/homebrew/lib/libmsodbcsql.18.dylib
SHAPE_MSSQL_ENCRYPT=no
SHAPE_MSSQL_TRUST_SERVER_CERTIFICATE=yes
SHAPE_MSSQL_USER=
SHAPE_MSSQL_PASSWORD=
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
