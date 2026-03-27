from __future__ import annotations

import io
import json
import os
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zipfile import ZipFile
import xml.etree.ElementTree as ET

from .models import SourceRecord, normalize_years

XLSX_NS = {
    "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "rel": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}

SOURCE_ALIASES: dict[str, tuple[str, str]] = {
    "acs": ("acs", "ACS"),
    "apcd": ("apcd", "APCD"),
    "brffs": ("brfss", "BRFSS"),
    "brfss": ("brfss", "BRFSS"),
    "ccsg": ("ccsg", "CCSG"),
    "ccsg clinical trial hci patients": ("ccsg", "CCSG"),
    "chas": ("chas", "CHAS"),
    "chas 1": ("chas", "CHAS"),
    "cif": ("cif", "CIF"),
    "cms": ("cms", "CMS"),
    "doh": ("doh", "DOH"),
    "dun and bradstreet": ("dun-bradstreet", "Dun & Bradstreet"),
    "dun bradstreet": ("dun-bradstreet", "Dun & Bradstreet"),
    "edw": ("edw", "EDW"),
    "edw no substantial data available": ("edw", "EDW"),
    "epa": ("epa", "EPA"),
    "fcc": ("fcc", "FCC"),
    "hints": ("hints", "HINTS"),
    "hpv vaccination coalition": ("hpv-vaccination-coalition", "HPV Vaccination Coalition"),
    "internal hci": ("internal-hci-data", "Internal HCI Data"),
    "internal hci data": ("internal-hci-data", "Internal HCI Data"),
    "internal hci dataset": ("internal-hci-data", "Internal HCI Data"),
    "hci": ("internal-hci-data", "Internal HCI Data"),
    "nhis": ("nhis", "NHIS"),
    "ocoe": ("ocoe", "OCOE"),
    "seer": ("seer", "SEER"),
    "shape derived": ("shape-derived", "SHAPE-derived"),
    "shape-derived": ("shape-derived", "SHAPE-derived"),
    "ucr": ("ucr", "UCR"),
    "ucr utah only": ("ucr", "UCR"),
}

FOOTNOTE_MARKER_PATTERN = re.compile(r"(\*+)$")
YEAR_RANGE_PATTERN = re.compile(r"\b(19\d{2}|20\d{2})\s*[-–]\s*(19\d{2}|20\d{2})\b")
YEAR_PATTERN = re.compile(r"\b(19\d{2}|20\d{2})\b")
IGNORED_SOURCE_LABELS = {
    "sources currently in shape",
    "sources planned or active work in shape",
    "sources to be determined",
}
TITLE_CASE_SOURCE_NAMES = {
    "census": "Census",
    "rurality": "Rurality",
}


@dataclass
class ImportedRecordAccumulator:
    source_id: str
    display_name: str
    domains: set[str] = field(default_factory=set)
    geographic_levels: set[str] = field(default_factory=set)
    available_years: set[int] = field(default_factory=set)
    notes: set[str] = field(default_factory=set)
    caveats: set[str] = field(default_factory=set)
    year_notes: set[str] = field(default_factory=set)
    source_documents: list[dict[str, Any]] = field(default_factory=list)


def load_observed_records(root: Path) -> list[SourceRecord]:
    snapshot_path = os.environ.get("SHAPE_OBSERVED_SNAPSHOT")
    if snapshot_path:
        return _load_json_records(_resolve_input_path(root, snapshot_path))

    if os.environ.get("SHAPE_MSSQL_USER") and os.environ.get("SHAPE_MSSQL_PASSWORD"):
        return _load_mssql_shape_doc_records()

    return _load_json_records(root / "data" / "inputs" / "observed_sample.json")


def load_imported_records(root: Path) -> list[SourceRecord]:
    snapshot_path = os.environ.get("SHAPE_IMPORTED_SNAPSHOT")
    if snapshot_path:
        imported_records = _load_imported_snapshot(_resolve_input_path(root, snapshot_path))
    elif os.environ.get("BOX_DEVELOPER_TOKEN") and os.environ.get("BOX_FILE_ID"):
        imported_records = _load_box_records()
    else:
        imported_records = _load_json_records(root / "data" / "inputs" / "imported_sample.json")

    codebook_path = os.environ.get("SHAPE_CODEBOOK_SNAPSHOT")
    if codebook_path:
        codebook_records = _load_json_records(_resolve_input_path(root, codebook_path))
        imported_records = _merge_reference_records(imported_records, codebook_records)

    return imported_records


def load_reviewed_registry(root: Path) -> list[SourceRecord]:
    return _load_json_records(root / "data" / "reviewed_registry.json")


def load_runtime_environment(root: Path) -> None:
    env_path = root / ".env"
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        os.environ[key] = _strip_env_value(value)


def _load_imported_snapshot(path: Path) -> list[SourceRecord]:
    if path.suffix.lower() == ".xlsx":
        return _load_xlsx_records(path)
    return _load_json_records(path)


def _load_json_records(path: Path) -> list[SourceRecord]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [SourceRecord.from_dict(record) for record in payload]


def _load_mssql_shape_doc_records() -> list[SourceRecord]:
    try:
        import pyodbc
    except ImportError as exc:
        raise RuntimeError(
            "The SQL Server adapter requires the `pyodbc` package to be installed."
        ) from exc

    connection = _connect_mssql(pyodbc)
    try:
        cursor = connection.cursor()
        table_name = os.environ.get("SHAPE_MSSQL_TABLE", "adm.shapeDoc")
        query = f"""
            SELECT
                [schema] AS schema_name,
                [table] AS table_name,
                [column] AS column_name,
                [description],
                [updated_at]
            FROM {table_name}
            WHERE [schema] IS NOT NULL
              AND [table] IS NULL
              AND [column] IS NULL
        """
        rows = cursor.execute(query).fetchall()
        columns = [column[0] for column in cursor.description]
        payload = [dict(zip(columns, row)) for row in rows]
        return _shape_doc_rows_to_records(payload)
    finally:
        connection.close()


def _connect_mssql(pyodbc_module: Any) -> Any:
    errors: list[str] = []
    for driver in _mssql_driver_candidates(pyodbc_module):
        try:
            return pyodbc_module.connect(_build_mssql_connection_string(driver))
        except pyodbc_module.Error as exc:
            errors.append(f"{driver}: {exc}")

    joined = "\n".join(errors) if errors else "No SQL Server ODBC driver candidates were available."
    raise RuntimeError(
        "Unable to connect to SQL Server with the configured ODBC drivers.\n"
        f"Tried:\n{joined}"
    )


def _mssql_driver_candidates(pyodbc_module: Any) -> list[str]:
    candidates: list[str] = []
    seen: set[str] = set()

    def add(candidate: str | None) -> None:
        if not candidate:
            return
        normalized = candidate.strip()
        if not normalized or normalized in seen:
            return
        seen.add(normalized)
        candidates.append(normalized)

    add(os.environ.get("SHAPE_MSSQL_DRIVER"))
    add(os.environ.get("SHAPE_MSSQL_DRIVER_PATH"))

    available_drivers = pyodbc_module.drivers()
    preferred_name = "ODBC Driver 18 for SQL Server"
    if preferred_name in available_drivers:
        add(preferred_name)
    for driver in available_drivers:
        if "sql server" in driver.casefold():
            add(driver)

    add("/opt/homebrew/lib/libmsodbcsql.18.dylib")
    return candidates


def _build_mssql_connection_string(driver: str) -> str:
    host = os.environ.get("SHAPE_MSSQL_HOST", "HCI-DB")
    database = os.environ.get("SHAPE_MSSQL_DATABASE", "SHAPE")
    user = os.environ["SHAPE_MSSQL_USER"]
    password = os.environ["SHAPE_MSSQL_PASSWORD"]
    encrypt = os.environ.get("SHAPE_MSSQL_ENCRYPT", "no")
    trust_server_certificate = os.environ.get("SHAPE_MSSQL_TRUST_SERVER_CERTIFICATE", "yes")

    return (
        f"DRIVER={_format_mssql_driver(driver)};"
        f"SERVER={host};"
        f"DATABASE={database};"
        f"UID={user};"
        f"PWD={password};"
        f"Encrypt={encrypt};"
        f"TrustServerCertificate={trust_server_certificate};"
    )


def _format_mssql_driver(driver: str) -> str:
    stripped = driver.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        return stripped
    return f"{{{stripped}}}"


def _shape_doc_rows_to_records(rows: list[dict[str, Any]]) -> list[SourceRecord]:
    records: dict[str, dict[str, Any]] = {}
    for row in rows:
        schema_name = (row.get("schema_name") or row.get("schema") or "").strip()
        table_name = row.get("table_name") or row.get("table")
        column_name = row.get("column_name") or row.get("column")
        description = (row.get("description") or "").strip()
        if not schema_name or table_name is not None or column_name is not None:
            continue

        source_id, display_name = _normalize_source_reference(schema_name)
        display_name = _database_display_name(source_id, schema_name, display_name)
        current = records.setdefault(
            source_id,
            {
                "source_id": source_id,
                "display_name": display_name,
                "source_systems": ["MS SQL Server"],
            },
        )
        if description:
            current["short_description"] = description

        updated_at = _format_timestamp(row.get("updated_at"))
        if updated_at:
            current["last_observed_at"] = updated_at

    return [SourceRecord.from_dict(record) for _, record in sorted(records.items())]


def _format_timestamp(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    if isinstance(value, date):
        return value.isoformat()
    return str(value).strip()


def _load_box_records() -> list[SourceRecord]:
    try:
        from boxsdk import Client, OAuth2
    except ImportError as exc:
        raise RuntimeError(
            "The Box adapter requires the `boxsdk` package to be installed."
        ) from exc

    token = os.environ["BOX_DEVELOPER_TOKEN"]
    file_id = os.environ["BOX_FILE_ID"]

    auth = OAuth2(None, None, access_token=token)
    client = Client(auth)
    stream = io.BytesIO()
    client.file(file_id).download_to(stream)
    stream.seek(0)

    if os.environ.get("BOX_FILE_FORMAT", "xlsx").lower() == "json":
        payload = json.loads(stream.read().decode("utf-8"))
        return [SourceRecord.from_dict(record) for record in payload]

    return _load_xlsx_records_from_bytes(stream.getvalue())


def _merge_reference_records(
    imported_records: list[SourceRecord], codebook_records: list[SourceRecord]
) -> list[SourceRecord]:
    merged = {record.source_id: record for record in imported_records}
    for codebook_record in codebook_records:
        existing = merged.get(codebook_record.source_id)
        if not existing:
            merged[codebook_record.source_id] = codebook_record
            continue
        existing.notes = sorted(set(existing.notes + codebook_record.notes), key=str.casefold)
        existing.caveats = sorted(
            set(existing.caveats + codebook_record.caveats), key=str.casefold
        )
        existing.source_documents = existing.source_documents + codebook_record.source_documents
    return list(merged.values())


def _resolve_input_path(root: Path, raw_path: str) -> Path:
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = root / path
    return path


def _strip_env_value(value: str) -> str:
    stripped = value.strip()
    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in {"'", '"'}:
        return stripped[1:-1]
    return stripped


def _load_xlsx_records(path: Path) -> list[SourceRecord]:
    return _load_xlsx_records_from_bytes(path.read_bytes())


def _load_xlsx_records_from_bytes(payload: bytes) -> list[SourceRecord]:
    workbook = _read_xlsx_workbook(payload)
    records: dict[str, ImportedRecordAccumulator] = {}
    footnotes, included_source_ids = _parse_current_state_sheet(
        workbook.get("Current state of SHAPE", []),
        records,
    )
    _parse_domains_by_source_sheet(workbook.get("Domains by data source", []), records, included_source_ids)
    _parse_source_tabs(workbook, records, footnotes, included_source_ids)
    return [_accumulator_to_record(accumulator) for _, accumulator in sorted(records.items())]


def _read_xlsx_workbook(payload: bytes) -> dict[str, list[dict[str, str]]]:
    workbook: dict[str, list[dict[str, str]]] = {}
    with ZipFile(io.BytesIO(payload)) as archive:
        shared_strings = _read_shared_strings(archive)
        workbook_xml = ET.fromstring(archive.read("xl/workbook.xml"))
        rels_xml = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        rel_map = {rel.attrib["Id"]: rel.attrib["Target"] for rel in rels_xml}
        sheets_node = workbook_xml.find("main:sheets", XLSX_NS)

        for sheet in list(sheets_node) if sheets_node is not None else []:
            name = sheet.attrib.get("name", "")
            rel_id = sheet.attrib.get(f"{{{XLSX_NS['rel']}}}id")
            target = rel_map.get(rel_id, "")
            if not name or not target:
                continue
            sheet_xml = ET.fromstring(archive.read(f"xl/{target}"))
            workbook[name] = _read_sheet_rows(sheet_xml, shared_strings)
    return workbook


def _read_shared_strings(archive: ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []

    root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    values: list[str] = []
    for item in root.findall("main:si", XLSX_NS):
        parts = [node.text or "" for node in item.iterfind(".//main:t", XLSX_NS)]
        values.append("".join(parts))
    return values


def _read_sheet_rows(sheet_xml: ET.Element, shared_strings: list[str]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for row in sheet_xml.findall(".//main:sheetData/main:row", XLSX_NS):
        values: dict[str, str] = {}
        for cell in row.findall("main:c", XLSX_NS):
            column = _column_letters(cell.attrib.get("r", ""))
            text = _extract_cell_value(cell, shared_strings)
            if column and text:
                values[column] = _normalize_cell_text(text)
        rows.append(values)
    return rows


def _column_letters(cell_ref: str) -> str:
    letters = []
    for char in cell_ref:
        if char.isalpha():
            letters.append(char)
        else:
            break
    return "".join(letters)


def _extract_cell_value(cell: ET.Element, shared_strings: list[str]) -> str:
    cell_type = cell.attrib.get("t")
    value_node = cell.find("main:v", XLSX_NS)

    if cell_type == "s" and value_node is not None:
        return shared_strings[int(value_node.text or "0")]

    if cell_type == "inlineStr":
        inline_node = cell.find("main:is", XLSX_NS)
        if inline_node is not None:
            return "".join(node.text or "" for node in inline_node.iterfind(".//main:t", XLSX_NS))

    if value_node is not None:
        return value_node.text or ""

    return ""


def _normalize_cell_text(value: str) -> str:
    text = value.replace("\r\n", "\n").replace("\r", "\n").strip()
    lines = [" ".join(part for part in line.split()) for line in text.split("\n")]
    collapsed = "\n".join(line for line in lines if line)
    return collapsed.strip()


def _parse_current_state_sheet(
    rows: list[dict[str, str]],
    records: dict[str, ImportedRecordAccumulator],
) -> tuple[dict[str, str], set[str]]:
    footnotes: dict[str, str] = {
        row.get("A", ""): row.get("B", "")
        for row in rows[1:]
        if row.get("A", "").startswith("*") and row.get("B", "")
    }
    current_domain = ""
    included_source_ids: set[str] = set()

    for row in rows[1:]:
        marker = row.get("A", "")
        note = row.get("B", "")
        if marker.startswith("*") and note:
            continue

        measure = row.get("B", "")
        if not measure:
            continue

        if not any(row.get(column, "") for column in ("C", "D", "E", "F")):
            current_domain = measure
            continue

        if not current_domain:
            continue

        context = f"{current_domain} / {measure}"
        for source_label, marker in _split_source_labels(row.get("D", "")):
            source_id, display_name = _normalize_source_reference(source_label)
            accumulator = _get_imported_record(records, source_id, display_name)
            accumulator.domains.add(current_domain)
            included_source_ids.add(source_id)
            if marker and marker in footnotes:
                accumulator.caveats.add(f"{context}: {footnotes[marker]}")

    return footnotes, included_source_ids


def _parse_domains_by_source_sheet(
    rows: list[dict[str, str]],
    records: dict[str, ImportedRecordAccumulator],
    included_source_ids: set[str],
) -> None:
    if not rows:
        return

    header_row = rows[0]
    source_columns: dict[str, tuple[str, str]] = {}
    for column, label in header_row.items():
        if column == "A" or not label:
            continue
        source_id, display_name = _normalize_source_reference(label)
        if included_source_ids and source_id not in included_source_ids:
            continue
        source_columns[column] = (source_id, display_name)

    current_domain = ""
    for row in rows[1:]:
        label = row.get("A", "")
        if not label:
            continue

        values = {column: row.get(column, "") for column in source_columns}
        nonempty_values = [value for value in values.values() if value]

        if label == "Lowest geographic level":
            for column, value in values.items():
                if not value:
                    continue
                accumulator = _get_imported_record(records, *source_columns[column])
                accumulator.geographic_levels.update(_parse_geographic_levels(value))
            continue

        if label == "Has PHI?":
            for column, value in values.items():
                if value.lower() == "yes":
                    accumulator = _get_imported_record(records, *source_columns[column])
                    accumulator.notes.add("Workbook marks this source as containing PHI.")
            continue

        if label == "Required applications?":
            for column, value in values.items():
                if value.lower() == "yes":
                    accumulator = _get_imported_record(records, *source_columns[column])
                    accumulator.notes.add("Workbook marks this source as requiring an application.")
            continue

        if not nonempty_values:
            current_domain = label
            continue

        if not current_domain:
            continue

        for column, value in values.items():
            if not value or value.lower() == "no":
                continue
            accumulator = _get_imported_record(records, *source_columns[column])
            accumulator.domains.add(current_domain)
            if value.lower() != "yes":
                accumulator.geographic_levels.update(_parse_geographic_levels(value))


def _parse_source_tabs(
    workbook: dict[str, list[dict[str, str]]],
    records: dict[str, ImportedRecordAccumulator],
    footnotes: dict[str, str],
    included_source_ids: set[str],
) -> None:
    for sheet_name, rows in workbook.items():
        if sheet_name in {"Current state of SHAPE", "Domains by data source"}:
            continue
        if not rows:
            continue

        source_id, display_name = _normalize_source_reference(sheet_name)
        if included_source_ids and source_id not in included_source_ids:
            continue
        accumulator = _get_imported_record(records, source_id, display_name)
        accumulator.source_documents.append(
            {
                "name": f"{display_name} worksheet",
                "type": "spreadsheet",
                "worksheet": sheet_name,
            }
        )

        header_row = rows[0]
        header_map = {column: _normalize_label(value) for column, value in header_row.items()}
        base_column = _find_column(header_map, "base measure")
        years_column = _find_column(header_map, "years included")
        link_column = _find_column(header_map, "link")
        notes_column = _find_column(header_map, "notes")
        variable_column = _find_column(header_map, "variable name")
        question_column = _find_column(header_map, "how does the source answer the domain? (ie. question)")

        current_domain = ""
        current_measure = ""
        for row in rows[1:]:
            if not row:
                continue

            measure = row.get(base_column, "") if base_column else ""
            years_text = row.get(years_column, "") if years_column else ""
            link_text = row.get(link_column, "") if link_column else ""
            notes_text = row.get(notes_column, "") if notes_column else ""
            variable_text = row.get(variable_column, "") if variable_column else ""
            question_text = row.get(question_column, "") if question_column else ""

            extra_context = [value for column, value in row.items() if column not in header_map]
            extra_notes = [value for value in extra_context if value]

            if measure and not any([years_text, link_text, notes_text, variable_text, question_text, *extra_notes]):
                current_domain = measure
                current_measure = ""
                continue

            if measure:
                current_measure = measure
            if not current_measure:
                if years_text:
                    accumulator.year_notes.add(years_text)
                if notes_text:
                    accumulator.notes.add(notes_text)
                for note in extra_notes:
                    accumulator.notes.add(note)
                continue

            if current_domain:
                accumulator.domains.add(current_domain)

            parsed_years = _parse_years(years_text)
            accumulator.available_years.update(parsed_years)
            if years_text and not parsed_years:
                accumulator.year_notes.add(f"{current_measure}: {years_text}")
            elif years_text and any(token in years_text.lower() for token in ("cycle", "rolling", "window")):
                accumulator.year_notes.add(f"{current_measure}: {years_text}")

            if link_text:
                accumulator.source_documents.append(
                    {
                        "name": f"{display_name} reference",
                        "type": "reference",
                        "url": link_text,
                    }
                )

            if notes_text:
                accumulator.caveats.add(f"{current_measure}: {notes_text}")
            for note in extra_notes:
                accumulator.caveats.add(f"{current_measure}: {note}")

            for marker in _footnote_markers_from_text(question_text):
                if marker in footnotes:
                    accumulator.caveats.add(f"{current_measure}: {footnotes[marker]}")


def _find_column(header_map: dict[str, str], target: str) -> str | None:
    for column, label in header_map.items():
        if label == target:
            return column
    return None


def _normalize_label(value: str) -> str:
    return " ".join(value.replace("\n", " ").split()).casefold()


def _split_source_labels(value: str) -> list[tuple[str, str]]:
    labels: list[tuple[str, str]] = []
    for raw_label in value.split(","):
        cleaned = " ".join(raw_label.split()).strip()
        if not cleaned:
            continue
        if cleaned.casefold() in IGNORED_SOURCE_LABELS:
            continue
        marker_match = FOOTNOTE_MARKER_PATTERN.search(cleaned)
        marker = marker_match.group(1) if marker_match else ""
        label = cleaned[: -len(marker)].strip() if marker else cleaned
        labels.append((label, marker))
    return labels


def _normalize_source_reference(label: str) -> tuple[str, str]:
    normalized = _normalize_source_key(label)
    if normalized in SOURCE_ALIASES:
        return SOURCE_ALIASES[normalized]

    source_id = normalized.replace(" ", "-")
    display_name = " ".join(word.upper() if word.isupper() else word.capitalize() for word in label.split())
    return source_id, display_name


def _database_display_name(source_id: str, schema_name: str, fallback: str) -> str:
    normalized = _normalize_source_key(schema_name)
    if normalized in TITLE_CASE_SOURCE_NAMES:
        return TITLE_CASE_SOURCE_NAMES[normalized]
    if source_id == "internal-hci-data":
        return "Internal HCI Data"
    if "-" not in source_id:
        return schema_name.upper()
    return fallback


def _normalize_source_key(label: str) -> str:
    cleaned = _normalize_cell_text(label)
    cleaned = re.sub(r"\([^)]*\)", "", cleaned)
    cleaned = cleaned.replace("&", " and ")
    cleaned = cleaned.replace("/", " ")
    cleaned = cleaned.replace("-", " ")
    cleaned = FOOTNOTE_MARKER_PATTERN.sub("", cleaned)
    cleaned = re.sub(r"\b\d+\b$", "", cleaned)
    return " ".join(cleaned.split()).casefold()


def _get_imported_record(
    records: dict[str, ImportedRecordAccumulator],
    source_id: str,
    display_name: str,
) -> ImportedRecordAccumulator:
    accumulator = records.get(source_id)
    if accumulator is None:
        accumulator = ImportedRecordAccumulator(source_id=source_id, display_name=display_name)
        records[source_id] = accumulator
    elif not accumulator.display_name:
        accumulator.display_name = display_name
    return accumulator


def _parse_geographic_levels(value: str) -> list[str]:
    normalized = value.replace("\n", " ").strip()
    if not normalized or normalized.lower() in {"yes", "no"}:
        return []

    parts = [part.strip() for part in re.split(r"[;,]", normalized) if part.strip()]
    levels: list[str] = []
    for part in parts:
        levels.extend(_split_and_standardize_geographic_level(part))
    return levels


def _standardize_geographic_level(value: str) -> str:
    normalized = " ".join(value.split())
    lower = normalized.casefold()
    aliases = {
        "census": "Census tract",
        "census tract": "Census tract",
        "county/census": "County/Census",
        "county/census tract": "County/Census tract",
        "census region": "Census region",
        "county": "County",
        "state": "State",
        "zipcode": "Zip code",
        "zip code": "Zip code",
        "us": "US",
    }
    if lower in aliases:
        return aliases[lower]

    if lower.startswith("yes"):
        return ""

    if not any(keyword in lower for keyword in ("state", "county", "zip", "census", "tract", "region", "us")):
        return ""

    return normalized


def _split_and_standardize_geographic_level(value: str) -> list[str]:
    candidates = [segment.strip() for segment in value.split("/") if segment.strip()]
    if not candidates:
        candidates = [value]

    levels: list[str] = []
    for candidate in candidates:
        standardized = _standardize_geographic_level(candidate)
        if standardized:
            levels.append(standardized)
    return levels


def _parse_years(value: str) -> list[int]:
    text = value.strip()
    if not text:
        return []

    years: set[int] = set()
    for start_text, end_text in YEAR_RANGE_PATTERN.findall(text):
        start = int(start_text)
        end = int(end_text)
        if start <= end and end - start <= 25:
            years.update(range(start, end + 1))

    years.update(int(match) for match in YEAR_PATTERN.findall(text))
    return normalize_years(list(years))


def _footnote_markers_from_text(value: str) -> list[str]:
    return sorted(set(re.findall(r"\*{1,3}", value)))


def _accumulator_to_record(accumulator: ImportedRecordAccumulator) -> SourceRecord:
    source_documents: list[dict[str, Any]] = []
    seen_documents: set[str] = set()
    for document in accumulator.source_documents:
        signature = json.dumps(document, sort_keys=True)
        if signature in seen_documents:
            continue
        seen_documents.add(signature)
        source_documents.append(document)

    year_notes = "\n".join(sorted(accumulator.year_notes))
    return SourceRecord.from_dict(
        {
            "source_id": accumulator.source_id,
            "display_name": accumulator.display_name,
            "domains": sorted(accumulator.domains, key=str.casefold),
            "geographic_levels": sorted(accumulator.geographic_levels, key=str.casefold),
            "available_years": normalize_years(list(accumulator.available_years)),
            "year_notes": year_notes,
            "notes": sorted(accumulator.notes, key=str.casefold),
            "caveats": sorted(accumulator.caveats, key=str.casefold),
            "source_documents": source_documents,
        }
    )
