from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from shape_metadata.pipeline import run_pipeline


class PipelineTest(unittest.TestCase):
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
                root / "data" / "inputs" / "observed_sample.json",
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
                root / "data" / "inputs" / "imported_sample.json",
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
            self._write_json(root / "data" / "inputs" / "observed_sample.json", [])
            self._write_json(root / "data" / "inputs" / "imported_sample.json", [])

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

    def _write_json(self, path: Path, payload: object) -> None:
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
