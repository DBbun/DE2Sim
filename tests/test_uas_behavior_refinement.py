from __future__ import annotations

import copy
import json
import unittest

from de2sim.asot.schema import stable_id
from de2sim.behaviors.proposal_generator import generate_behavior_proposals
from de2sim.visualization.behavior_review import build_behavior_review_data, render_behavior_review_html


def uas_asot(complete: bool = True, duplicate_components: bool = False) -> dict:
    uas_id = stable_id("component", {"name": "DemoUAS"})
    airframe_def_id = stable_id("component", {"name": "Airframe", "kind": "part def"})
    airframe_instance_id = stable_id("component", {"name": "airframe", "kind": "part"})
    battery_req_id = stable_id("requirement", {"id": "REQ-LOW-BATTERY-RTB"})
    speed_req_id = stable_id("requirement", {"id": "REQ-MAX-SPEED"})
    threshold_param_id = stable_id("parameter", {"name": "battery_threshold"})
    speed_param_id = stable_id("parameter", {"name": "max_speed"})
    capacity_param_id = stable_id("parameter", {"name": "battery_capacity"})
    rtb_behavior_id = stable_id("behavior", {"name": "ReturnToBase"})
    components = [
        {
            "stable_id": uas_id,
            "name": "DemoUAS",
            "description": "Representative UAS",
            "component_type": "system",
            "source_references": ["prov-sysml"],
        },
        {
            "stable_id": airframe_def_id,
            "name": "Airframe",
            "description": "Airframe definition",
            "component_type": "part def",
            "source_references": ["prov-sysml"],
        },
    ]
    if duplicate_components:
        components.append(
            {
                "stable_id": airframe_instance_id,
                "name": "airframe",
                "description": "Airframe instance",
                "component_type": "part",
                "source_references": ["prov-sysml"],
            }
        )
    behaviors = []
    if complete:
        behaviors.append(
            {
                "stable_id": rtb_behavior_id,
                "name": "ReturnToBase",
                "description": "Source action commands return to base.",
                "behavior_type": "action",
                "states": [],
                "transitions": [],
                "triggers": [],
                "guards": [],
                "actions": ["ReturnToBase"],
                "owning_component_id": "",
                "generated_by": "source",
                "source_references": ["prov-rtb"],
            }
        )
    return {
        "schema_version": "de2sim.asot.v1",
        "asot_id": stable_id("asot", {"title": "DemoUAS"}),
        "metadata": {
            "title": "DemoUAS",
            "created_at_utc": "2026-07-16T00:00:00Z",
            "source_package_filename": "demouas.zip",
            "source_package_sha256": "a" * 64,
            "parsed_artifacts_sha256": "b" * 64,
            "generator_name": "de2sim",
            "generator_version": "phase4b-test",
        },
        "components": components,
        "requirements": [
            {
                "stable_id": battery_req_id,
                "requirement_id": "REQ-LOW-BATTERY-RTB",
                "name": "Low battery return to base",
                "text": "When battery state is low, the UAS shall return to base.",
                "source_references": ["prov-req"],
            },
            {
                "stable_id": speed_req_id,
                "requirement_id": "REQ-MAX-SPEED",
                "name": "Maximum speed",
                "text": "The UAS shall respect the documented maximum speed.",
                "source_references": ["prov-speed-req"],
            },
        ],
        "interfaces": [],
        "parameters": [
            {
                "stable_id": threshold_param_id,
                "name": "battery_threshold",
                "description": "Battery threshold for return to base.",
                "source_references": ["prov-threshold"],
            },
            {
                "stable_id": speed_param_id,
                "name": "max_speed",
                "description": "Maximum speed operating limit.",
                "source_references": ["prov-speed-param"],
            },
            {
                "stable_id": capacity_param_id,
                "name": "battery_capacity",
                "description": "Battery capacity model input.",
                "source_references": ["prov-capacity"],
            },
        ],
        "physical_models": [],
        "behaviors": behaviors,
        "geometry": [],
        "provenance": [
            {"provenance_id": "prov-req", "source_relative_path": "requirements.md", "evidence_text": "low battery return to base"},
            {"provenance_id": "prov-threshold", "source_relative_path": "parameters.json", "evidence_text": "battery_threshold"},
            {"provenance_id": "prov-rtb", "source_relative_path": "model.sysml", "evidence_text": "ReturnToBase"},
            {"provenance_id": "prov-speed-req", "source_relative_path": "requirements.md", "evidence_text": "maximum speed"},
            {"provenance_id": "prov-speed-param", "source_relative_path": "parameters.json", "evidence_text": "max_speed"},
            {"provenance_id": "prov-capacity", "source_relative_path": "parameters.json", "evidence_text": "battery_capacity"},
            {"provenance_id": "prov-sysml", "source_relative_path": "model.sysml", "evidence_text": "components"},
        ],
        "validation": {"errors": [], "warnings": []},
    }


class UASBehaviorRefinementTests(unittest.TestCase):
    def test_operational_uas_proposal_uses_complete_explicit_evidence(self) -> None:
        asot = uas_asot()
        _prompt, payload = generate_behavior_proposals(asot, "offline")
        self.assertEqual(len(payload["proposals"]), 1)
        proposal = payload["proposals"][0]
        self.assertEqual(proposal["name"], "Low Battery Return-to-Base")
        self.assertEqual(proposal["generated_by"], "offline_template")
        self.assertEqual(proposal["provider"], "offline")
        self.assertEqual(proposal["model"], "deterministic-uas-template-v1")
        self.assertEqual(proposal["approval_status"], "proposed")
        self.assertEqual(proposal["states"], ["preflight", "mission_flight", "return_to_base", "landed"])
        self.assertEqual(
            [(item["from"], item["to"]) for item in proposal["transitions"]],
            [("preflight", "mission_flight"), ("mission_flight", "return_to_base"), ("return_to_base", "landed")],
        )
        self.assertIn("battery_state <= battery_threshold", proposal["guards"])
        all_text = json.dumps(
            {
                "description": proposal["description"],
                "transitions": proposal["transitions"],
                "triggers": proposal["triggers"],
                "guards": proposal["guards"],
                "actions": proposal["actions"],
                "assumptions": proposal["assumptions"],
                "risks": proposal["risks"],
            }
        )
        for unsupported in ("20", "25", "4800"):
            self.assertNotIn(unsupported, all_text)
        self.assertEqual(proposal["owning_component_id"], "")
        self.assertIn(asot["requirements"][0]["stable_id"], proposal["referenced_requirement_ids"])
        self.assertIn(asot["parameters"][0]["stable_id"], proposal["referenced_parameter_ids"])
        self.assertIn(asot["behaviors"][0]["stable_id"], proposal["referenced_behavior_ids"])
        for prov_id in ("prov-req", "prov-threshold", "prov-rtb"):
            self.assertIn(prov_id, proposal["source_provenance_ids"])
        self.assertIn("battery_capacity", " ".join(proposal["assumptions"]))
        self.assertIn("Simulation semantics have not yet been generated.", proposal["risks"])

    def test_fallback_and_duplicate_component_name_suppression(self) -> None:
        asot = uas_asot(complete=False, duplicate_components=True)
        _prompt, payload = generate_behavior_proposals(asot, "offline")
        names = [item["name"] for item in payload["proposals"]]
        self.assertNotIn("Low Battery Return-to-Base", names)
        self.assertEqual(sum(1 for name in names if name.lower().startswith("airframe review")), 1)
        self.assertIn("source-derived ReturnToBase behavior", json.dumps(payload["proposals"]))

    def test_proposal_id_and_output_are_deterministic_except_timestamp(self) -> None:
        asot = uas_asot()
        _prompt1, first = generate_behavior_proposals(asot, "offline")
        _prompt2, second = generate_behavior_proposals(asot, "offline")
        self.assertEqual(first["proposals"][0]["proposal_id"], second["proposals"][0]["proposal_id"])
        self.assertEqual(_without_runtime_time(first), _without_runtime_time(second))

    def test_review_data_and_html_show_phase4b_uas_context(self) -> None:
        asot = uas_asot()
        _prompt, payload = generate_behavior_proposals(asot, "offline")
        data = build_behavior_review_data(asot, payload)
        html = render_behavior_review_html(data)
        card = data["cards"][0]
        self.assertEqual([item["id"] for item in card["behaviors"]], [asot["behaviors"][0]["stable_id"]])
        self.assertIn("orderedStates(p)", html)
        self.assertIn("clippedLabel", html)
        self.assertIn("y:24", html)
        self.assertIn("Deterministic offline template — not generative AI", html)
        self.assertIn("Linked source-derived behaviors", html)


def _without_runtime_time(payload: dict) -> dict:
    normalized = copy.deepcopy(payload)
    normalized["generated_at_utc"] = "<runtime>"
    for proposal in normalized["proposals"]:
        proposal["generated_at_utc"] = "<runtime>"
    return normalized


if __name__ == "__main__":
    unittest.main()
