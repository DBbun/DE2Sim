from __future__ import annotations

import importlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
LEGACY_SCRIPT = REPO_ROOT / "paper_to_simulator_builder_v3_4.py"
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"


class Phase0ScaffoldTests(unittest.TestCase):
    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "de2sim.cli.challenge_pipeline", *args],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_module_imports(self) -> None:
        module = importlib.import_module("de2sim.cli.challenge_pipeline")
        self.assertTrue(callable(module.main))

    def test_version(self) -> None:
        result = self.run_cli("--version")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("DE2Sim v0.6.0-phase6a", result.stdout)
        self.assertIn("DE2Sim v0.5.0-phase5a", result.stdout)
        self.assertIn("DE2Sim v0.2.0-phase2b", result.stdout)

    def test_missing_engineering_package_is_controlled_error(self) -> None:
        result = self.run_cli()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--engineering-package is required", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_existing_dummy_package_reaches_phase0_not_implemented(self) -> None:
        with tempfile.TemporaryDirectory(dir=FIXTURES_DIR) as tmp:
            tmp_path = Path(tmp)
            package_path = tmp_path / "dummy_package.zip"
            package_path.write_bytes(b"not a real zip and not parsed in phase 0")
            output_path = tmp_path / "out"

            result = self.run_cli(
                "--engineering-package",
                str(package_path),
                "--output",
                str(output_path),
            )

            self.assertEqual(result.returncode, 3)
            self.assertIn("Phase 0 scaffold is installed", result.stdout)
            self.assertIn("not implemented yet", result.stdout)
            self.assertFalse(output_path.exists())

    def test_legacy_script_remains_byte_for_byte_unchanged(self) -> None:
        before = LEGACY_SCRIPT.read_bytes()

        self.run_cli("--version")
        with tempfile.TemporaryDirectory(dir=FIXTURES_DIR) as tmp:
            package_path = Path(tmp) / "dummy_package.zip"
            package_path.write_bytes(b"phase 0 dummy")
            self.run_cli("--engineering-package", str(package_path))

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


if __name__ == "__main__":
    unittest.main()
