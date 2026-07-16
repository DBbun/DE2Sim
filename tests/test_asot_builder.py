from __future__ import annotations

import ast
import copy
import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from de2sim.asot.builder import build_asot, build_asot_from_files, write_asot_outputs
from de2sim.asot.schema import ASOTDocument, ASOTMetadata, Component, SUPPORTED_SCHEMA_VERSION, stable_id
from de2sim.asot.validators import validate_asot
from de2sim.ingest.artifact_parser import parse_artifacts_from_manifest
from de2sim.ingest.package_reader import ingest_engineering_package


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"
BUILDER_MODULE = REPO_ROOT / "de2sim" / "asot" / "builder.py"


def make_zip(path: Path, members: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as zf:
        for name, data in members.items():
            zf.writestr(name, data)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def normalized_asot(payload: dict) -> dict:
    data = copy.deepcopy(payload)
    data["metadata"]["created_at_utc"] = "<runtime>"
    return data


def representative_members() -> dict[str, bytes]:
    sysml = {
        "elements": [
            {"kind": "package", "id": "uas", "name": "UAS"},
            {"kind": "part def", "id": "airframe", "name": "Airframe", "owner": "uas", "description": "Primary structure"},
            {"kind": "part", "id": "payload", "name": "Payload", "owner": "airframe"},
            {"kind": "port", "id": "payload_port", "name": "PayloadPort", "owner": "airframe"},
            {"kind": "action", "id": "loiter", "name": "Loiter"},
            {"kind": "attribute", "id": "ignored", "name": "NotAComponent"},
        ],
        "relationships": [
            {"kind": "connect", "source": "Airframe", "target": "Payload", "description": "payload bus"},
            {"kind": "satisfy", "source": "Airframe", "target": "REQ-1"},
            {"kind": "verify", "source": "Loiter", "target": "REQ-1"},
            {"kind": "satisfy", "source": "Missing", "target": "REQ-404", "description": "unresolved"},
        ],
    }
    physical = {
        "physical_models": [
            {
                "id": "lift",
                "name": "Lift relation",
                "equation": "lift = q * s * cl",
                "variables": ["lift", "q", "s", "cl"],
                "parameters": ["mass"],
                "assumptions": ["subsonic"],
                "description": "Do not evaluate this equation.",
            }
        ]
    }
    parameters = {
        "parameters": [
            {"id": "P-1", "name": "mass", "value": 12.5, "unit": "kg", "minimum": 1, "maximum": 20, "description": "Mass"},
            {"id": "P-2", "name": "mode", "value": "m_airframe", "unit": "kg"},
        ]
    }
    return {
        "requirements/reqs.csv": b"id,title,text,verification_method,priority\nREQ-1,Safe flight,Vehicle shall fly safely,test,high\n",
        "parameters/params.json": json.dumps(parameters).encode("utf-8"),
        "sysml/model.sysml.json": json.dumps(sysml).encode("utf-8"),
        "physical_models/flight.json": json.dumps(physical).encode("utf-8"),
        "geometry/body.glb": b"glb-bytes",
    }


class ASOTBuilderTests(unittest.TestCase):
    def build_representative(self) -> tuple[dict, dict, ASOTDocument]:
        with tempfile.TemporaryDirectory(dir=FIXTURES_DIR) as tmp:
            root = Path(tmp)
            package = root / "uas.zip"
            make_zip(package, representative_members())
            manifest_path = ingest_engineering_package(package, root / "out")
            parsed_path = parse_artifacts_from_manifest(manifest_path)
            manifest = read_json(manifest_path)
            parsed = read_json(parsed_path)
            document = build_asot_from_files(manifest_path, parsed_path)
            return manifest, parsed, document

    def test_minimal_package_builds_valid_asot(self) -> None:
        with tempfile.TemporaryDirectory(dir=FIXTURES_DIR) as tmp:
            root = Path(tmp)
            package = root / "minimal.zip"
            make_zip(package, {"requirements/reqs.csv": b"id,text\nREQ-1,Keep records\n"})
            manifest_path = ingest_engineering_package(package, root / "out")
            parsed_path = parse_artifacts_from_manifest(manifest_path)
            document = build_asot_from_files(manifest_path, parsed_path)

            result = validate_asot(document)
            self.assertTrue(result.ok, result.errors)
            self.assertEqual(document.metadata.title, "minimal")
            self.assertEqual(document.metadata.source_package_filename, "minimal.zip")
            self.assertEqual(document.metadata.source_package_sha256, hashlib.sha256(package.read_bytes()).hexdigest())
            self.assertEqual(document.schema_version, SUPPORTED_SCHEMA_VERSION)

    def test_representative_mapping_is_conservative_and_source_derived(self) -> None:
        _manifest, _parsed, document = self.build_representative()
        payload = document.to_dict()
        self.assertTrue(validate_asot(document).ok, document.validation.errors)
        self.assertEqual(len(payload["requirements"]), 1)
        self.assertEqual(payload["requirements"][0]["requirement_id"], "REQ-1")
        self.assertEqual(payload["requirements"][0]["text"], "Vehicle shall fly safely")
        self.assertEqual(payload["requirements"][0]["verification_method"], "test")
        self.assertEqual(payload["requirements"][0]["priority"], "high")

        parameters = {item["name"]: item for item in payload["parameters"]}
        self.assertEqual(parameters["mass"]["value"], 12.5)
        self.assertEqual(parameters["mass"]["unit"], "kg")
        self.assertEqual(parameters["mass"]["minimum"], 1)
        self.assertEqual(parameters["mass"]["maximum"], 20)
        self.assertIsNone(parameters["mode"]["value"])
        self.assertEqual(parameters["mode"]["symbolic_expression"], "m_airframe")

        components = {item["name"]: item for item in payload["components"]}
        self.assertEqual(set(components), {"Airframe", "Payload", "UAS"})
        self.assertNotIn("NotAComponent", components)
        self.assertEqual(components["Payload"]["parent_component_id"], components["Airframe"]["stable_id"])

        self.assertEqual(payload["behaviors"][0]["name"], "Loiter")
        self.assertEqual(payload["behaviors"][0]["generated_by"], "source")
        self.assertEqual(payload["behaviors"][0]["approval_status"], "approved")
        self.assertEqual(payload["physical_models"][0]["equation"], "lift = q * s * cl")
        self.assertEqual(payload["physical_models"][0]["parameter_ids"], [parameters["mass"]["stable_id"]])
        self.assertEqual(payload["geometry"][0]["parser_status"], "referenced_not_parsed")
        self.assertEqual(payload["geometry"][0]["source_relative_path"], "geometry/body.glb")
        self.assertGreaterEqual(len(payload["provenance"]), 5)
        self.assertIn("unresolved satisfy relationship", "\n".join(document.validation.warnings))

    def test_explicit_interface_fields_preserved_when_parsed_records_contain_them(self) -> None:
        manifest = {
            "package_filename": "direct.zip",
            "package_sha256": "a" * 64,
            "files": [{"relative_path": "sysml/model.sysml.json", "role": "sysml", "sha256": "b" * 64}],
        }
        parsed = {
            "package_filename": "direct.zip",
            "sysml_elements": [
                {
                    "stable_id": "source-port",
                    "source_relative_path": "sysml/model.sysml.json",
                    "source_locator": "json:0",
                    "parser_name": "test",
                    "kind": "port",
                    "element_id": "p1",
                    "name": "PowerPort",
                    "direction": "out",
                    "exchanged_items": ["power"],
                }
            ],
        }
        document = build_asot(manifest, parsed, "c" * 64)
        interface = document.to_dict()["interfaces"][0]
        self.assertEqual(interface["direction"], "out")
        self.assertEqual(interface["exchanged_items"], ["power"])

    def test_deterministic_ids_and_ordering(self) -> None:
        with tempfile.TemporaryDirectory(dir=FIXTURES_DIR) as tmp:
            root = Path(tmp)
            package = root / "uas.zip"
            make_zip(package, representative_members())
            first_manifest = ingest_engineering_package(package, root / "out1")
            second_manifest = ingest_engineering_package(package, root / "out2")
            first_parsed = parse_artifacts_from_manifest(first_manifest)
            second_parsed = parse_artifacts_from_manifest(second_manifest)
            first = build_asot_from_files(first_manifest, first_parsed).to_dict()
            second = build_asot_from_files(second_manifest, second_parsed).to_dict()

            self.assertEqual(normalized_asot(first), normalized_asot(second))
            for section in ("components", "requirements", "interfaces", "parameters", "physical_models", "behaviors", "geometry"):
                ids = [item["stable_id"] for item in first[section]]
                self.assertEqual(ids, sorted(ids))
                self.assertEqual(ids, [item["stable_id"] for item in second[section]])
            self.assertEqual(first["asot_id"], second["asot_id"])

    def test_duplicate_source_record_handling(self) -> None:
        manifest = {"package_filename": "dup.zip", "package_sha256": "a" * 64, "files": []}
        record = {
            "source_relative_path": "requirements/reqs.csv",
            "source_locator": "row:2",
            "parser_name": "requirement_reader.phase1b",
            "requirement_id": "REQ-1",
            "title": "Title",
            "text": "Same text",
        }
        document = build_asot(manifest, {"package_filename": "dup.zip", "requirements": [record, dict(record)]}, "b" * 64)
        self.assertEqual(len(document.requirements), 1)

    def test_no_invented_ownership_or_relationships(self) -> None:
        _manifest, _parsed, document = self.build_representative()
        payload = document.to_dict()
        self.assertTrue(all(not item["owning_component_id"] for item in payload["parameters"]))
        self.assertTrue(all(not item["owning_component_id"] for item in payload["geometry"]))
        self.assertTrue(all(not item["owning_component_ids"] for item in payload["physical_models"]))

    def test_invalid_asot_outputs_invalid_file_and_validation_report(self) -> None:
        document = ASOTDocument(
            schema_version=SUPPORTED_SCHEMA_VERSION,
            asot_id=stable_id("asot", {"bad": True}),
            metadata=ASOTMetadata(
                title="Bad",
                created_at_utc="2026-07-15T00:00:00Z",
                source_package_filename="bad.zip",
                source_package_sha256="a" * 64,
                parsed_artifacts_sha256="b" * 64,
                generator_name="test",
                generator_version="test",
            ),
            components=[Component(stable_id="component-a", name="A", child_component_ids=["missing"])],
        )
        with tempfile.TemporaryDirectory(dir=FIXTURES_DIR) as tmp:
            outputs = write_asot_outputs(document, Path(tmp), {})
            self.assertEqual(outputs["asot"].name, "asot_invalid.json")
            self.assertFalse((Path(tmp) / "asot.json").exists())
            validation = read_json(outputs["validation"])
            self.assertFalse(validation["valid"])
            self.assertIn("nonexistent child_component_id", "\n".join(validation["errors"]))

    def test_new_phase2b_code_does_not_call_eval_or_exec(self) -> None:
        tree = ast.parse(BUILDER_MODULE.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                self.assertNotIn(node.func.id, {"eval", "exec"})


if __name__ == "__main__":
    unittest.main()
