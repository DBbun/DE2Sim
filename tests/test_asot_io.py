from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from de2sim.asot.io import ASOTIOError, asot_json_text, read_asot_json, write_asot_json
from tests.test_asot_schema import representative_asot


class ASOTIOTests(unittest.TestCase):
    def test_deterministic_json_output(self) -> None:
        document = representative_asot()
        first = asot_json_text(document)
        second = asot_json_text(document)
        self.assertEqual(first, second)
        self.assertTrue(first.endswith("\n"))
        self.assertIn('\n  "schema_version": "de2sim.asot.v1"', first)
        self.assertLess(first.index('"components"'), first.index('"requirements"'))

    def test_json_round_trip_preserves_normalized_asot(self) -> None:
        document = representative_asot()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "asot.json"
            write_asot_json(document, path)
            loaded = read_asot_json(path)
            self.assertEqual(loaded.to_dict(), document.to_dict())
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), document.to_dict())

    def test_malformed_json_controlled_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.json"
            path.write_text("{bad", encoding="utf-8")
            with self.assertRaisesRegex(ASOTIOError, "malformed ASOT JSON"):
                read_asot_json(path)

    def test_write_uses_utf8_and_no_absolute_temp_paths_in_json(self) -> None:
        document = representative_asot()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nested" / "asot.json"
            write_asot_json(document, path)
            raw = path.read_bytes()
            self.assertEqual(raw.decode("utf-8"), path.read_text(encoding="utf-8"))
            payload = json.loads(path.read_text(encoding="utf-8"))
            text = json.dumps(payload)
            self.assertNotIn(str(Path(tmp)), text)
            self.assertFalse(any(path.parent.glob("*.tmp")))


if __name__ == "__main__":
    unittest.main()
