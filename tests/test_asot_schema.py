from __future__ import annotations

import unittest

from de2sim.asot.schema import (
    SUPPORTED_SCHEMA_VERSION,
    ASOTDocument,
    ASOTMetadata,
    ASOTValidationState,
    Behavior,
    Component,
    GeometryRecord,
    Interface,
    Parameter,
    PhysicalModel,
    ProvenanceRecord,
    Requirement,
    stable_id,
)
from de2sim.asot.validators import validate_asot


def representative_asot() -> ASOTDocument:
    airframe_id = stable_id("component", {"name": "Airframe", "type": "structure"})
    payload_id = stable_id("component", {"name": "Payload", "type": "sensor"})
    interface_id = stable_id("interface", {"source": airframe_id, "target": payload_id, "name": "Payload mount"})
    parameter_id = stable_id("parameter", {"name": "mass", "owner": airframe_id, "value": 12.5})
    behavior_id = stable_id("behavior", {"name": "Loiter", "owner": airframe_id})
    geometry_id = stable_id("geometry", {"path": "geometry/airframe.glb", "owner": airframe_id})
    model_id = stable_id("physicalmodel", {"equation": "lift = q * s * cl", "owner": airframe_id})
    requirement_id = stable_id("requirement", {"id": "REQ-001", "text": "Vehicle shall fly safely"})

    return ASOTDocument(
        schema_version=SUPPORTED_SCHEMA_VERSION,
        asot_id=stable_id("asot", {"title": "Representative UAS"}),
        metadata=ASOTMetadata(
            title="Representative UAS",
            created_at_utc="2026-07-15T00:00:00Z",
            source_package_filename="uas.zip",
            source_package_sha256="a" * 64,
            parsed_artifacts_sha256="b" * 64,
            generator_name="de2sim",
            generator_version="phase2a",
        ),
        components=[
            Component(
                stable_id=airframe_id,
                name="Airframe",
                description="Primary structure",
                source_references=["prov-001"],
                status="parsed",
                component_type="structure",
                child_component_ids=[payload_id],
                interface_ids=[interface_id],
                parameter_ids=[parameter_id],
                behavior_ids=[behavior_id],
                geometry_ids=[geometry_id],
            ),
            Component(
                stable_id=payload_id,
                name="Payload",
                description="Sensor payload",
                source_references=["prov-001"],
                status="parsed",
                component_type="sensor",
                parent_component_id=airframe_id,
            ),
        ],
        requirements=[
            Requirement(
                stable_id=requirement_id,
                name="Safe flight",
                description="Safety requirement",
                source_references=["prov-001"],
                status="parsed",
                requirement_id="REQ-001",
                text="Vehicle shall fly safely",
                verification_method="test",
                priority="high",
                satisfied_by_ids=[airframe_id],
                verified_by_ids=[behavior_id],
            )
        ],
        interfaces=[
            Interface(
                stable_id=interface_id,
                name="Payload mount",
                description="Mechanical payload interface",
                source_references=["prov-001"],
                status="parsed",
                interface_type="mechanical",
                source_component_id=airframe_id,
                target_component_id=payload_id,
                port_names=["mount_a", "mount_b"],
                direction="bidirectional",
                exchanged_items=["loads"],
            )
        ],
        parameters=[
            Parameter(
                stable_id=parameter_id,
                name="mass",
                description="Airframe mass",
                source_references=["prov-001"],
                status="parsed",
                value=12.5,
                unit="kg",
                minimum=1,
                maximum=20,
                symbolic_expression="m_airframe",
                owning_component_id=airframe_id,
            )
        ],
        physical_models=[
            PhysicalModel(
                stable_id=model_id,
                name="Lift model",
                description="Simple lift relation",
                source_references=["prov-001"],
                status="parsed",
                equation="lift = q * s * cl",
                variables=["lift", "q", "s", "cl"],
                parameter_ids=[parameter_id],
                assumptions=["low fidelity"],
                owning_component_ids=[airframe_id],
            )
        ],
        behaviors=[
            Behavior(
                stable_id=behavior_id,
                name="Loiter",
                description="Hold station",
                source_references=["prov-001"],
                status="approved",
                behavior_type="state_machine",
                states=["idle", "loiter"],
                triggers=["mission_start"],
                actions=["hold_position"],
                owning_component_id=airframe_id,
                generated_by="human",
                approval_status="not_required",
            )
        ],
        geometry=[
            GeometryRecord(
                stable_id=geometry_id,
                name="Airframe geometry",
                description="Referenced GLB",
                source_references=["prov-001"],
                status="referenced",
                source_relative_path="geometry/airframe.glb",
                geometry_format="glb",
                owning_component_id=airframe_id,
                parser_status="referenced_not_parsed",
                coordinate_system="ENU",
                unit="m",
            )
        ],
        provenance=[
            ProvenanceRecord(
                provenance_id="prov-001",
                source_relative_path="sysml/uas.sysml",
                source_sha256="c" * 64,
                source_locator="line:1",
                parser_name="phase1b",
                confidence=1.0,
            )
        ],
        validation=ASOTValidationState(),
    )


class ASOTSchemaTests(unittest.TestCase):
    def test_minimal_valid_asot(self) -> None:
        document = ASOTDocument.minimal("Minimal ASOT", "package.zip")
        result = validate_asot(document)
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(document.schema_version, SUPPORTED_SCHEMA_VERSION)
        self.assertEqual(document.components, [])

    def test_complete_representative_asot(self) -> None:
        document = representative_asot()
        payload = document.to_dict()
        self.assertEqual(list(payload), [
            "schema_version",
            "asot_id",
            "metadata",
            "components",
            "requirements",
            "interfaces",
            "parameters",
            "physical_models",
            "behaviors",
            "geometry",
            "provenance",
            "validation",
        ])
        self.assertTrue(validate_asot(document).ok)
        self.assertEqual(len(payload["components"]), 2)
        self.assertEqual(payload["metadata"]["generator_version"], "phase2a")

    def test_deterministic_stable_ids(self) -> None:
        payload = {"name": "Airframe", "type": "structure", "values": ["b", "a"]}
        self.assertEqual(stable_id("component", payload), stable_id("component", payload))
        self.assertNotEqual(stable_id("component", payload), stable_id("parameter", payload))

    def test_empty_optional_sections_allowed(self) -> None:
        document = representative_asot()
        document.interfaces = []
        document.parameters = []
        document.physical_models = []
        document.behaviors = []
        document.geometry = []
        for component in document.components:
            component.interface_ids = []
            component.parameter_ids = []
            component.behavior_ids = []
            component.geometry_ids = []
        for requirement in document.requirements:
            requirement.verified_by_ids = []
        result = validate_asot(document)
        self.assertTrue(result.ok, result.errors)


if __name__ == "__main__":
    unittest.main()
