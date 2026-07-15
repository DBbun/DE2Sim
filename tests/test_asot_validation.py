from __future__ import annotations

import copy
import subprocess
import unittest
from pathlib import Path

from de2sim.asot.schema import Behavior, Component, SUPPORTED_SCHEMA_VERSION
from de2sim.asot.validators import validate_asot
from tests.test_asot_schema import representative_asot


REPO_ROOT = Path(__file__).resolve().parents[1]
LEGACY_SCRIPT = REPO_ROOT / "paper_to_simulator_builder_v3_4.py"


class ASOTValidationTests(unittest.TestCase):
    def test_duplicate_ids(self) -> None:
        document = representative_asot()
        document.parameters[0].stable_id = document.components[0].stable_id
        result = validate_asot(document)
        self.assertIn("duplicate stable ID", "\n".join(result.errors))

    def test_broken_references(self) -> None:
        document = representative_asot()
        document.requirements[0].satisfied_by_ids = ["missing-component"]
        document.interfaces[0].target_component_id = "missing-target"
        result = validate_asot(document)
        joined = "\n".join(result.errors)
        self.assertIn("nonexistent satisfied_by_id", joined)
        self.assertIn("nonexistent target_component_id", joined)

    def test_invalid_ownership(self) -> None:
        document = representative_asot()
        document.parameters[0].owning_component_id = "missing-owner"
        document.behaviors[0].owning_component_id = "missing-owner"
        document.geometry[0].owning_component_id = "missing-owner"
        document.physical_models[0].owning_component_ids = ["missing-owner"]
        document.physical_models[0].parameter_ids = ["missing-parameter"]
        result = validate_asot(document)
        joined = "\n".join(result.errors)
        self.assertIn("parameter", joined)
        self.assertIn("behavior", joined)
        self.assertIn("geometry", joined)
        self.assertIn("physical model", joined)

    def test_invalid_component_hierarchy(self) -> None:
        document = representative_asot()
        document.components[1].parent_component_id = "missing-parent"
        document.components[0].child_component_ids.append(document.components[0].stable_id)
        result = validate_asot(document)
        joined = "\n".join(result.errors)
        self.assertIn("nonexistent parent_component_id", joined)
        self.assertIn("cannot be its own child", joined)
        self.assertIn("not mirrored by child parent_component_id", joined)

    def test_invalid_component_interface_relationship(self) -> None:
        document = representative_asot()
        document.components[0].interface_ids = ["missing-interface"]
        result = validate_asot(document)
        self.assertIn("nonexistent interface_ids", "\n".join(result.errors))

    def test_invalid_approval_status(self) -> None:
        document = representative_asot()
        document.behaviors[0].approval_status = "auto-approved"
        result = validate_asot(document)
        self.assertIn("invalid approval_status", "\n".join(result.errors))

    def test_unsupported_schema_version(self) -> None:
        document = representative_asot()
        document.schema_version = "de2sim.asot.v999"
        result = validate_asot(document)
        self.assertIn("unsupported schema_version", "\n".join(result.errors))

    def test_missing_required_top_level_fields_fail_validation(self) -> None:
        payload = representative_asot().to_dict()
        payload.pop("components")
        result = validate_asot(payload)
        self.assertIn("missing required top-level field: components", result.errors)

    def test_validator_does_not_mutate_input(self) -> None:
        document = representative_asot()
        before = copy.deepcopy(document.to_dict())
        validate_asot(document)
        self.assertEqual(document.to_dict(), before)

    def test_errors_and_warnings_are_separate(self) -> None:
        document = representative_asot()
        document.components[0].source_references = ["missing-provenance"]
        result = validate_asot(document)
        self.assertEqual(result.errors, [])
        self.assertIn("source reference", "\n".join(result.warnings))

    def test_original_dbbun_file_unchanged(self) -> None:
        before = LEGACY_SCRIPT.read_bytes()
        document = representative_asot()
        validate_asot(document)
        after = LEGACY_SCRIPT.read_bytes()
        self.assertEqual(after, before)
        diff = subprocess.run(
            ["git", "diff", "--", str(LEGACY_SCRIPT.relative_to(REPO_ROOT))],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(diff.returncode, 0, diff.stderr)
        self.assertEqual(diff.stdout, "")

    def test_empty_asot_dict_sections_are_valid(self) -> None:
        payload = {
            "schema_version": SUPPORTED_SCHEMA_VERSION,
            "asot_id": "asot-empty",
            "metadata": {
                "title": "Empty",
                "created_at_utc": "",
                "source_package_filename": "",
                "source_package_sha256": "",
                "parsed_artifacts_sha256": "",
                "generator_name": "",
                "generator_version": "",
            },
            "components": [],
            "requirements": [],
            "interfaces": [],
            "parameters": [],
            "physical_models": [],
            "behaviors": [],
            "geometry": [],
            "provenance": [],
            "validation": {"errors": [], "warnings": []},
        }
        self.assertTrue(validate_asot(payload).ok)

    def test_invalid_dict_list_sections_are_reported(self) -> None:
        payload = representative_asot().to_dict()
        payload["behaviors"] = {}
        result = validate_asot(payload)
        self.assertIn("top-level field must be a list: behaviors", result.errors)

    def test_dataclass_imports_available_for_phase2a(self) -> None:
        self.assertTrue(Component)
        self.assertTrue(Behavior)


if __name__ == "__main__":
    unittest.main()
