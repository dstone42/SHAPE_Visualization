from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from .models import FieldProvenance, SourceRecord, ValidationWarning, normalize_years
from .publish import generated_timestamp, publish_site, publish_validation_report
from .sources import (
    load_imported_records,
    load_observed_records,
    load_reviewed_registry,
    load_runtime_environment,
)

STRUCTURAL_FIELDS = {
    "available_years",
    "year_start",
    "year_end",
    "geographic_levels",
    "source_systems",
    "last_observed_at",
}

LIST_FIELDS = {
    "domains",
    "geographic_levels",
    "available_years",
    "source_systems",
    "notes",
    "caveats",
    "source_documents",
}

TEXT_FIELDS = {
    "display_name",
    "short_description",
    "source_type",
    "update_frequency",
    "year_notes",
    "confidence",
    "review_status",
    "last_observed_at",
    "last_reviewed_at",
}


def run_pipeline(root: Path) -> dict[str, Path]:
    root = root.resolve()
    load_runtime_environment(root)
    observed_records = load_observed_records(root)
    imported_records = load_imported_records(root)
    reviewed_records = load_reviewed_registry(root)

    merged_records, warnings = reconcile_records(
        observed_records=observed_records,
        imported_records=imported_records,
        reviewed_records=reviewed_records,
    )

    artifacts_dir = root / "artifacts"
    site_dir = root / "site"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    site_dir.mkdir(parents=True, exist_ok=True)

    write_json(artifacts_dir / "observed_metadata.json", [record.to_dict() for record in observed_records])
    write_json(artifacts_dir / "imported_metadata.json", [record.to_dict() for record in imported_records])
    write_json(artifacts_dir / "reviewed_registry_draft.json", [record.to_dict() for record in merged_records])
    write_json(artifacts_dir / "validation_report.json", [warning.to_dict() for warning in warnings])

    generated_at = generated_timestamp()
    publish_validation_report(warnings, artifacts_dir / "validation_report.html", generated_at)
    publish_site(merged_records, warnings, site_dir, generated_at)

    return {
        "artifacts_dir": artifacts_dir,
        "site_dir": site_dir,
    }


def reconcile_records(
    observed_records: list[SourceRecord],
    imported_records: list[SourceRecord],
    reviewed_records: list[SourceRecord],
) -> tuple[list[SourceRecord], list[ValidationWarning]]:
    observed = {record.source_id: record for record in observed_records}
    imported = {record.source_id: record for record in imported_records}
    reviewed = {record.source_id: record for record in reviewed_records}

    merged_records: list[SourceRecord] = []
    warnings: list[ValidationWarning] = []

    for source_id in sorted(set(observed) | set(imported) | set(reviewed)):
        observed_record = observed.get(source_id)
        imported_record = imported.get(source_id)
        reviewed_record = reviewed.get(source_id)

        merged = SourceRecord(source_id=source_id)

        for field_name in TEXT_FIELDS | LIST_FIELDS:
            value, provenance = pick_field(
                field_name,
                observed_record,
                imported_record,
                reviewed_record,
            )
            setattr(merged, field_name, value)
            if provenance:
                merged.provenance[field_name] = provenance

        merged.available_years = normalize_years(merged.available_years)
        if merged.available_years:
            merged.year_start = merged.available_years[0]
            merged.year_end = merged.available_years[-1]
            if "available_years" in merged.provenance:
                merged.provenance["year_start"] = merged.provenance["available_years"]
                merged.provenance["year_end"] = merged.provenance["available_years"]

        merged_records.append(merged)
        warnings.extend(
            validate_record(
                merged,
                observed_record=observed_record,
                imported_record=imported_record,
                reviewed_record=reviewed_record,
            )
        )

    return merged_records, sorted(
        warnings,
        key=lambda warning: (warning.severity, warning.source_id, warning.code, warning.field or ""),
    )


def pick_field(
    field_name: str,
    observed_record: SourceRecord | None,
    imported_record: SourceRecord | None,
    reviewed_record: SourceRecord | None,
) -> tuple[Any, FieldProvenance | None]:
    source_order: list[tuple[str, SourceRecord | None]]
    if field_name in STRUCTURAL_FIELDS:
        source_order = [
            ("database", observed_record),
            ("manual", reviewed_record),
            ("spreadsheet", imported_record),
        ]
    else:
        source_order = [
            ("manual", reviewed_record),
            ("spreadsheet", imported_record),
            ("database", observed_record),
        ]

    for source_name, record in source_order:
        if not record:
            continue
        value = getattr(record, field_name)
        if has_value(value):
            detail = None
            if source_name == "spreadsheet":
                detail = "imported reference metadata"
            elif source_name == "database":
                detail = "observed metadata"
            elif source_name == "manual":
                detail = "reviewed registry"
            timestamp = getattr(record, "last_observed_at", "") or getattr(record, "last_reviewed_at", "")
            return clone_value(value), FieldProvenance(source=source_name, detail=detail, timestamp=timestamp or None)

    default_value: Any = [] if field_name in LIST_FIELDS else ""
    return default_value, None


def validate_record(
    merged: SourceRecord,
    observed_record: SourceRecord | None,
    imported_record: SourceRecord | None,
    reviewed_record: SourceRecord | None,
) -> list[ValidationWarning]:
    warnings: list[ValidationWarning] = []

    if observed_record and not reviewed_record:
        warnings.append(
            ValidationWarning(
                code="missing_reviewed_registry_entry",
                severity="warning",
                source_id=merged.source_id,
                message="Source was observed or imported but is missing from the reviewed registry.",
            )
        )

    if reviewed_record and observed_record:
        observed_years = normalize_years(observed_record.available_years)
        reviewed_years = normalize_years(reviewed_record.available_years)
        if observed_years and reviewed_years and observed_years != reviewed_years:
            warnings.append(
                ValidationWarning(
                    code="observed_year_drift",
                    severity="warning",
                    source_id=merged.source_id,
                    field="available_years",
                    message="Observed years differ from the reviewed registry.",
                    details={"observed": observed_years, "reviewed": reviewed_years},
                )
            )

    if reviewed_record and imported_record:
        imported_domains = sorted(imported_record.domains, key=str.casefold)
        reviewed_domains = sorted(reviewed_record.domains, key=str.casefold)
        if imported_domains and reviewed_domains and imported_domains != reviewed_domains:
            warnings.append(
                ValidationWarning(
                    code="domain_mismatch",
                    severity="warning",
                    source_id=merged.source_id,
                    field="domains",
                    message="Imported domains differ from the reviewed registry.",
                    details={"imported": imported_domains, "reviewed": reviewed_domains},
                )
            )

    for document in imported_record.source_documents if imported_record else []:
        if document.get("stale"):
            warnings.append(
                ValidationWarning(
                    code="stale_codebook",
                    severity="info",
                    source_id=merged.source_id,
                    field="source_documents",
                    message="A referenced codebook or source document is marked as stale.",
                    details=document,
                )
            )

    if merged.available_years and not is_contiguous(merged.available_years):
        warnings.append(
            ValidationWarning(
                code="non_contiguous_years",
                severity="info",
                source_id=merged.source_id,
                field="available_years",
                message="Available years are non-contiguous.",
                details={"available_years": merged.available_years},
            )
        )

    if merged.review_status.lower() != "reviewed":
        warnings.append(
            ValidationWarning(
                code="needs_review",
                severity="info",
                source_id=merged.source_id,
                field="review_status",
                message="Source is not yet marked as reviewed.",
                details={"review_status": merged.review_status},
            )
        )

    return warnings


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, Iterable) and not isinstance(value, (str, bytes, dict)):
        return bool(list(value))
    if isinstance(value, dict):
        return bool(value)
    return True


def clone_value(value: Any) -> Any:
    if isinstance(value, list):
        return list(value)
    if isinstance(value, dict):
        return dict(value)
    return value


def is_contiguous(years: list[int]) -> bool:
    return years == list(range(years[0], years[-1] + 1))
