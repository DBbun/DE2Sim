from __future__ import annotations

import ast
import hashlib
import tempfile
import unittest
from pathlib import Path

from de2sim.provenance.hashing import HashingError, sha256_bytes, sha256_file, sha256_normalized_json


REPO_ROOT = Path(__file__).resolve().parents[1]
NEW_MODULES = [
    REPO_ROOT / "de2sim" / "provenance" / "hashing.py",
    REPO_ROOT / "de2sim" / "provenance" / "trace.py",
    REPO_ROOT / "de2sim" / "provenance" / "manifest.py",
]


class ProvenanceHashingTests(unittest.TestCase):
    def test_bytes_sha256(self) -> None:
        self.assertEqual(sha256_bytes(b"abc"), hashlib.sha256(b"abc").hexdigest())

    def test_file_sha256_and_chunked_reading(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "large.bin"
            path.write_bytes(b"abc" * 10000)
            self.assertEqual(sha256_file(path, chunk_size=7), hashlib.sha256(path.read_bytes()).hexdigest())

    def test_normalized_json_sha256_is_deterministic(self) -> None:
        first = {"b": [2, 1], "a": {"z": True}}
        second = {"a": {"z": True}, "b": [2, 1]}
        self.assertEqual(sha256_normalized_json(first), sha256_normalized_json(second))

    def test_missing_file_is_controlled_error(self) -> None:
        with self.assertRaises(HashingError):
            sha256_file(Path("missing-file-does-not-exist.txt"))

    def test_no_eval_or_exec_in_phase3a_modules(self) -> None:
        for module_path in NEW_MODULES:
            tree = ast.parse(module_path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    self.assertNotIn(node.func.id, {"eval", "exec"}, f"{module_path} calls {node.func.id}")


if __name__ == "__main__":
    unittest.main()
