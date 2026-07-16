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


def make_zip(path: Path, members: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as zf:
        for name, data in members.items():
            zf.writestr(name, data)


class ASOTCLITests(unittest.TestCase):
    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "de2sim.cli.challenge_pipeline", *args],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_build_asot_integration_auto_parses_and_prints_outputs(self) -> None:
        with tempfile.TemporaryDirectory(dir=FIXTURES_DIR) as tmp:
            root = Path(tmp)
            package = root / "package.zip"
            output = root / "out"
            make_zip(
                package,
                {
                    "requirements/reqs.csv": b"id,text\nREQ-1,Fly safely\n",
                    "parameters/params.json": b'{"mass": 12, "mode": "m_airframe"}',
                    "sysml/model.sysml": b"package UAS\npart def Airframe\naction Loiter\n",
                    "physical_models/flight.md": b"equation: x = v * t\n",
                    "geometry/body.obj": b"o body\n",
                },
            )

            result = self.run_cli(
                "--engineering-package",
                str(package),
                "--output",
                str(output),
                "--build-asot",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            expected = [
                output / "package_manifest.json",
                output / "parsed_artifacts.json",
                output / "asot.json",
                output / "asot_summary.md",
                output / "asot_validation.json",
            ]
            self.assertEqual(result.stdout.strip().splitlines(), [str(path) for path in expected])
            for path in expected:
                self.assertTrue(path.is_file(), path)

            parsed = json.loads((output / "parsed_artifacts.json").read_text(encoding="utf-8"))
            asot = json.loads((output / "asot.json").read_text(encoding="utf-8"))
            validation = json.loads((output / "asot_validation.json").read_text(encoding="utf-8"))
            summary = (output / "asot_summary.md").read_text(encoding="utf-8")

            self.assertEqual(parsed["record_counts"]["requirements"], 1)
            self.assertTrue(validation["valid"], validation)
            self.assertEqual(validation["counts"]["geometry"], 1)
            self.assertEqual(asot["metadata"]["generator_version"], "phase2b")
            self.assertEqual(asot["geometry"][0]["parser_status"], "referenced_not_parsed")
            self.assertIn("ASOT ID", summary)
            self.assertIn("Geometry is referenced but not parsed", summary)

    def test_build_asot_version(self) -> None:
        result = self.run_cli("--version")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("DE2Sim v0.2.0-phase2b", result.stdout)


if __name__ == "__main__":
    unittest.main()
