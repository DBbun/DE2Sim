from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.test_asot_builder import make_zip, representative_members


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"
LEGACY_SCRIPT = REPO_ROOT / "paper_to_simulator_builder_v3_4.py"


class TraceabilityViewerCLITests(unittest.TestCase):
    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "de2sim.cli.challenge_pipeline", *args],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_build_viewer_cli_runs_prior_stages_generates_outputs_and_prints_paths(self) -> None:
        before = LEGACY_SCRIPT.read_bytes()
        with tempfile.TemporaryDirectory(dir=FIXTURES_DIR) as tmp:
            root = Path(tmp)
            package = root / "package.zip"
            output = root / "out"
            make_zip(package, representative_members())

            result = self.run_cli("--engineering-package", str(package), "--output", str(output), "--build-viewer")

            self.assertEqual(result.returncode, 0, result.stderr)
            expected = [
                output / "package_manifest.json",
                output / "parsed_artifacts.json",
                output / "asot.json",
                output / "asot_summary.md",
                output / "asot_validation.json",
                output / "provenance_manifest.json",
                output / "traceability_report.json",
                output / "traceability_report.md",
                output / "asot_traceability_viewer.html",
                output / "viewer_data.json",
            ]
            self.assertEqual(result.stdout.strip().splitlines(), [str(path) for path in expected])
            for path in expected:
                self.assertTrue(path.is_file(), path)
            viewer_data = json.loads((output / "viewer_data.json").read_text(encoding="utf-8"))
            html = (output / "asot_traceability_viewer.html").read_text(encoding="utf-8")
            self.assertEqual(viewer_data["schema_version"], "de2sim.traceability_viewer.v1")
            self.assertIn("viewer-data", html)
            self.assertGreater(viewer_data["metrics"]["traceability_percentage"], 0.0)
        self.assertEqual(LEGACY_SCRIPT.read_bytes(), before)

    def test_version_reports_phase3b(self) -> None:
        result = self.run_cli("--version")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("DE2Sim v0.3.1-phase3b", result.stdout)


if __name__ == "__main__":
    unittest.main()

