from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"
LEGACY_SCRIPT = REPO_ROOT / "paper_to_simulator_builder_v3_4.py"


def make_zip(path: Path, members: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as zf:
        for name, data in members.items():
            zf.writestr(name, data)


class ProvenanceCLITests(unittest.TestCase):
    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "de2sim.cli.challenge_pipeline", *args],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_build_provenance_cli_integration(self) -> None:
        before = LEGACY_SCRIPT.read_bytes()
        with tempfile.TemporaryDirectory(dir=FIXTURES_DIR) as tmp:
            root = Path(tmp)
            package = root / "package.zip"
            output = root / "out"
            make_zip(
                package,
                {
                    "requirements/reqs.csv": b"id,text\nREQ-1,Fly safely\n",
                    "parameters/params.json": b'{"mass": 12}',
                    "sysml/model.sysml": b"package UAS\npart def Airframe\naction Loiter\n",
                    "physical_models/flight.md": b"equation: x = v * t\n",
                    "geometry/body.obj": b"o body\n",
                },
            )
            result = self.run_cli("--engineering-package", str(package), "--output", str(output), "--build-provenance")
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
            ]
            self.assertEqual(result.stdout.strip().splitlines(), [str(path) for path in expected])
            for path in expected:
                self.assertTrue(path.is_file(), path)
            provenance = json.loads((output / "provenance_manifest.json").read_text(encoding="utf-8"))
            report = json.loads((output / "traceability_report.json").read_text(encoding="utf-8"))
            all_outputs = "\n".join(path.read_text(encoding="utf-8", errors="ignore") for path in expected[2:])
            self.assertTrue(report["valid"], report)
            self.assertEqual(provenance["coverage_summary"], report["coverage_summary"])
            self.assertNotIn(str(root), all_outputs)
            self.assertGreater(provenance["coverage_summary"]["traceability_percentage"], 0.0)
        self.assertEqual(LEGACY_SCRIPT.read_bytes(), before)

    def test_version_reports_phase3a(self) -> None:
        result = self.run_cli("--version")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("DE2Sim v0.3.0-phase3a", result.stdout)


if __name__ == "__main__":
    unittest.main()
