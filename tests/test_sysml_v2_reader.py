from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from de2sim.ingest.sysml_v2_reader import read_sysml


class SysMLV2ReaderTests(unittest.TestCase):
    def test_textual_subset_parsing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "model.sysml"
            path.write_text("package UAS\npart def Airframe\npart wing\nconnect wing to fuselage\nsatisfy REQ-1 by Airframe\n", encoding="utf-8")
            elements, relationships, warnings = read_sysml(path, "sysml/model.sysml")
            self.assertEqual(warnings, [])
            self.assertEqual([item["kind"] for item in elements], ["package", "part def", "part"])
            self.assertEqual([item["kind"] for item in relationships], ["connect", "satisfy"])

    def test_sysml_json_parsing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "model.sysml.json"
            payload = {
                "elements": [{"kind": "part", "id": "e1", "name": "Battery", "unit": "V"}],
                "relationships": [{"type": "connect", "id": "r1", "source": "Battery", "target": "Bus"}],
            }
            path.write_text(json.dumps(payload), encoding="utf-8")
            elements, relationships, warnings = read_sysml(path, "sysml/model.sysml.json")
            self.assertEqual(warnings, [])
            self.assertEqual(elements[0]["element_id"], "e1")
            self.assertEqual(relationships[0]["source"], "Battery")

    def test_unrecognized_lines_become_warnings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "model.sysml"
            path.write_text("this is not in the supported subset\n", encoding="utf-8")
            elements, relationships, warnings = read_sysml(path, "sysml/model.sysml")
            self.assertEqual(elements, [])
            self.assertEqual(relationships, [])
            self.assertIn("unrecognized SysML subset line", warnings[0])


if __name__ == "__main__":
    unittest.main()
