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
from de2sim.provenance.manifest import build_provenance_manifest, traceability_markdown, write_provenance_outputs
from de2sim.provenance.trace import validate_traceability
from tests.test_asot_builder import make_zip, representative_members


FIXTURES_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class ProvenanceManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp_roots: list[Path] = []

    def tearDown(self) -> None:
        for root in self._temp_roots:
            shutil.rmtree(root, ignore_errors=True)

    def build_paths(self) -> tuple[Path, Path, Path, Path, dict, dict, dict]:
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
        return root, manifest_path, parsed_path, asot_path, read_json(manifest_path), read_json(parsed_path), read_json(asot_path)

    def test_manifest_shape_ordering_and_source_files(self) -> None:
        _root, manifest_path, parsed_path, asot_path, manifest, parsed, asot = self.build_paths()
        provenance = build_provenance_manifest(asot, manifest, parsed, manifest_path, parsed_path, asot_path)
        self.assertEqual(provenance["schema_version"], "de2sim.provenance_manifest.v1")
        self.assertEqual(provenance["asot_id"], asot["asot_id"])
        self.assertIn("package_manifest_sha256", provenance)
        self.assertEqual(
            [item["source_relative_path"] for item in provenance["source_files"]],
            sorted(item["source_relative_path"] for item in provenance["source_files"]),
        )
        self.assertEqual(
            [item["provenance_id"] for item in provenance["provenance_records"]],
            sorted(item["provenance_id"] for item in provenance["provenance_records"]),
        )
        for record in provenance["provenance_records"]:
            self.assertEqual(record["target_entity_ids"], sorted(record["target_entity_ids"]))
            self.assertEqual(record["warnings"], sorted(record["warnings"]))

    def test_deterministic_manifest_excluding_timestamp(self) -> None:
        _root, manifest_path, parsed_path, asot_path, manifest, parsed, asot = self.build_paths()
        first = build_provenance_manifest(asot, manifest, parsed, manifest_path, parsed_path, asot_path)
        second = build_provenance_manifest(asot, manifest, parsed, manifest_path, parsed_path, asot_path)
        first["generated_at_utc"] = "<runtime>"
        second["generated_at_utc"] = "<runtime>"
        self.assertEqual(first, second)

    def test_write_outputs_and_markdown_limitations(self) -> None:
        root, manifest_path, parsed_path, asot_path, manifest, parsed, asot = self.build_paths()
        outputs = write_provenance_outputs(asot, manifest, parsed, root / "out", manifest_path, parsed_path, asot_path)
        for path in outputs.values():
            self.assertTrue(path.is_file(), path)
        report = read_json(outputs["traceability_report_json"])
        self.assertTrue(report["valid"], report)
        markdown = outputs["traceability_report_md"].read_text(encoding="utf-8")
        self.assertIn("ASOT ID", markdown)
        self.assertIn("Overall traceability", markdown)
        self.assertIn("does not claim exact replayability", markdown)

    def test_missing_source_file_detection(self) -> None:
        root, _manifest_path, _parsed_path, _asot_path, manifest, parsed, asot = self.build_paths()
        provenance = build_provenance_manifest(asot, manifest, parsed, root / "out" / "package_manifest.json", root / "out" / "parsed_artifacts.json", root / "out" / "asot.json")
        missing = root / "out" / "work" / "package" / "requirements" / "reqs.csv"
        missing.unlink()
        report = validate_traceability(asot, provenance, root / "out" / manifest["extraction_root"])
        self.assertFalse(report.valid)
        self.assertIn("requirements/reqs.csv", report.missing_source_files)

    def test_markdown_renderer_accepts_empty_sections(self) -> None:
        markdown = traceability_markdown(
            {"asot_id": "asot-empty"},
            {"package_filename": "empty.zip"},
            {"provenance_records": []},
            {"valid": True, "coverage_summary": {}, "entities_without_provenance": [], "checksum_mismatches": [], "missing_source_files": []},
            {"deferred_files": []},
        )
        self.assertIn("Explicit Limitations", markdown)


if __name__ == "__main__":
    unittest.main()
