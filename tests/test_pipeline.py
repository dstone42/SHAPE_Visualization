from __future__ import annotations

import json
import os
import tempfile
import unittest
from html import escape
from pathlib import Path
from zipfile import ZipFile

from shape_metadata.pipeline import run_pipeline
from shape_metadata.sources import _shape_doc_rows_to_records


class PipelineTest(unittest.TestCase):
    def setUp(self) -> None:
        self._saved_env = {
            key: os.environ.get(key)
            for key in (
                "SHAPE_IMPORTED_SNAPSHOT",
                "SHAPE_CODEBOOK_SNAPSHOT",
                "SHAPE_OBSERVED_SNAPSHOT",
                "SHAPE_MSSQL_USER",
                "SHAPE_MSSQL_PASSWORD",
                "SHAPE_MSSQL_HOST",
                "SHAPE_MSSQL_DATABASE",
                "SHAPE_MSSQL_TABLE",
            )
        }
        for key in self._saved_env:
            os.environ.pop(key, None)

    def tearDown(self) -> None:
        for key in (
            "SHAPE_IMPORTED_SNAPSHOT",
            "SHAPE_CODEBOOK_SNAPSHOT",
            "SHAPE_OBSERVED_SNAPSHOT",
            "SHAPE_MSSQL_USER",
            "SHAPE_MSSQL_PASSWORD",
            "SHAPE_MSSQL_HOST",
            "SHAPE_MSSQL_DATABASE",
            "SHAPE_MSSQL_TABLE",
        ):
            os.environ.pop(key, None)
        for key, value in self._saved_env.items():
            if value is not None:
                os.environ[key] = value

    def test_pipeline_builds_artifacts_and_warnings(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "data" / "inputs").mkdir(parents=True)

            self._write_json(
                root / "data" / "reviewed_registry.json",
                [
                    {
                        "source_id": "alpha",
                        "display_name": "Alpha",
                        "domains": ["Cancer diagnosis"],
                        "available_years": [2022, 2023],
                        "review_status": "reviewed",
                        "last_reviewed_at": "2026-03-25",
                    },
                    {
                        "source_id": "beta",
                        "display_name": "Beta",
                        "domains": ["Health care access"],
                        "available_years": [2020, 2021],
                        "review_status": "reviewed",
                        "last_reviewed_at": "2026-03-25",
                    },
                ],
            )
            self._write_json(
                root / "data" / "inputs" / "observed_snapshot.json",
                [
                    {
                        "source_id": "alpha",
                        "display_name": "Alpha",
                        "available_years": [2022, 2023],
                        "geographic_levels": ["State"],
                        "source_systems": ["Warehouse"],
                        "last_observed_at": "2026-03-25T08:00:00-06:00",
                    },
                    {
                        "source_id": "beta",
                        "display_name": "Beta",
                        "available_years": [2020, 2021, 2022],
                        "geographic_levels": ["County", "State"],
                        "source_systems": ["Warehouse"],
                        "last_observed_at": "2026-03-25T08:01:00-06:00",
                    },
                    {
                        "source_id": "gamma",
                        "display_name": "Gamma",
                        "available_years": [2018, 2020],
                        "geographic_levels": ["State"],
                        "source_systems": ["Warehouse"],
                        "last_observed_at": "2026-03-25T08:02:00-06:00",
                    },
                ],
            )
            self._write_json(
                root / "data" / "inputs" / "imported_snapshot.json",
                [
                    {
                        "source_id": "alpha",
                        "display_name": "Alpha",
                        "domains": ["Cancer diagnosis"],
                        "source_documents": [],
                    },
                    {
                        "source_id": "beta",
                        "display_name": "Beta",
                        "domains": ["General health"],
                        "source_documents": [
                            {
                                "name": "Beta codebook",
                                "type": "codebook",
                                "stale": True,
                            }
                        ],
                    },
                ],
            )
            os.environ["SHAPE_OBSERVED_SNAPSHOT"] = str(root / "data" / "inputs" / "observed_snapshot.json")
            os.environ["SHAPE_IMPORTED_SNAPSHOT"] = str(root / "data" / "inputs" / "imported_snapshot.json")

            outputs = run_pipeline(root)

            self.assertTrue((outputs["artifacts_dir"] / "observed_metadata.json").exists())
            self.assertTrue((outputs["artifacts_dir"] / "imported_metadata.json").exists())
            self.assertTrue((outputs["artifacts_dir"] / "reviewed_registry_draft.json").exists())
            self.assertTrue((outputs["artifacts_dir"] / "validation_report.json").exists())
            self.assertTrue((outputs["site_dir"] / "index.html").exists())
            self.assertTrue((outputs["site_dir"] / "metadata.json").exists())

            warnings = json.loads((outputs["artifacts_dir"] / "validation_report.json").read_text())
            codes = {(warning["source_id"], warning["code"]) for warning in warnings}
            self.assertIn(("gamma", "missing_reviewed_registry_entry"), codes)
            self.assertIn(("beta", "observed_year_drift"), codes)
            self.assertIn(("beta", "domain_mismatch"), codes)
            self.assertIn(("beta", "stale_codebook"), codes)
            self.assertIn(("gamma", "non_contiguous_years"), codes)

    def test_site_filters_are_data_driven(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "data" / "inputs").mkdir(parents=True)
            self._write_json(
                root / "data" / "reviewed_registry.json",
                [
                    {
                        "source_id": "delta",
                        "display_name": "Delta",
                        "domains": ["Rurality"],
                        "geographic_levels": ["County"],
                        "available_years": [2024],
                        "source_type": "Survey",
                        "update_frequency": "Annual",
                        "review_status": "reviewed",
                        "last_reviewed_at": "2026-03-25",
                    }
                ],
            )
            outputs = run_pipeline(root)

            app_js = (outputs["site_dir"] / "app.js").read_text()
            index_html = (outputs["site_dir"] / "index.html").read_text()
            metadata = json.loads((outputs["site_dir"] / "metadata.json").read_text())

            self.assertIn("collectFilterValues(records, \"domains\")", app_js)
            self.assertIn('document.getElementById("shapeMetadata")', app_js)
            self.assertNotIn("Rurality", app_js)
            self.assertIn('id="filters"', index_html)
            self.assertIn('id="shapeMetadata"', index_html)
            self.assertEqual(metadata["records"][0]["domains"], ["Rurality"])

    def test_pipeline_loads_env_and_parses_xlsx_import(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "data" / "inputs").mkdir(parents=True)

            workbook_path = root / "data" / "inputs" / "imported_snapshot.xlsx"
            self._write_test_workbook(
                workbook_path,
                {
                    "Current state of SHAPE": [
                        ["Health Assessment Domain", "Base Measure", "In SHAPE?", "Sources Currently in SHAPE", "Sources Planned or Active work in SHAPE", "Sources to be determined"],
                        ["", "Health behaviors", "", "", "", ""],
                        ["", "Breast cancer screening", "Yes", "BRFSS", "CMS", ""],
                        ["", "Confidence in getting cancer information", "Yes", "HINTS**", "", ""],
                        ["**", "The measure is in the dataset but did not create a stable enough measure to pass the QC.", "", "", "", ""],
                    ],
                    "Domains by data source": [
                        ["", "BRFSS", "CMS", "HINTS"],
                        ["Lowest geographic level", "State/County", "County", "State"],
                        ["Has PHI?", "", "Yes", ""],
                        ["Health behaviors", "", "", ""],
                        ["Breast cancer screening", "Yes", "", "Yes"],
                        ["Confidence in getting cancer information", "", "", "Yes"],
                    ],
                    "BRFFS": [
                        ["Base Measure", "How does the source answer the domain? (ie. question)", "Years Included", "Link"],
                        ["Health behaviors", "", "", ""],
                        ["Breast cancer screening", "Women respondents aged 40+ who have had a mammogram in the past two years", "2022, 2023", "https://example.test/brfss"],
                    ],
                },
            )

            (root / ".env").write_text(
                "SHAPE_IMPORTED_SNAPSHOT=data/inputs/imported_snapshot.xlsx\n",
                encoding="utf-8",
            )
            self._write_json(
                root / "data" / "reviewed_registry.json",
                [
                    {
                        "source_id": "brfss",
                        "display_name": "BRFSS",
                        "domains": ["Health behaviors"],
                        "review_status": "reviewed",
                        "last_reviewed_at": "2026-03-25",
                    }
                ],
            )
            outputs = run_pipeline(root)
            imported = json.loads((outputs["artifacts_dir"] / "imported_metadata.json").read_text())
            imported_by_id = {record["source_id"]: record for record in imported}

            self.assertEqual(imported_by_id["brfss"]["available_years"], [2022, 2023])
            self.assertEqual(imported_by_id["brfss"]["geographic_levels"], ["County", "State"])
            self.assertEqual(imported_by_id["brfss"]["domains"], ["Health behaviors"])
            self.assertTrue(
                any(document.get("worksheet") == "BRFFS" for document in imported_by_id["brfss"]["source_documents"])
            )
            self.assertTrue(
                any(document.get("url") == "https://example.test/brfss" for document in imported_by_id["brfss"]["source_documents"])
            )
            self.assertNotIn("cms", imported_by_id)
            self.assertTrue(
                any("stable enough measure" in caveat for caveat in imported_by_id["hints"]["caveats"])
            )

    def test_pipeline_normalizes_spreadsheet_source_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "data" / "inputs").mkdir(parents=True)

            workbook_path = root / "data" / "inputs" / "alias_snapshot.xlsx"
            self._write_test_workbook(
                workbook_path,
                {
                    "Current state of SHAPE": [
                        ["Health Assessment Domain", "Base Measure", "In SHAPE?", "Sources Currently in SHAPE", "Sources Planned or Active work in SHAPE", "Sources to be determined"],
                        ["", "Clinical trials", "", "", "", ""],
                        ["", "Trial accrual", "Yes", "CCSG", "", ""],
                        ["", "Health behaviors", "", "", "", ""],
                        ["", "HPV vaccination", "Yes", "HPV Vaccination Coalition", "", ""],
                    ],
                    "Domains by data source": [
                        ["", "CCSG", "HPV Vaccination Coalition"],
                        ["Lowest geographic level", "State", "State"],
                        ["Clinical trials", "Yes", ""],
                        ["Health behaviors", "", "Yes"],
                    ],
                    "CCSG": [
                        ["Base Measure", "Years Included", "Link"],
                        ["Clinical trials", "", ""],
                        ["Trial accrual", "2024", "https://example.test/ccsg"],
                    ],
                    "HPV Vaccination Coalition": [
                        ["Base Measure", "Years Included", "Link"],
                        ["Health behaviors", "", ""],
                        ["HPV vaccination", "2023", "https://example.test/hpv"],
                    ],
                },
            )

            (root / ".env").write_text(
                "SHAPE_IMPORTED_SNAPSHOT=data/inputs/alias_snapshot.xlsx\n",
                encoding="utf-8",
            )
            self._write_json(
                root / "data" / "reviewed_registry.json",
                [
                    {
                        "source_id": "internal-hci-data",
                        "display_name": "Internal HCI Data",
                        "review_status": "reviewed",
                        "last_reviewed_at": "2026-03-25",
                    },
                    {
                        "source_id": "hpv-vaccination-coalition",
                        "display_name": "HPV Vaccination Coalition",
                        "review_status": "reviewed",
                        "last_reviewed_at": "2026-03-25",
                    },
                ],
            )

            outputs = run_pipeline(root)
            imported = json.loads((outputs["artifacts_dir"] / "imported_metadata.json").read_text())
            imported_by_id = {record["source_id"]: record for record in imported}

            self.assertIn("internal-hci-data", imported_by_id)
            self.assertIn("hpv-vaccination-coalition", imported_by_id)
            self.assertNotIn("ccsg", imported_by_id)
            self.assertEqual(imported_by_id["internal-hci-data"]["display_name"], "Internal HCI Data")
            self.assertEqual(
                imported_by_id["hpv-vaccination-coalition"]["display_name"],
                "HPV Vaccination Coalition",
            )

    def test_pipeline_normalizes_json_snapshot_source_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "data" / "inputs").mkdir(parents=True)

            self._write_json(
                root / "data" / "reviewed_registry.json",
                [
                    {
                        "source_id": "internal-hci-data",
                        "display_name": "Internal HCI Data",
                        "review_status": "reviewed",
                        "last_reviewed_at": "2026-03-25",
                    },
                    {
                        "source_id": "hpv-vaccination-coalition",
                        "display_name": "HPV Vaccination Coalition",
                        "review_status": "reviewed",
                        "last_reviewed_at": "2026-03-25",
                    },
                ],
            )
            self._write_json(
                root / "data" / "inputs" / "observed_snapshot.json",
                [
                    {
                        "source_id": "edw",
                        "display_name": "EDW",
                        "short_description": "Warehouse source",
                        "source_systems": ["Warehouse"],
                        "last_observed_at": "2026-03-25T08:00:00-06:00",
                    },
                    {
                        "source_id": "vcaa",
                        "display_name": "VCAA",
                        "short_description": "Vaccination source",
                        "source_systems": ["Warehouse"],
                        "last_observed_at": "2026-03-25T08:01:00-06:00",
                    },
                ],
            )
            self._write_json(
                root / "data" / "inputs" / "imported_snapshot.json",
                [
                    {
                        "source_id": "ccsg",
                        "display_name": "CCSG",
                        "domains": ["Clinical trials"],
                    },
                    {
                        "source_id": "hpv-vaccination-coalition",
                        "display_name": "HPV Vaccination Coalition",
                        "domains": ["Health behaviors"],
                    },
                ],
            )

            os.environ["SHAPE_OBSERVED_SNAPSHOT"] = str(root / "data" / "inputs" / "observed_snapshot.json")
            os.environ["SHAPE_IMPORTED_SNAPSHOT"] = str(root / "data" / "inputs" / "imported_snapshot.json")

            outputs = run_pipeline(root)
            merged = json.loads((outputs["artifacts_dir"] / "reviewed_registry_draft.json").read_text())
            merged_by_id = {record["source_id"]: record for record in merged}

            self.assertIn("internal-hci-data", merged_by_id)
            self.assertIn("hpv-vaccination-coalition", merged_by_id)
            self.assertNotIn("edw", merged_by_id)
            self.assertNotIn("ccsg", merged_by_id)
            self.assertNotIn("vcaa", merged_by_id)
            self.assertEqual(merged_by_id["internal-hci-data"]["domains"], ["Clinical trials"])
            self.assertEqual(merged_by_id["internal-hci-data"]["display_name"], "Internal HCI Data")
            self.assertEqual(
                merged_by_id["hpv-vaccination-coalition"]["display_name"],
                "HPV Vaccination Coalition",
            )

    def test_shape_doc_rows_map_schema_descriptions_to_sources(self) -> None:
        records = _shape_doc_rows_to_records(
            [
                {
                    "schema_name": "BRFSS",
                    "table_name": None,
                    "column_name": None,
                    "description": "Behavioral Risk Factor Surveillance System schema.",
                    "updated_at": "2026-03-27T08:15:00-06:00",
                },
                {
                    "schema_name": "HCI",
                    "table_name": None,
                    "column_name": None,
                    "description": "Internal HCI schema documentation.",
                    "updated_at": "2026-03-27T08:20:00-06:00",
                },
                {
                    "schema_name": "BRFSS",
                    "table_name": "question",
                    "column_name": None,
                    "description": "Should be ignored because it is table-level documentation.",
                    "updated_at": "2026-03-27T08:25:00-06:00",
                },
                {
                    "schema_name": None,
                    "table_name": None,
                    "column_name": None,
                    "description": "Database-level row should be ignored for now.",
                    "updated_at": "2026-03-27T08:30:00-06:00",
                },
            ]
        )

        by_id = {record.source_id: record.to_dict() for record in records}
        self.assertEqual(sorted(by_id), ["brfss", "internal-hci-data"])
        self.assertEqual(
            by_id["brfss"]["short_description"],
            "Behavioral Risk Factor Surveillance System schema.",
        )
        self.assertEqual(
            by_id["internal-hci-data"]["short_description"],
            "Internal HCI schema documentation.",
        )
        self.assertEqual(by_id["brfss"]["source_systems"], ["MS SQL Server"])
        self.assertEqual(by_id["brfss"]["last_observed_at"], "2026-03-27T08:15:00-06:00")

    def test_shape_doc_rows_normalize_database_source_aliases(self) -> None:
        records = _shape_doc_rows_to_records(
            [
                {
                    "schema_name": "EDW",
                    "table_name": None,
                    "column_name": None,
                    "description": "Enterprise data warehouse schema documentation.",
                    "updated_at": "2026-03-27T08:15:00-06:00",
                },
                {
                    "schema_name": "VCAA",
                    "table_name": None,
                    "column_name": None,
                    "description": "Vaccination Coverage Among Adolescents schema documentation.",
                    "updated_at": "2026-03-27T08:20:00-06:00",
                },
            ]
        )

        by_id = {record.source_id: record.to_dict() for record in records}
        self.assertEqual(sorted(by_id), ["hpv-vaccination-coalition", "internal-hci-data"])
        self.assertEqual(by_id["internal-hci-data"]["display_name"], "Internal HCI Data")
        self.assertEqual(
            by_id["hpv-vaccination-coalition"]["display_name"],
            "HPV Vaccination Coalition",
        )
        self.assertEqual(
            by_id["internal-hci-data"]["short_description"],
            "Enterprise data warehouse schema documentation.",
        )
        self.assertEqual(
            by_id["hpv-vaccination-coalition"]["short_description"],
            "Vaccination Coverage Among Adolescents schema documentation.",
        )


    def _write_json(self, path: Path, payload: object) -> None:
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    def _write_test_workbook(self, path: Path, sheets: dict[str, list[list[str]]]) -> None:
        with ZipFile(path, "w") as archive:
            archive.writestr(
                "[Content_Types].xml",
                self._build_content_types_xml(len(sheets)),
            )
            archive.writestr(
                "_rels/.rels",
                """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>
""",
            )
            archive.writestr(
                "xl/workbook.xml",
                self._build_workbook_xml(list(sheets)),
            )
            archive.writestr(
                "xl/_rels/workbook.xml.rels",
                self._build_workbook_rels_xml(len(sheets)),
            )

            for index, (_, rows) in enumerate(sheets.items(), start=1):
                archive.writestr(
                    f"xl/worksheets/sheet{index}.xml",
                    self._build_sheet_xml(rows),
                )

    def _build_content_types_xml(self, sheet_count: int) -> str:
        overrides = [
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        ]
        for index in range(1, sheet_count + 1):
            overrides.append(
                f'<Override PartName="/xl/worksheets/sheet{index}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            )
        joined = "\n  ".join(overrides)
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  {joined}
</Types>
"""

    def _build_workbook_xml(self, sheet_names: list[str]) -> str:
        sheets_xml = []
        for index, name in enumerate(sheet_names, start=1):
            sheets_xml.append(
                f'<sheet name="{escape(name, quote=True)}" sheetId="{index}" r:id="rId{index}"/>'
            )
        joined = "\n    ".join(sheets_xml)
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    {joined}
  </sheets>
</workbook>
"""

    def _build_workbook_rels_xml(self, sheet_count: int) -> str:
        relationships = []
        for index in range(1, sheet_count + 1):
            relationships.append(
                f'<Relationship Id="rId{index}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{index}.xml"/>'
            )
        joined = "\n  ".join(relationships)
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  {joined}
</Relationships>
"""

    def _build_sheet_xml(self, rows: list[list[str]]) -> str:
        row_xml = []
        for row_number, values in enumerate(rows, start=1):
            cells = []
            for column_index, value in enumerate(values, start=1):
                if value == "":
                    continue
                ref = f"{self._column_name(column_index)}{row_number}"
                cells.append(
                    f'<c r="{ref}" t="inlineStr"><is><t>{escape(value)}</t></is></c>'
                )
            row_xml.append(f'<row r="{row_number}">{"".join(cells)}</row>')
        joined = "\n    ".join(row_xml)
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>
    {joined}
  </sheetData>
</worksheet>
"""

    def _column_name(self, index: int) -> str:
        name = ""
        current = index
        while current:
            current, remainder = divmod(current - 1, 26)
            name = chr(65 + remainder) + name
        return name


if __name__ == "__main__":
    unittest.main()
