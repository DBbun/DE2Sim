from __future__ import annotations

import unittest

from de2sim.ingest.geometry_manifest import (
    classify_package_member,
    normalized_extension,
    parser_status_for_role,
)


class GeometryManifestTests(unittest.TestCase):
    def test_geometry_recognition_by_extension(self) -> None:
        role, warnings = classify_package_member("vehicle/body.glb")
        self.assertEqual(role, "geometry")
        self.assertEqual(warnings, [])
        self.assertEqual(normalized_extension("vehicle/body.glb"), ".glb")
        self.assertEqual(parser_status_for_role(role), "referenced_not_parsed")

    def test_sysml_compound_extension(self) -> None:
        role, warnings = classify_package_member("system/model.sysml.json")
        self.assertEqual(role, "sysml")
        self.assertEqual(warnings, [])
        self.assertEqual(normalized_extension("system/model.sysml.json"), ".sysml.json")

    def test_folder_based_classification(self) -> None:
        cases = {
            "parameters/flight.csv": "parameters",
            "physical_models/dynamics.md": "physical_model",
            "requirements/needs.txt": "requirements",
            "docs/interface.json": "documentation",
        }
        for path, expected_role in cases.items():
            with self.subTest(path=path):
                role, _ = classify_package_member(path)
                self.assertEqual(role, expected_role)

    def test_unsupported_file_is_preserved_role(self) -> None:
        role, warnings = classify_package_member("misc/blob.bin")
        self.assertEqual(role, "unsupported")
        self.assertEqual(warnings, [])
        self.assertEqual(parser_status_for_role(role), "unsupported")


if __name__ == "__main__":
    unittest.main()
