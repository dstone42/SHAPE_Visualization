from __future__ import annotations

import csv
import io
import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from .models import SourceRecord, normalize_years


def load_observed_records(root: Path) -> list[SourceRecord]:
    snapshot_path = os.environ.get("SHAPE_OBSERVED_SNAPSHOT")
    if snapshot_path:
        return _load_json_records(Path(snapshot_path))

    sqlite_path = os.environ.get("SHAPE_SQLITE_PATH")
    if sqlite_path:
        table_name = os.environ.get("SHAPE_SQLITE_TABLE", "shape_metadata_inventory")
        return _load_sqlite_records(Path(sqlite_path), table_name)

    return _load_json_records(root / "data" / "inputs" / "observed_sample.json")


def load_imported_records(root: Path) -> list[SourceRecord]:
    snapshot_path = os.environ.get("SHAPE_IMPORTED_SNAPSHOT")
    if snapshot_path:
        imported_records = _load_imported_snapshot(Path(snapshot_path))
    elif os.environ.get("BOX_DEVELOPER_TOKEN") and os.environ.get("BOX_FILE_ID"):
        imported_records = _load_box_records()
    else:
        imported_records = _load_json_records(root / "data" / "inputs" / "imported_sample.json")

    codebook_path = os.environ.get("SHAPE_CODEBOOK_SNAPSHOT")
    if codebook_path:
        codebook_records = _load_json_records(Path(codebook_path))
        imported_records = _merge_reference_records(imported_records, codebook_records)

    return imported_records


def load_reviewed_registry(root: Path) -> list[SourceRecord]:
    return _load_json_records(root / "data" / "reviewed_registry.json")


def _load_imported_snapshot(path: Path) -> list[SourceRecord]:
    if path.suffix.lower() == ".csv":
        return _load_csv_records(path)
    return _load_json_records(path)


def _load_json_records(path: Path) -> list[SourceRecord]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [SourceRecord.from_dict(record) for record in payload]


def _load_csv_records(path: Path) -> list[SourceRecord]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            rows.append(_csv_row_to_record(row))
    return [SourceRecord.from_dict(row) for row in rows]


def _csv_row_to_record(row: dict[str, str]) -> dict[str, Any]:
    years = normalize_years(_split_multivalue(row.get("available_years", "")))
    return {
        "source_id": row["source_id"],
        "display_name": row.get("display_name", ""),
        "short_description": row.get("short_description", ""),
        "source_type": row.get("source_type", ""),
        "update_frequency": row.get("update_frequency", ""),
        "domains": _split_multivalue(row.get("domains", "")),
        "geographic_levels": _split_multivalue(row.get("geographic_levels", "")),
        "available_years": years,
        "year_start": years[0] if years else None,
        "year_end": years[-1] if years else None,
        "year_notes": row.get("year_notes", ""),
        "source_systems": _split_multivalue(row.get("source_systems", "")),
        "confidence": row.get("confidence", ""),
        "review_status": row.get("review_status", "draft"),
        "last_observed_at": row.get("last_observed_at", ""),
        "last_reviewed_at": row.get("last_reviewed_at", ""),
        "notes": _split_multivalue(row.get("notes", "")),
        "caveats": _split_multivalue(row.get("caveats", "")),
    }


def _split_multivalue(value: str) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split("|") if item.strip()]


def _load_sqlite_records(path: Path, table_name: str) -> list[SourceRecord]:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    try:
        query = (
            f"SELECT source_id, display_name, year, geographic_level, source_system "
            f"FROM {table_name}"
        )
        records: dict[str, dict[str, Any]] = {}
        for row in connection.execute(query):
            source_id = row["source_id"]
            current = records.setdefault(
                source_id,
                {
                    "source_id": source_id,
                    "display_name": row["display_name"] or source_id,
                    "available_years": [],
                    "geographic_levels": [],
                    "source_systems": [],
                },
            )
            if row["year"] is not None:
                current["available_years"].append(int(row["year"]))
            if row["geographic_level"]:
                current["geographic_levels"].append(row["geographic_level"])
            if row["source_system"]:
                current["source_systems"].append(row["source_system"])
        normalized: list[SourceRecord] = []
        for record in records.values():
            years = normalize_years(record.get("available_years", []))
            record["available_years"] = years
            record["year_start"] = years[0] if years else None
            record["year_end"] = years[-1] if years else None
            normalized.append(SourceRecord.from_dict(record))
        return normalized
    finally:
        connection.close()


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

    if os.environ.get("BOX_FILE_FORMAT", "csv").lower() == "json":
        payload = json.loads(stream.read().decode("utf-8"))
        return [SourceRecord.from_dict(record) for record in payload]

    text_stream = io.StringIO(stream.read().decode("utf-8-sig"))
    reader = csv.DictReader(text_stream)
    return [SourceRecord.from_dict(_csv_row_to_record(row)) for row in reader]


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
