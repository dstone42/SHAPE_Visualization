from __future__ import annotations

from dataclasses import asdict, dataclass, field as dataclass_field
from typing import Any


@dataclass
class FieldProvenance:
    source: str
    detail: str | None = None
    timestamp: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = {"source": self.source}
        if self.detail:
            payload["detail"] = self.detail
        if self.timestamp:
            payload["timestamp"] = self.timestamp
        return payload


@dataclass
class ValidationWarning:
    code: str
    severity: str
    source_id: str
    message: str
    field: str | None = None
    details: dict[str, Any] = dataclass_field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SourceRecord:
    source_id: str
    display_name: str = ""
    short_description: str = ""
    source_type: str = ""
    update_frequency: str = ""
    domains: list[str] = dataclass_field(default_factory=list)
    geographic_levels: list[str] = dataclass_field(default_factory=list)
    available_years: list[int] = dataclass_field(default_factory=list)
    year_start: int | None = None
    year_end: int | None = None
    year_notes: str = ""
    source_systems: list[str] = dataclass_field(default_factory=list)
    provenance: dict[str, FieldProvenance] = dataclass_field(default_factory=dict)
    confidence: str = ""
    review_status: str = "draft"
    last_observed_at: str = ""
    last_reviewed_at: str = ""
    notes: list[str] = dataclass_field(default_factory=list)
    caveats: list[str] = dataclass_field(default_factory=list)
    source_documents: list[dict[str, Any]] = dataclass_field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SourceRecord":
        provenance_payload = payload.get("provenance", {})
        provenance = {
            key: value
            if isinstance(value, FieldProvenance)
            else FieldProvenance(
                source=value.get("source", ""),
                detail=value.get("detail"),
                timestamp=value.get("timestamp"),
            )
            for key, value in provenance_payload.items()
        }
        return cls(
            source_id=payload["source_id"],
            display_name=payload.get("display_name", ""),
            short_description=payload.get("short_description", ""),
            source_type=payload.get("source_type", ""),
            update_frequency=payload.get("update_frequency", ""),
            domains=list(payload.get("domains", [])),
            geographic_levels=list(payload.get("geographic_levels", [])),
            available_years=normalize_years(payload.get("available_years", [])),
            year_start=payload.get("year_start"),
            year_end=payload.get("year_end"),
            year_notes=payload.get("year_notes", ""),
            source_systems=list(payload.get("source_systems", [])),
            provenance=provenance,
            confidence=payload.get("confidence", ""),
            review_status=payload.get("review_status", "draft"),
            last_observed_at=payload.get("last_observed_at", ""),
            last_reviewed_at=payload.get("last_reviewed_at", ""),
            notes=list(payload.get("notes", [])),
            caveats=list(payload.get("caveats", [])),
            source_documents=list(payload.get("source_documents", [])),
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["available_years"] = normalize_years(self.available_years)
        payload["domains"] = sorted_unique(self.domains)
        payload["geographic_levels"] = sorted_unique(self.geographic_levels)
        payload["source_systems"] = sorted_unique(self.source_systems)
        payload["notes"] = [note for note in self.notes if note]
        payload["caveats"] = [caveat for caveat in self.caveats if caveat]
        payload["provenance"] = {
            field_name: provenance.to_dict()
            for field_name, provenance in sorted(self.provenance.items())
        }
        if payload["available_years"]:
            payload["year_start"] = payload["available_years"][0]
            payload["year_end"] = payload["available_years"][-1]
        return payload


def normalize_years(values: list[Any]) -> list[int]:
    years = sorted({int(value) for value in values if value not in (None, "")})
    return years


def sorted_unique(values: list[str]) -> list[str]:
    normalized = {value.strip() for value in values if value and value.strip()}
    return sorted(normalized, key=str.casefold)
