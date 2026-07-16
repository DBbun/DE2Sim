from __future__ import annotations

import copy
import unittest

from de2sim.simulation.asot_adapter import SimulationASOTError, extract_simulation_facts


def approved_asot() -> dict:
    return {
        "schema_version": "de2sim.asot.v1",
        "asot_id": "asot-test",
        "metadata": {
            "title": "Test UAS",
            "created_at_utc": "2026-01-01T00:00:00Z",
            "source_package_filename": "test.zip",
            "source_package_sha256": "a",
            "parsed_artifacts_sha256": "b",
            "generator_name": "test",
            "generator_version": "test",
        },
        "components": [],
        "requirements": [
            {"stable_id": "requirement-low", "name": "Low Battery Return", "description": "", "source_references": ["provenance-low"], "traceability_status": "precise", "status": "draft", "warnings": [], "requirement_id": "REQ-1", "text": "The UAS shall return to base when battery state falls below 20 percent", "verification_method": "simulation", "priority": "", "satisfied_by_ids": [], "verified_by_ids": []},
            {"stable_id": "requirement-speed", "name": "Maximum Speed", "description": "", "source_references": ["provenance-speed"], "traceability_status": "precise", "status": "draft", "warnings": [], "requirement_id": "REQ-2", "text": "The UAS shall not exceed the configured maximum speed", "verification_method": "simulation", "priority": "", "satisfied_by_ids": [], "verified_by_ids": []},
        ],
        "interfaces": [],
        "parameters": [
            {"stable_id": "parameter-threshold", "name": "battery_threshold", "description": "", "source_references": ["provenance-threshold"], "traceability_status": "precise", "status": "draft", "warnings": [], "value": 20, "unit": "percent", "minimum": None, "maximum": None, "symbolic_expression": "", "owning_component_id": ""},
            {"stable_id": "parameter-capacity", "name": "battery_capacity", "description": "", "source_references": ["provenance-capacity"], "traceability_status": "precise", "status": "draft", "warnings": [], "value": 4800, "unit": "Wh", "minimum": None, "maximum": None, "symbolic_expression": "", "owning_component_id": ""},
            {"stable_id": "parameter-speed", "name": "max_speed", "description": "", "source_references": ["provenance-param-speed"], "traceability_status": "precise", "status": "draft", "warnings": [], "value": 25, "unit": "m/s", "minimum": None, "maximum": None, "symbolic_expression": "", "owning_component_id": ""},
        ],
        "physical_models": [],
        "behaviors": [
            {"stable_id": "behavior-approved", "name": "Low Battery Return-to-Base", "description": "", "source_references": ["provenance-behavior"], "traceability_status": "precise", "status": "approved", "warnings": [], "behavior_type": "state_machine", "states": ["preflight", "mission_flight", "return_to_base", "landed"], "transitions": [{"from": "mission_flight", "to": "return_to_base", "trigger": "battery_threshold_reached", "guard": "battery_state <= battery_threshold", "action": "invoke the explicit source-derived ReturnToBase behavior"}, {"from": "preflight", "to": "mission_flight", "trigger": "mission_started", "guard": "required mission evidence is available", "action": "begin mission while respecting documented operating limits, including max_speed"}, {"from": "return_to_base", "to": "landed", "trigger": "home_position_reached", "guard": "return-to-base behavior is active and home arrival is confirmed", "action": "land and terminate the mission"}], "triggers": [], "guards": [], "actions": [], "owning_component_id": "", "generated_by": "offline_template", "approval_status": "approved", "provider": "offline", "model": "", "prompt_hash": "", "proposal_id": "proposal-1", "referenced_requirement_ids": ["requirement-low", "requirement-speed"], "referenced_parameter_ids": ["parameter-threshold", "parameter-capacity", "parameter-speed"], "referenced_physical_model_ids": [], "source_provenance_ids": ["provenance-behavior"], "approval_decision": {}},
            {"stable_id": "behavior-rtb", "name": "ReturnToBase", "description": "", "source_references": ["provenance-rtb"], "traceability_status": "precise", "status": "source-derived", "warnings": [], "behavior_type": "action", "states": [], "transitions": [], "triggers": [], "guards": [], "actions": ["ReturnToBase"], "owning_component_id": "", "generated_by": "source", "approval_status": "approved", "provider": "", "model": "", "prompt_hash": "", "proposal_id": "", "referenced_requirement_ids": [], "referenced_parameter_ids": [], "referenced_physical_model_ids": [], "source_provenance_ids": ["provenance-rtb"], "approval_decision": {}},
        ],
        "geometry": [],
        "provenance": [
            {"provenance_id": item, "source_relative_path": "source.txt", "source_sha256": "x", "source_role": "", "parser_name": "", "parser_status": "", "source_locator": "file", "evidence_type": "text_line", "evidence_text": item, "confidence": 1.0, "target_entity_ids": [], "warnings": []}
            for item in ("provenance-low", "provenance-speed", "provenance-threshold", "provenance-capacity", "provenance-param-speed", "provenance-behavior", "provenance-rtb")
        ],
        "validation": {"errors": [], "warnings": []},
    }


class SimulationAdapterTests(unittest.TestCase):
    def test_approved_asot_extraction_stable_ids_and_values(self) -> None:
        facts = extract_simulation_facts(approved_asot())
        self.assertEqual(facts.approved_behavior_id, "behavior-approved")
        self.assertEqual(facts.source_return_to_base_behavior_id, "behavior-rtb")
        self.assertEqual(facts.battery_threshold_percent, 20.0)
        self.assertEqual(facts.battery_capacity_wh, 4800.0)
        self.assertEqual(facts.max_speed_mps, 25.0)
        self.assertEqual([item[:2] for item in facts.transition_sequence], [("preflight", "mission_flight"), ("mission_flight", "return_to_base"), ("return_to_base", "landed")])

    def test_rejects_missing_or_unapproved_behavior(self) -> None:
        missing = approved_asot()
        missing["behaviors"] = [missing["behaviors"][1]]
        with self.assertRaisesRegex(SimulationASOTError, "absent"):
            extract_simulation_facts(missing)
        unapproved = approved_asot()
        unapproved["behaviors"][0]["approval_status"] = "pending"
        with self.assertRaisesRegex(SimulationASOTError, "not approved"):
            extract_simulation_facts(unapproved)

    def test_rejects_missing_required_parameters_and_bad_references(self) -> None:
        missing = approved_asot()
        missing["parameters"] = missing["parameters"][:2]
        with self.assertRaisesRegex(SimulationASOTError, "max_speed"):
            extract_simulation_facts(missing)
        broken = approved_asot()
        broken["behaviors"][0]["source_provenance_ids"] = ["missing-provenance"]
        with self.assertRaisesRegex(SimulationASOTError, "does not exist"):
            extract_simulation_facts(broken)


if __name__ == "__main__":
    unittest.main()
