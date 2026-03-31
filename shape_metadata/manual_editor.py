from __future__ import annotations

import argparse
import json
from functools import partial
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .models import SourceRecord
from .pipeline import reconcile_records
from .sources import (
    _canonicalize_records,
    load_imported_records,
    load_observed_records,
    load_reviewed_registry,
    load_runtime_environment,
)

EDITOR_ASSETS_DIR = Path(__file__).resolve().parent / "manual_editor_assets"
REVIEWED_REGISTRY_PATH = Path("data") / "reviewed_registry.json"
LIST_FIELDS = {
    "domains",
    "geographic_levels",
    "available_years",
    "source_systems",
    "notes",
    "caveats",
    "source_documents",
}
MANUAL_FIELD_ORDER = (
    "source_id",
    "display_name",
    "short_description",
    "source_type",
    "update_frequency",
    "domains",
    "geographic_levels",
    "available_years",
    "year_notes",
    "source_systems",
    "confidence",
    "review_status",
    "last_reviewed_at",
    "notes",
    "caveats",
    "source_documents",
)


def load_editor_context(root: Path) -> dict[str, Any]:
    root = root.resolve()
    load_runtime_environment(root)

    reviewed_records = load_reviewed_registry(root)
    observed_records, observed_error = _load_optional_records("database", load_observed_records, root)
    imported_records, imported_error = _load_optional_records("spreadsheet", load_imported_records, root)
    merged_records, warnings = reconcile_records(
        observed_records=observed_records,
        imported_records=imported_records,
        reviewed_records=reviewed_records,
    )

    load_errors = [error for error in (observed_error, imported_error) if error]
    return {
        "reviewed_records": [serialize_reviewed_record(record) for record in reviewed_records],
        "observed_records": [record.to_dict() for record in observed_records],
        "imported_records": [record.to_dict() for record in imported_records],
        "merged_records": [record.to_dict() for record in merged_records],
        "warnings": [warning.to_dict() for warning in warnings],
        "load_errors": load_errors,
    }


def normalize_reviewed_registry_payload(payload: Any) -> list[SourceRecord]:
    if not isinstance(payload, list):
        raise ValueError("Reviewed registry payload must be a JSON array of records.")

    records: list[SourceRecord] = []
    for index, raw_record in enumerate(payload, start=1):
        if not isinstance(raw_record, dict):
            raise ValueError(f"Record {index} must be a JSON object.")

        record_payload = dict(raw_record)
        source_id = str(record_payload.get("source_id", "")).strip()
        if not source_id:
            raise ValueError(f"Record {index} is missing a source_id.")
        record_payload["source_id"] = source_id

        for field_name in LIST_FIELDS:
            if field_name not in record_payload:
                continue
            value = record_payload[field_name]
            if value in (None, ""):
                record_payload[field_name] = []
                continue
            if not isinstance(value, list):
                raise ValueError(f"Field '{field_name}' on record {index} must be a JSON array.")

        source_documents = record_payload.get("source_documents", [])
        if any(not isinstance(document, dict) for document in source_documents):
            raise ValueError(f"Field 'source_documents' on record {index} must only contain JSON objects.")

        records.append(SourceRecord.from_dict(record_payload))

    return _canonicalize_records(records)


def save_reviewed_registry(root: Path, payload: Any) -> list[SourceRecord]:
    records = normalize_reviewed_registry_payload(payload)
    output_path = root.resolve() / REVIEWED_REGISTRY_PATH
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps([serialize_reviewed_record(record) for record in records], indent=2) + "\n",
        encoding="utf-8",
    )
    return records


def serialize_reviewed_record(record: SourceRecord) -> dict[str, Any]:
    payload = record.to_dict()
    payload.pop("provenance", None)
    payload.pop("last_observed_at", None)
    payload.pop("year_start", None)
    payload.pop("year_end", None)

    serialized: dict[str, Any] = {}
    for field_name in MANUAL_FIELD_ORDER:
        value = payload.get(field_name)
        if field_name == "source_id":
            serialized[field_name] = value
            continue
        if value in ("", [], None, {}):
            continue
        serialized[field_name] = value
    return serialized


def create_server(root: Path, host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
    if not EDITOR_ASSETS_DIR.exists():
        raise FileNotFoundError(f"Manual editor assets not found at {EDITOR_ASSETS_DIR}")

    handler = partial(ManualEditorHandler, workspace_root=root.resolve(), directory=str(EDITOR_ASSETS_DIR))
    return ThreadingHTTPServer((host, port), handler)


class ManualEditorHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args: Any, workspace_root: Path, **kwargs: Any) -> None:
        self.workspace_root = workspace_root
        super().__init__(*args, **kwargs)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/context":
            self._handle_context()
            return

        self.path = "/index.html" if parsed.path in {"", "/"} else parsed.path
        super().do_GET()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/api/reviewed-registry":
            self.send_error(HTTPStatus.NOT_FOUND, "Unknown API route.")
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length)
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError as exc:
            self._send_json({"error": f"Request body is not valid JSON: {exc.msg}."}, status=HTTPStatus.BAD_REQUEST)
            return

        try:
            save_reviewed_registry(self.workspace_root, payload)
        except ValueError as exc:
            self._send_json({"error": str(exc)}, status=HTTPStatus.UNPROCESSABLE_ENTITY)
            return
        except Exception as exc:  # pragma: no cover - defensive server path
            self._send_json({"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        self._send_json(load_editor_context(self.workspace_root))

    def do_PUT(self) -> None:
        self.do_POST()

    def log_message(self, format: str, *args: Any) -> None:
        super().log_message(format, *args)

    def _handle_context(self) -> None:
        try:
            payload = load_editor_context(self.workspace_root)
        except Exception as exc:  # pragma: no cover - defensive server path
            self._send_json({"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        self._send_json(payload)

    def _send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        encoded = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)


def _load_optional_records(
    source_name: str,
    loader: Any,
    root: Path,
) -> tuple[list[SourceRecord], dict[str, str] | None]:
    try:
        return loader(root), None
    except Exception as exc:
        return [], {"source": source_name, "message": str(exc)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the SHAPE manual registry editor.")
    parser.add_argument("--root", default=".", help="Workspace root containing data/reviewed_registry.json.")
    parser.add_argument("--host", default="127.0.0.1", help="Host interface to bind.")
    parser.add_argument("--port", type=int, default=8765, help="Port to bind.")
    args = parser.parse_args()

    server = create_server(Path(args.root), host=args.host, port=args.port)
    display_host = "127.0.0.1" if args.host in {"0.0.0.0", "::"} else args.host
    print(f"Manual editor available at http://{display_host}:{server.server_port}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping manual editor.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
