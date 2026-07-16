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


class BehaviorCLITests(unittest.TestCase):
    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "de2sim.cli.challenge_pipeline", *args],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_propose_behaviors_and_apply_decisions_cli(self) -> None:
        with tempfile.TemporaryDirectory(dir=FIXTURES_DIR) as tmp:
            root = Path(tmp)
            package = root / "package.zip"
            output = root / "out"
            make_zip(package, representative_members())
            result = self.run_cli("--engineering-package", str(package), "--output", str(output), "--propose-behaviors")
            self.assertEqual(result.returncode, 0, result.stderr)
            for name in ("behavior_prompt.json", "behavior_proposals.json", "behavior_review.html", "behavior_generation_report.json"):
                self.assertTrue((output / name).is_file(), name)
            proposals = json.loads((output / "behavior_proposals.json").read_text(encoding="utf-8"))
            proposal_id = proposals["proposals"][0]["proposal_id"]
            decisions_path = output / "downloaded_decisions.json"
            decisions_path.write_text(json.dumps({"decisions": [{"proposal_id": proposal_id, "approval_status": "approved"}]}) + "\n", encoding="utf-8")
            apply_result = self.run_cli("--output", str(output), "--apply-behavior-decisions", str(decisions_path))
            self.assertEqual(apply_result.returncode, 0, apply_result.stderr)
            for name in ("behavior_decisions.json", "asot_with_approved_behaviors.json", "behavior_approval_report.json"):
                self.assertTrue((output / name).is_file(), name)
            approved = json.loads((output / "asot_with_approved_behaviors.json").read_text(encoding="utf-8"))
            self.assertIn("offline_template", {item["generated_by"] for item in approved["behaviors"]})

    def test_version_reports_phase4b(self) -> None:
        result = self.run_cli("--version")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("DE2Sim v0.4.1-phase4b", result.stdout)


if __name__ == "__main__":
    unittest.main()
