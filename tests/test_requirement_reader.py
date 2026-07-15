from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from de2sim.ingest.requirement_reader import read_requirements


class RequirementReaderTests(unittest.TestCase):
    def test_csv_parsing_with_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "reqs.csv"
            path.write_text("req_id,name,requirement,verification,priority\nREQ-001,Fly,Vehicle shall fly,Test,High\n", encoding="utf-8")
            records, warnings = read_requirements(path, "requirements/reqs.csv")
            self.assertEqual(warnings, [])
            self.assertEqual(records[0]["requirement_id"], "REQ-001")
            self.assertEqual(records[0]["title"], "Fly")
            self.assertEqual(records[0]["text"], "Vehicle shall fly")
            self.assertEqual(records[0]["verification_method"], "Test")

    def test_json_top_level_variants(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "reqs.json"
            path.write_text(json.dumps({"requirements": [{"id": "REQ-002", "description": "Land safely"}]}), encoding="utf-8")
            records, warnings = read_requirements(path, "requirements/reqs.json")
            self.assertEqual(warnings, [])
            self.assertEqual(records[0]["requirement_id"], "REQ-002")
            self.assertEqual(records[0]["text"], "Land safely")

    def test_text_and_markdown_parsing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "reqs.md"
            path.write_text("# Navigation\nREQ-003 shall hold waypoint.\n\nOne requirement per line.\n", encoding="utf-8")
            records, warnings = read_requirements(path, "requirements/reqs.md")
            self.assertEqual(warnings, [])
            self.assertEqual(records[0]["title"], "Navigation")
            self.assertEqual(records[0]["requirement_id"], "REQ-003")
            self.assertEqual(records[1]["text"], "One requirement per line.")


if __name__ == "__main__":
    unittest.main()
