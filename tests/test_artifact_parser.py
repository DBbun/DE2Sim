from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from de2sim.ingest.artifact_parser import parse_artifacts_from_manifest
from de2sim.ingest.package_reader import ingest_engineering_package


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"
NEW_MODULES = [
    REPO_ROOT / "de2sim" / "ingest" / "artifact_parser.py",
    REPO_ROOT / "de2sim" / "ingest" / "sysml_v2_reader.py",
    REPO_ROOT / "de2sim" / "ingest" / "requirement_reader.py",
    REPO_ROOT / "de2sim" / "ingest" / "parameter_reader.py",
    REPO_ROOT / "de2sim" / "ingest" / "physical_model_reader.py",
]


class ArtifactParserTests(unittest.TestCase):
    def make_zip(self, path: Path, members: dict[str, bytes]) -> None:
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as zf:
            for name, data in members.items():
                zf.writestr(name, data)

    def read_json(self, path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    def test_parse_artifacts_integration_deferred_and_counts(self) -> None:
        with tempfile.TemporaryDirectory(dir=FIXTURES_DIR) as tmp:
            root = Path(tmp)
            package = root / "package.zip"
            output = root / "out"
            self.make_zip(
                package,
                {
                    "requirements/reqs.csv": b"id,text\nREQ-1,Fly safely\n",
                    "parameters/params.yaml": b"mass: 12\nmode: symbolic\n",
                    "sysml/model.sysml": b"package UAS\npart def Airframe\nconnect Airframe to Payload\n",
                    "physical_models/flight.md": b"equation: x = v * t\n",
                    "geometry/body.glb": b"binary-ish",
                    "docs/manual.pdf": b"%PDF",
                    "docs/spec.docx": b"docx",
                    "parameters/table.xlsx": b"xlsx",
                },
            )
            manifest_path = ingest_engineering_package(package, output)
            original_manifest_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
            parsed_path = parse_artifacts_from_manifest(manifest_path)
            parsed = self.read_json(parsed_path)
            manifest = self.read_json(manifest_path)

            self.assertEqual(parsed["package_manifest_sha256"], original_manifest_hash)
            self.assertEqual(parsed["record_counts"]["requirements"], 1)
            self.assertEqual(parsed["record_counts"]["parameters"], 2)
            self.assertEqual(parsed["record_counts"]["sysml_elements"], 2)
            self.assertEqual(parsed["record_counts"]["sysml_relationships"], 1)
            self.assertEqual(parsed["record_counts"]["physical_models"], 1)
            deferred_paths = {item["source_relative_path"] for item in parsed["deferred_files"]}
            self.assertEqual(
                deferred_paths,
                {"geometry/body.glb", "docs/manual.pdf", "docs/spec.docx", "parameters/table.xlsx"},
            )
            statuses = {item["relative_path"]: item["parser_status"] for item in manifest["files"]}
            self.assertEqual(statuses["requirements/reqs.csv"], "parsed")
            self.assertEqual(statuses["geometry/body.glb"], "referenced_not_parsed")
            self.assertEqual(statuses["parameters/table.xlsx"], "deferred")

    def test_deterministic_stable_ids_and_ordering(self) -> None:
        with tempfile.TemporaryDirectory(dir=FIXTURES_DIR) as tmp:
            root = Path(tmp)
            package = root / "package.zip"
            self.make_zip(package, {"requirements/b.csv": b"id,text\nB,B text\n", "requirements/a.csv": b"id,text\nA,A text\n"})
            first_manifest = ingest_engineering_package(package, root / "out1")
            second_manifest = ingest_engineering_package(package, root / "out2")
            first = self.read_json(parse_artifacts_from_manifest(first_manifest))
            second = self.read_json(parse_artifacts_from_manifest(second_manifest))
            first_ids = [item["stable_id"] for item in first["requirements"]]
            second_ids = [item["stable_id"] for item in second["requirements"]]
            self.assertEqual(first_ids, second_ids)
            self.assertEqual([item["source_relative_path"] for item in first["requirements"]], ["requirements/a.csv", "requirements/b.csv"])

    def test_malformed_json_and_unsupported_yaml_are_controlled(self) -> None:
        with tempfile.TemporaryDirectory(dir=FIXTURES_DIR) as tmp:
            root = Path(tmp)
            package = root / "package.zip"
            self.make_zip(package, {"requirements/bad.json": b"{bad", "parameters/bad.yaml": b"base: &anchor 1\ncopy: *anchor\n"})
            manifest_path = ingest_engineering_package(package, root / "out")
            parsed = self.read_json(parse_artifacts_from_manifest(manifest_path))
            joined = "\n".join(parsed["warnings"])
            self.assertIn("malformed JSON", joined)
            self.assertIn("outside the supported subset", joined)

    def test_cli_parse_artifacts_prints_both_paths(self) -> None:
        with tempfile.TemporaryDirectory(dir=FIXTURES_DIR) as tmp:
            root = Path(tmp)
            package = root / "package.zip"
            output = root / "out"
            self.make_zip(package, {"requirements/reqs.csv": b"id,text\nR1,Do thing\n"})
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "de2sim.cli.challenge_pipeline",
                    "--engineering-package",
                    str(package),
                    "--output",
                    str(output),
                    "--parse-artifacts",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            lines = result.stdout.strip().splitlines()
            self.assertEqual(lines, [str(output / "package_manifest.json"), str(output / "parsed_artifacts.json")])

    def test_new_ingestion_modules_do_not_call_forbidden_runtime_hooks(self) -> None:
        for module_path in NEW_MODULES:
            with self.subTest(module=module_path.name):
                tree = ast.parse(module_path.read_text(encoding="utf-8"))
                for node in ast.walk(tree):
                    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                        self.assertNotIn(node.func.id, {"eval", "exec"}, f"{module_path} calls {node.func.id}")


if __name__ == "__main__":
    unittest.main()
