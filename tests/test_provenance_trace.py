from __future__ import annotations

import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from de2sim.asot.builder import build_asot_from_files
from de2sim.ingest.artifact_parser import parse_artifacts_from_manifest
from de2sim.ingest.package_reader import ingest_engineering_package
from de2sim.provenance.manifest import build_provenance_manifest
from de2sim.provenance.trace import calculate_coverage_summary, classify_locator, validate_traceability
from tests.test_asot_builder import make_zip, representative_members


FIXTURES_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class ProvenanceTraceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp_roots: list[Path] = []

    def tearDown(self) -> None:
        for root in self._temp_roots:
            shutil.rmtree(root, ignore_errors=True)

    def build_fixture(self) -> tuple[dict, dict, dict, dict, Path]:
        root = Path(tempfile.mkdtemp(dir=FIXTURES_DIR))
        self._temp_roots.append(root)
        package = root / "uas.zip"
        output = root / "out"
        make_zip(package, representative_members())
        manifest_path = ingest_engineering_package(package, output)
        parsed_path = parse_artifacts_from_manifest(manifest_path)
        document = build_asot_from_files(manifest_path, parsed_path)
        asot_path = output / "asot.json"
        asot_path.write_text(json.dumps(document.to_dict(), indent=2) + "\n", encoding="utf-8")
        manifest = read_json(manifest_path)
        parsed = read_json(parsed_path)
        asot = read_json(asot_path)
        provenance = build_provenance_manifest(asot, manifest, parsed, manifest_path, parsed_path, asot_path)
        return manifest, parsed, asot, provenance, output

    def test_locator_classification(self) -> None:
        self.assertEqual(classify_locator("row:2", "requirements/reqs.csv"), "csv_row")
        self.assertEqual(classify_locator("line:4", "requirements/reqs.md"), "text_line")
        self.assertEqual(classify_locator("json:0", "parameters/params.json"), "json_pointer")
        self.assertEqual(classify_locator("line:1", "sysml/model.sysml"), "sysml_line")
        self.assertEqual(classify_locator("sysml:Airframe", "sysml/model.sysml"), "sysml_element")
        self.assertEqual(classify_locator("file", "geometry/body.glb"), "geometry_file")

    def test_requirement_parameter_sysml_behavior_model_and_geometry_traceability(self) -> None:
        manifest, _parsed, asot, provenance, output = self.build_fixture()
        report = validate_traceability(asot, provenance, output / manifest["extraction_root"])
        self.assertTrue(report.valid, report.errors)

        for section in ("requirements", "parameters", "components", "behaviors", "physical_models", "geometry"):
            with self.subTest(section=section):
                self.assertTrue(asot[section])
                self.assertTrue(all(item["source_references"] for item in asot[section]))

        self.assertEqual(asot["geometry"][0]["traceability_status"], "whole_file")
        self.assertEqual(asot["requirements"][0]["traceability_status"], "precise")
        self.assertGreater(report.coverage_summary["traceability_percentage"], 0.0)
        self.assertIn(asot["geometry"][0]["stable_id"], report.entities_with_whole_file_only_provenance)

    def test_unresolved_and_not_provided_coverage(self) -> None:
        _manifest, _parsed, asot, provenance, _output = self.build_fixture()
        edited = copy.deepcopy(asot)
        edited["parameters"][0]["source_references"] = []
        edited["parameters"][0]["traceability_status"] = "not_provided"
        summary = calculate_coverage_summary(edited, provenance)
        self.assertEqual(summary["entities_marked_not_provided"], 1)

    def test_trace_validation_errors(self) -> None:
        manifest, _parsed, asot, provenance, output = self.build_fixture()
        broken = copy.deepcopy(provenance)
        broken["provenance_records"].append(dict(broken["provenance_records"][0]))
        broken["provenance_records"][0]["target_entity_ids"] = ["missing-entity"]
        broken["provenance_records"][0]["confidence"] = 1.5
        broken["provenance_records"][0]["evidence_type"] = "page_coordinate"
        broken["source_files"][0]["sha256"] = "0" * 64
        asot["requirements"][0]["source_references"] = ["missing-provenance"]
        report = validate_traceability(asot, broken, output / manifest["extraction_root"])
        joined = "\n".join(report.errors)
        self.assertIn("duplicate provenance ID", joined)
        self.assertIn("nonexistent ASOT entity", joined)
        self.assertIn("nonexistent provenance record", joined)
        self.assertIn("checksum mismatch", joined)
        self.assertIn("invalid confidence", joined)
        self.assertIn("unsupported evidence_type", joined)

    def test_validation_does_not_mutate_inputs(self) -> None:
        manifest, _parsed, asot, provenance, output = self.build_fixture()
        before_asot = copy.deepcopy(asot)
        before_provenance = copy.deepcopy(provenance)
        validate_traceability(asot, provenance, output / manifest["extraction_root"])
        self.assertEqual(asot, before_asot)
        self.assertEqual(provenance, before_provenance)


if __name__ == "__main__":
    unittest.main()
