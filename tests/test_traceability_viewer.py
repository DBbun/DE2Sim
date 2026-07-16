from __future__ import annotations

import ast
import copy
import json
import tempfile
import unittest
from pathlib import Path

from de2sim.asot.builder import build_asot_from_files
from de2sim.ingest.artifact_parser import parse_artifacts_from_manifest
from de2sim.ingest.package_reader import ingest_engineering_package
from de2sim.provenance.manifest import build_provenance_manifest
from de2sim.provenance.trace import validate_traceability
from de2sim.visualization.traceability_viewer import EVIDENCE_TEXT_MAX_CHARS, build_viewer_data, render_viewer_html
from tests.test_asot_builder import make_zip, representative_members


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"
VIEWER_MODULE = REPO_ROOT / "de2sim" / "visualization" / "traceability_viewer.py"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def without_timestamp(payload: dict) -> dict:
    data = copy.deepcopy(payload)
    data["generated_at_utc"] = "<runtime>"
    return data


class TraceabilityViewerTests(unittest.TestCase):
    def build_bundle(self) -> tuple[dict, dict, dict]:
        with tempfile.TemporaryDirectory(dir=FIXTURES_DIR) as tmp:
            root = Path(tmp)
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
            report = validate_traceability(asot, provenance, output / manifest["extraction_root"]).to_dict()
            return asot, provenance, report

    def test_viewer_data_generation_ordering_layout_metrics_and_edges(self) -> None:
        asot, provenance, report = self.build_bundle()
        first = build_viewer_data(asot, provenance, report)
        second = build_viewer_data(asot, provenance, report)
        self.assertEqual(without_timestamp(first), without_timestamp(second))

        self.assertEqual([node["node_id"] for node in first["nodes"]], sorted(node["node_id"] for node in first["nodes"]))
        self.assertEqual([edge["edge_id"] for edge in first["edges"]], sorted(edge["edge_id"] for edge in first["edges"]))
        self.assertTrue(all("layout" in node for node in first["nodes"]))
        self.assertGreater(first["metrics"]["traceability_percentage"], 0.0)
        self.assertEqual(first["metrics"]["components"], len(asot["components"]))
        self.assertEqual(first["metrics"]["provenance_records"], len(provenance["provenance_records"]))

        relationships = {edge["relationship_type"] for edge in first["edges"]}
        self.assertIn("requirement-satisfied-by", relationships)
        self.assertIn("requirement-verified-by", relationships)
        self.assertIn("physical-model-parameter", relationships)
        self.assertIn("entity-provenance", relationships)
        self.assertIn("provenance-source-file", relationships)

    def test_explicit_relationships_only_and_no_invented_edges(self) -> None:
        asot, provenance, report = self.build_bundle()
        data = build_viewer_data(asot, provenance, report)
        parameter_ids = {item["stable_id"] for item in asot["parameters"]}
        component_ids = {item["stable_id"] for item in asot["components"]}
        invented_component_parameter = [
            edge
            for edge in data["edges"]
            if edge["relationship_type"] == "component-parameter"
            and edge["source_node_id"].split(":", 1)[1] in component_ids
            and edge["target_node_id"].split(":", 1)[1] in parameter_ids
        ]
        self.assertEqual(invented_component_parameter, [])

    def test_entity_details_source_evidence_and_gaps_are_preserved(self) -> None:
        asot, provenance, report = self.build_bundle()
        data = build_viewer_data(asot, provenance, report)
        req = next(node for node in data["nodes"] if node["entity_type"] == "requirement")
        self.assertEqual(req["fields"]["requirement_id"], "REQ-1")
        self.assertEqual(req["fields"]["text"], "Vehicle shall fly safely")
        self.assertTrue(req["provenance_ids"])

        evidence = next(node for node in data["nodes"] if node["entity_type"] == "provenance")
        self.assertIn("source_relative_path", evidence["fields"])
        self.assertIn("evidence_text", evidence["fields"])

        modified_report = copy.deepcopy(report)
        modified_report["broken_provenance_references"] = ["requirement-x->provenance-missing"]
        modified_report["checksum_mismatches"] = [{"source_relative_path": "requirements/reqs.csv", "expected_sha256": "a", "actual_sha256": "b"}]
        with_gaps = build_viewer_data(asot, provenance, modified_report)
        self.assertEqual(with_gaps["metrics"]["broken_reference_count"], 1)
        self.assertEqual(with_gaps["metrics"]["checksum_mismatch_count"], 1)
        self.assertTrue(any(item["gap_type"] == "broken-reference" for item in with_gaps["traceability_gaps"]))

    def test_html_generation_is_standalone_embeds_data_and_avoids_unsafe_constructs(self) -> None:
        asot, provenance, report = self.build_bundle()
        data = build_viewer_data(asot, provenance, report)
        html = render_viewer_html(data)
        self.assertIn('<script id="viewer-data" type="application/json">', html)
        self.assertNotIn('src="http', html)
        self.assertNotIn("href=\"http", html)
        self.assertNotIn("<link", html.lower())
        self.assertNotIn("eval(", html)
        self.assertNotIn("exec(", html)
        self.assertNotIn("Function(", html)
        self.assertNotIn("innerHTML", html)

    def test_source_text_escaping_truncation_and_no_unrelated_absolute_paths(self) -> None:
        asot, provenance, report = self.build_bundle()
        provenance = copy.deepcopy(provenance)
        record = provenance["provenance_records"][0]
        record["evidence_text"] = "</script><img src=x>" + ("x" * (EVIDENCE_TEXT_MAX_CHARS + 20))
        record["source_relative_path"] = r"C:\Users\karto\secret\reqs.csv"
        data = build_viewer_data(asot, provenance, report)
        node = next(item for item in data["nodes"] if item["entity_type"] == "provenance" and item["entity_id"] == record["provenance_id"])
        self.assertTrue(node["fields"]["evidence_text_truncated"])
        self.assertLessEqual(len(node["fields"]["evidence_text"]), EVIDENCE_TEXT_MAX_CHARS + len("\n[truncated]"))
        self.assertNotIn("C:\\", json.dumps(data))
        html = render_viewer_html(data)
        self.assertNotIn("</script><img", html)
        self.assertIn("<\\/script>", html)

    def test_viewer_module_does_not_call_eval_exec_or_function_constructor(self) -> None:
        tree = ast.parse(VIEWER_MODULE.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    self.assertNotIn(node.func.id, {"eval", "exec", "Function"})


if __name__ == "__main__":
    unittest.main()

