from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from de2sim.ingest.physical_model_reader import read_physical_models


class PhysicalModelReaderTests(unittest.TestCase):
    def test_explicit_equation_extraction(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "flight.md"
            path.write_text("Lift = 0.5 * rho * v^2 * S * Cl\nformula: drag = Cd * q * S\n", encoding="utf-8")
            records, warnings = read_physical_models(path, "physical_models/flight.md")
            self.assertEqual(warnings, [])
            self.assertEqual(len(records), 2)
            self.assertIn("Lift =", records[0]["equation"])
            self.assertEqual(records[1]["equation"], "drag = Cd * q * S")

    def test_no_inferred_equations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "notes.txt"
            path.write_text("Lift depends on speed and density.\n", encoding="utf-8")
            records, warnings = read_physical_models(path, "physical_models/notes.txt")
            self.assertEqual(warnings, [])
            self.assertEqual(records, [])


if __name__ == "__main__":
    unittest.main()
