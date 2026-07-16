"""Phase 5A simulation orchestration and artifact writing."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

from de2sim.asot.io import ASOTIOError, read_asot_json
from de2sim.simulation.asot_adapter import SimulationASOTError, extract_simulation_facts
from de2sim.simulation.high_fidelity import run_high_fidelity
from de2sim.simulation.low_fidelity import run_low_fidelity
from de2sim.simulation.scenario import ScenarioError, load_scenario, scenario_values
from de2sim.simulation.schema import SIMULATION_SCHEMA_VERSION, TELEMETRY_COLUMNS
from de2sim.simulation.validation import (
    SimulationValidationError,
    compare_fidelities,
    evaluate_requirements,
    validate_engineering_limits,
    validate_simulation_output,
)
from de2sim.visualization.simulation_viewer import build_simulation_viewer_data, render_simulation_viewer_html


class SimulationError(Exception):
    """Controlled simulation build failure."""


def run_simulation_build(approved_asot_path: Path | str, output_dir: Path | str, scenario_path: Path | str | None = None) -> dict[str, Path]:
    try:
        asot = read_asot_json(approved_asot_path)
        facts = extract_simulation_facts(asot)
        validate_engineering_limits(facts)
        scenario = load_scenario(scenario_path)
        low = run_low_fidelity(facts, scenario)
        high = run_high_fidelity(facts, scenario)
        max_time = float(scenario_values(scenario)["maximum_simulation_time_s"])
        validate_simulation_output(low, max_time)
        validate_simulation_output(high, max_time)
        requirements = evaluate_requirements(facts, [low, high])
        comparison = compare_fidelities(low, high, requirements)
        run_id = _run_id(asot.to_dict(), scenario)
        return _write_outputs(Path(output_dir), run_id, facts, scenario, low, high, requirements, comparison)
    except (ASOTIOError, SimulationASOTError, ScenarioError, SimulationValidationError, OSError) as exc:
        raise SimulationError(str(exc)) from exc


def build_simulation_package(run_id: str, facts: Any, scenario: dict[str, Any], low: dict[str, Any], high: dict[str, Any], requirements: dict[str, Any], comparison: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": SIMULATION_SCHEMA_VERSION,
        "simulation_run_id": run_id,
        "metadata": {
            "determinism": "simulation_run_id excludes runtime timestamps and filesystem paths",
            "runtime_timestamps": "none",
        },
        "asot_facts": facts.to_dict(),
        "scenario": scenario,
        "simulation_model": _simulation_model(facts, scenario),
        "telemetry": {"low": low["telemetry"], "high": high["telemetry"]},
        "events": {"low": low["events"], "high": high["events"]},
        "simulation_status": {
            "low": _status(low, comparison),
            "high": _status(high, comparison),
        },
        "requirements_evaluation": requirements,
        "fidelity_comparison": comparison,
        "limitations": _limitations(),
    }


def _write_outputs(output: Path, run_id: str, facts: Any, scenario: dict[str, Any], low: dict[str, Any], high: dict[str, Any], requirements: dict[str, Any], comparison: dict[str, Any]) -> dict[str, Path]:
    output.mkdir(parents=True, exist_ok=True)
    package = build_simulation_package(run_id, facts, scenario, low, high, requirements, comparison)
    paths = {
        "simulation_inputs": output / "simulation_inputs.json",
        "simulation_model": output / "simulation_model.json",
        "telemetry_low": output / "telemetry_low.csv",
        "telemetry_high": output / "telemetry_high.csv",
        "simulation_events": output / "simulation_events.json",
        "requirements_evaluation": output / "requirements_evaluation.json",
        "fidelity_comparison": output / "fidelity_comparison.json",
        "simulation_summary": output / "simulation_summary.md",
        "simulation_data": output / "simulation_data.json",
        "simulation_viewer": output / "simulation_viewer.html",
    }
    _write_json({"simulation_run_id": run_id, "asot_facts": facts.to_dict(), "scenario": scenario}, paths["simulation_inputs"])
    _write_json(package["simulation_model"], paths["simulation_model"])
    _write_csv(low["telemetry"], paths["telemetry_low"])
    _write_csv(high["telemetry"], paths["telemetry_high"])
    _write_json(package["events"], paths["simulation_events"])
    _write_json(requirements, paths["requirements_evaluation"])
    _write_json(comparison, paths["fidelity_comparison"])
    paths["simulation_summary"].write_text(_summary(package), encoding="utf-8", newline="\n")
    viewer_data = build_simulation_viewer_data(package)
    package["viewer"] = viewer_data
    _write_json(package, paths["simulation_data"])
    paths["simulation_viewer"].write_text(render_simulation_viewer_html(viewer_data), encoding="utf-8", newline="\n")
    return paths


def _simulation_model(facts: Any, scenario: dict[str, Any]) -> dict[str, Any]:
    return {
        "model_scope": "Phase 5A executable deterministic UAS mission simulation",
        "states": ["preflight", "mission_flight", "return_to_base", "landed"],
        "transition_sequence": facts.to_dict()["transition_sequence"],
        "return_to_base_guard": "battery_state <= battery_threshold",
        "source_derived_action": facts.return_to_base_action,
        "low_fidelity": {
            "description": "deterministic two-dimensional kinematic point model",
            "battery_logic": "remaining_energy = battery_capacity - power_draw * time",
            "excluded_effects": ["wind", "acceleration dynamics", "arbitrary equation evaluation"],
        },
        "high_fidelity": {
            "description": "demonstrative higher-fidelity two-dimensional point-mass model",
            "included_effects": ["velocity state", "acceleration limit", "constant wind disturbance", "idle power", "speed-dependent power draw"],
            "certification_notice": "not flight-certified aerodynamics",
        },
        "shared_inputs": {
            "approved_behavior_id": facts.approved_behavior_id,
            "max_speed_mps": facts.max_speed_mps,
            "battery_threshold_percent": facts.battery_threshold_percent,
            "battery_capacity_wh": facts.battery_capacity_wh,
            "scenario_id": scenario["scenario_id"]["value"],
        },
        "security": ["fixed simulation logic only", "no eval", "no exec", "no arbitrary source equation evaluation"],
        "terminal_conditions": ["landed", "battery_depleted_before_landing"],
    }


def _summary(package: dict[str, Any]) -> str:
    facts = package["asot_facts"]
    low = package["fidelity_comparison"]["low"]
    high = package["fidelity_comparison"]["high"]
    req = package["requirements_evaluation"]
    assumptions = [
        f"- {name}: {item['value']} {item['unit']} ({item['source_classification']}) - {item['explanation']}"
        for name, item in package["scenario"].items()
    ]
    return "\n".join(
        [
            "# DE2Sim Phase 5A Simulation Summary",
            "",
            f"Simulation run ID: `{package['simulation_run_id']}`",
            f"ASOT title: {facts['title']}",
            f"Approved behavior: {facts['approved_behavior_id']}",
            "",
            "## Extracted ASOT Values",
            f"- battery_threshold: {facts['battery_threshold_percent']} percent",
            f"- battery_capacity: {facts['battery_capacity_wh']} Wh",
            f"- max_speed: {facts['max_speed_mps']} m/s",
            "",
            "## Demonstration Scenario Assumptions",
            *assumptions,
            "",
            "## Low-Fidelity Result Summary",
            f"- landing_time_s: {low['landing_time_s']}",
            f"- minimum_battery_percent: {low['minimum_battery_percent']}",
            f"- battery_reserve_at_landing_percent: {package['simulation_status']['low']['battery_reserve_at_landing_percent']}",
            f"- scenario_feasibility_status: {package['simulation_status']['low']['scenario_feasibility_status']}",
            "",
            "## High-Fidelity Result Summary",
            f"- landing_time_s: {high['landing_time_s']}",
            f"- minimum_battery_percent: {high['minimum_battery_percent']}",
            f"- battery_reserve_at_landing_percent: {package['simulation_status']['high']['battery_reserve_at_landing_percent']}",
            f"- scenario_feasibility_status: {package['simulation_status']['high']['scenario_feasibility_status']}",
            "",
            "## Requirement Results",
            f"- low: low_battery_return={req['low']['low_battery_return']['status']}, maximum_speed={req['low']['maximum_speed']['status']}",
            f"- high: low_battery_return={req['high']['low_battery_return']['status']}, maximum_speed={req['high']['maximum_speed']['status']}",
            "",
            "## Known Limitations",
            *_limitations(prefix="- "),
            "",
        ]
    )


def _run_id(asot: dict[str, Any], scenario: dict[str, Any]) -> str:
    payload = {"asot": asot, "scenario": scenario, "schema_version": SIMULATION_SCHEMA_VERSION}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return "simulation-run-" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


def _write_json(payload: dict[str, Any], path: Path) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


def _write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(TELEMETRY_COLUMNS), lineterminator="\n")
        writer.writeheader()
        for row in sorted(rows, key=lambda item: (item["time_s"], item["state"], item["event"])):
            writer.writerow({column: row[column] for column in TELEMETRY_COLUMNS})


def _status(output: dict[str, Any], comparison: dict[str, Any]) -> dict[str, Any]:
    status = dict(comparison["scenario_feasibility"]["per_fidelity"][output["fidelity"]])
    status["mission_completed"] = bool(output["mission_completed"])
    status["terminal_reason"] = output["terminal_reason"]
    status["battery_reserve_at_landing_percent"] = output["battery_reserve_at_landing_percent"]
    status["battery_depleted_before_landing"] = bool(output["battery_depleted_before_landing"])
    return status


def _limitations(prefix: str = "") -> list[str]:
    return [
        prefix + "The simulation engine produces deterministic low- and high-fidelity demonstrative point-mass results.",
        prefix + "High fidelity is a demonstrative point-mass model, not flight-certified aerodynamics.",
        prefix + "Scenario defaults are demonstration assumptions, not CAD, SysML, or authoritative engineering facts.",
        prefix + "The browser viewer plays back precomputed telemetry and does not recompute authoritative results.",
        prefix + "The browser viewer replays precomputed telemetry and is packaged as part of the integrated DE2Sim demonstration. No Godot export or flight-certified model is claimed.",
    ]
