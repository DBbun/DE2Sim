from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from de2sim.ingest.parameter_reader import read_parameters


class ParameterReaderTests(unittest.TestCase):
    def test_csv_parsing_preserves_units(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "params.csv"
            path.write_text("id,name,value,unit,min,max\nP1,mass,12.5,kg,1,20\n", encoding="utf-8")
            records, warnings = read_parameters(path, "parameters/params.csv")
            self.assertEqual(warnings, [])
            self.assertEqual(records[0]["value"], 12.5)
            self.assertEqual(records[0]["unit"], "kg")
            self.assertEqual(records[0]["minimum"], 1)

    def test_json_parsing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "params.json"
            path.write_text(json.dumps({"parameters": [{"name": "speed", "value": "Mach 0.3", "unit": "Mach"}]}), encoding="utf-8")
            records, warnings = read_parameters(path, "parameters/params.json")
            self.assertEqual(warnings, [])
            self.assertEqual(records[0]["value"], "Mach 0.3")
            self.assertEqual(records[0]["unit"], "Mach")

    def test_simple_yaml_scalar_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "params.yaml"
            path.write_text("mass: 12\nmode: hover\n", encoding="utf-8")
            records, warnings = read_parameters(path, "parameters/params.yaml")
            self.assertEqual(warnings, [])
            values = {record["name"]: record["value"] for record in records}
            self.assertEqual(values["mass"], 12)
            self.assertEqual(values["mode"], "hover")

    def test_numeric_and_symbolic_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "params.csv"
            path.write_text("name,value\ncount,3\nlimit,N/A\n", encoding="utf-8")
            records, _ = read_parameters(path, "parameters/params.csv")
            values = {record["name"]: record["value"] for record in records}
            self.assertEqual(values["count"], 3)
            self.assertEqual(values["limit"], "N/A")


if __name__ == "__main__":
    unittest.main()
