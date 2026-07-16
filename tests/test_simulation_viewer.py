from __future__ import annotations

import ast
import unittest
from pathlib import Path

from de2sim.simulation.asot_adapter import extract_simulation_facts
from de2sim.simulation.high_fidelity import run_high_fidelity
from de2sim.simulation.low_fidelity import run_low_fidelity
from de2sim.simulation.runner import build_simulation_package
from de2sim.simulation.scenario import default_scenario
from de2sim.simulation.validation import compare_fidelities, evaluate_requirements
from de2sim.visualization.simulation_viewer import build_simulation_viewer_data, render_simulation_viewer_html
from tests.test_simulation_adapter import approved_asot


REPO_ROOT = Path(__file__).resolve().parents[1]
VIEWER_MODULE = REPO_ROOT / "de2sim" / "visualization" / "simulation_viewer.py"


class SimulationViewerTests(unittest.TestCase):
    def package(self) -> dict:
        facts = extract_simulation_facts(approved_asot())
        scenario = default_scenario()
        low = run_low_fidelity(facts, scenario)
        high = run_high_fidelity(facts, scenario)
        req = evaluate_requirements(facts, [low, high])
        return build_simulation_package("simulation-run-test", facts, scenario, low, high, req, compare_fidelities(low, high, req))

    def test_standalone_viewer_generation_controls_map_charts_and_labels(self) -> None:
        html = render_simulation_viewer_html(build_simulation_viewer_data(self.package()))
        for text in ("Low fidelity", "High fidelity", "Side-by-side comparison", "Play", "Pause", "Reset", "mission map", "battery versus time chart", "speed versus time chart", "Scenario Assumptions", "Limitations"):
            self.assertIn(text, html)
        self.assertIn("preflight -> mission_flight -> return_to_base -> landed", html)
        self.assertIn("demonstration_assumption", html)
        self.assertIn("not flight-certified aerodynamics", html)
        for text in ("Simulation Status", "Mission completed", "Terminal reason", "Battery reserve at landing", "Scenario feasibility", "threshold", "current-marker", "Low path", "High path", "labelize(k)", "details"):
            self.assertIn(text, html)
        self.assertIn("source_classification", html)
        self.assertIn("machine", html)

    def test_viewer_security_and_no_unsafe_python_or_javascript(self) -> None:
        html = render_simulation_viewer_html(build_simulation_viewer_data(self.package()))
        self.assertIn('<script id="simulation-data" type="application/json">', html)
        for bad in ("src=\"http", "href=\"http", "<link", "eval(", "exec(", "Function(", "document.write", "innerHTML", "fetch("):
            self.assertNotIn(bad, html)
        tree = ast.parse(VIEWER_MODULE.read_text(encoding="utf-8"))
        calls = [node.func.id for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)]
        self.assertNotIn("eval", calls)
        self.assertNotIn("exec", calls)


if __name__ == "__main__":
    unittest.main()
