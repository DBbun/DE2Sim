from __future__ import annotations

import json
import re
import shutil
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path
import zipfile

from de2sim.asot.builder import build_asot_from_files
from de2sim.demo.geometry_package import build_geometry_package, demo_uas_stl
from de2sim.demo.package import build_demo_package
from de2sim.geometry.pipeline import render_geometry_viewer, validate_geometry_extraction, write_geometry_outputs
from de2sim.geometry.stl import STLParseError, STLParseOptions, parse_stl
from de2sim.ingest.artifact_parser import parse_artifacts_from_manifest
from de2sim.ingest.package_reader import ingest_engineering_package
from de2sim.simulation.runner import run_simulation_build
from tests.test_demo_package import make_demo_inputs


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def executable_scripts(html: str) -> list[str]:
    scripts = []
    for match in re.finditer(r"<script([^>]*)>(.*?)</script>", html, flags=re.IGNORECASE | re.DOTALL):
        attrs = match.group(1).lower()
        if 'type="application/json"' not in attrs and "type='application/json'" not in attrs:
            scripts.append(match.group(2))
    return scripts


def embedded_json_payload(html: str, script_id: str) -> dict:
    match = re.search(
        rf'<script[^>]*id="{re.escape(script_id)}"[^>]*type="application/json"[^>]*>(.*?)</script>',
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        raise AssertionError(f"missing JSON script: {script_id}")
    return json.loads(match.group(1))


def assert_no_raw_newline_in_js_string(testcase: unittest.TestCase, script: str) -> None:
    quote = ""
    escaped = False
    for index, char in enumerate(script):
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = ""
            elif char in "\r\n":
                testcase.fail(f"raw newline inside JavaScript string literal at character {index}")
        elif char in ("'", '"'):
            quote = char
    testcase.assertFalse(quote, "unterminated JavaScript string literal")


def assert_node_check_passes_if_available(testcase: unittest.TestCase, script: str, root: Path) -> None:
    if not shutil.which("node"):
        return
    script_path = root / "geometry_viewer_executable.js"
    script_path.write_text(script, encoding="utf-8", newline="\n")
    completed = subprocess.run(["node", "--check", str(script_path)], capture_output=True, text=True, check=False)
    testcase.assertEqual(completed.returncode, 0, completed.stderr)


class GeometryPhase6CTests(unittest.TestCase):
    def test_ascii_stl_exact_dimensions_and_deterministic_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "demo.stl"
            path.write_text(demo_uas_stl(), encoding="utf-8")
            first = parse_stl(path, "m")
            second = parse_stl(path, "m")
            self.assertEqual(first, second)
            self.assertEqual(first["source_format"], "ascii_stl")
            self.assertEqual(first["dimensions"], {"x": 1.2, "y": 1.2, "z": 0.24})
            self.assertEqual(first["facet_count"], 164)

    def test_binary_stl_and_security_rejections(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            binary = root / "one.stl"
            header = b"binary-demo".ljust(80, b"\0")
            facet = struct.pack("<12fH", 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0)
            binary.write_bytes(header + struct.pack("<I", 1) + facet)
            parsed = parse_stl(binary, "m")
            self.assertEqual(parsed["source_format"], "binary_stl")
            self.assertEqual(parsed["facet_count"], 1)

            malformed = root / "bad.stl"
            malformed.write_text("solid bad\nfacet normal 0 0 1\nendsolid bad\n", encoding="utf-8")
            with self.assertRaisesRegex(STLParseError, "malformed ASCII STL"):
                parse_stl(malformed, "m")
            truncated = root / "truncated.stl"
            truncated.write_bytes(header + struct.pack("<I", 2) + facet)
            with self.assertRaisesRegex(STLParseError, "truncated binary STL"):
                parse_stl(truncated, "m")
            nan = root / "nan.stl"
            nan.write_bytes(header + struct.pack("<I", 1) + struct.pack("<12fH", 0, 0, 1, float("nan"), 0, 0, 1, 0, 0, 0, 1, 0, 0))
            with self.assertRaisesRegex(STLParseError, "NaN or infinite"):
                parse_stl(nan, "m")
            with self.assertRaisesRegex(STLParseError, "maximum size"):
                parse_stl(binary, "m", STLParseOptions(max_source_size=10))
            with self.assertRaisesRegex(STLParseError, "facet count|impossible"):
                parse_stl(binary, "m", STLParseOptions(max_facets=0))
            with self.assertRaisesRegex(STLParseError, "unit is missing"):
                parse_stl(binary, "")

    def test_geometry_package_zip_pipeline_viewer_and_simulation_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = root / "base.zip"
            with zipfile.ZipFile(base, "w") as archive:
                archive.writestr("sysml/demo_uas.sysml", "package DemoUAS\naction ReturnToBase\n")
                archive.writestr("physical_models/energy_model.md", "equation: remaining_energy = battery_capacity - power_draw * time\n")
                archive.writestr("requirements/requirements.csv", "id,title,text,verification_method\nREQ-1,Low Battery Return,The UAS shall return to base when battery state falls below 20 percent,Simulation\nREQ-2,Maximum Speed,The UAS shall not exceed the configured maximum speed,Simulation\n")
                archive.writestr("parameters/parameters.csv", "parameter_id,name,value,unit\nP-1,battery_threshold,20,percent\nP-2,max_speed,25,m/s\nP-3,battery_capacity,4800,Wh\n")
            package1 = build_geometry_package(base, root / "geom1.zip")
            package2 = build_geometry_package(base, root / "geom2.zip")
            self.assertEqual(package1.read_bytes(), package2.read_bytes())

            manifest = ingest_engineering_package(package1, root / "out")
            parsed = parse_artifacts_from_manifest(manifest)
            asot_doc = build_asot_from_files(manifest, parsed)
            asot = asot_doc.to_dict()
            extraction = read_json(parsed)["geometry_extractions"][0]
            validation, linkage = validate_geometry_extraction(extraction, asot)
            outputs = write_geometry_outputs(extraction, validation, linkage, root / "out")
            self.assertTrue(validation["valid"])
            self.assertEqual(asot["geometry"][0]["stable_id"], extraction["geometry_id"])
            self.assertEqual(asot["geometry"][0]["dimensions"], {"x": 1.2, "y": 1.2, "z": 0.24})
            viewer = outputs["geometry_viewer"].read_text(encoding="utf-8")
            self.assertIn("Demonstration CAD-export mesh - not vendor-authoritative vehicle geometry.", viewer)
            for bad in ("src=\"http", "href=\"http", "eval(", "Function(", "innerHTML", "fetch("):
                self.assertNotIn(bad, viewer)
            scene = embedded_json_payload(viewer, "geometry-scene")
            self.assertEqual(scene["source_geometry_id"], "geometry-442731f9c74c1b85")
            self.assertEqual(scene["facet_count"], 164)
            self.assertEqual(scene["dimensions"], {"x": 1.2, "y": 1.2, "z": 0.24})
            self.assertEqual(scene["source_hash"], "a480ea2f2c1951975008d48747d41bc6f7b65fa2483f2033b38801fe2c144ea1")
            scripts = executable_scripts(viewer)
            self.assertEqual(len(scripts), 1)
            assert_no_raw_newline_in_js_string(self, scripts[0])
            assert_node_check_passes_if_available(self, scripts[0], root)
            self.assertIn('let mode="solid",rx=-0.6,ry=0.7,zoom=2.4', scripts[0])
            self.assertNotIn('getContext("webgl")', scripts[0])
            self.assertIn('getContext("2d")', scripts[0])
            self.assertIn("requestAnimationFrame(draw)", scripts[0])
            self.assertIn('document.getElementById("solid").classList.add("active");draw();', scripts[0])
            for control in ("fit", "solid", "wire", "box", "front", "side", "top", "reset"):
                self.assertIn(f'id="{control}"', viewer)

            asot_path = root / "out" / "approved.json"
            asot["behaviors"] = [
                {
                    "stable_id": "behavior-approved", "name": "Low Battery Return-to-Base", "description": "", "source_references": [], "traceability_status": "precise", "status": "approved", "warnings": [], "behavior_type": "state_machine",
                    "states": ["preflight", "mission_flight", "return_to_base", "landed"],
                    "transitions": [{"from": "preflight", "to": "mission_flight", "trigger": "mission_started", "guard": "required mission evidence is available", "action": "begin mission"}, {"from": "mission_flight", "to": "return_to_base", "trigger": "battery_threshold_reached", "guard": "battery_state <= battery_threshold", "action": "ReturnToBase"}, {"from": "return_to_base", "to": "landed", "trigger": "home_position_reached", "guard": "return-to-base behavior is active and home arrival is confirmed", "action": "land"}],
                    "triggers": [], "guards": [], "actions": [], "owning_component_id": "", "generated_by": "offline_template", "approval_status": "approved", "provider": "offline", "model": "", "prompt_hash": "", "proposal_id": "proposal-1",
                    "referenced_requirement_ids": [asot["requirements"][0]["stable_id"], asot["requirements"][1]["stable_id"]],
                    "referenced_parameter_ids": [p["stable_id"] for p in asot["parameters"] if p["name"] in {"battery_threshold", "battery_capacity", "max_speed"}],
                    "referenced_physical_model_ids": [], "source_provenance_ids": [], "approval_decision": {},
                },
                {"stable_id": "behavior-rtb", "name": "ReturnToBase", "description": "", "source_references": [], "traceability_status": "precise", "status": "source-derived", "warnings": [], "behavior_type": "action", "states": [], "transitions": [], "triggers": [], "guards": [], "actions": ["ReturnToBase"], "owning_component_id": "", "generated_by": "source", "approval_status": "approved", "provider": "", "model": "", "prompt_hash": "", "proposal_id": "", "referenced_requirement_ids": [], "referenced_parameter_ids": [], "referenced_physical_model_ids": [], "source_provenance_ids": [], "approval_decision": {}},
            ]
            for record in asot["provenance"]:
                record["target_entity_ids"] = []
            asot_path.write_text(json.dumps(asot, indent=2) + "\n", encoding="utf-8")
            sim = run_simulation_build(asot_path, root / "sim")
            self.assertEqual(read_json(sim["simulation_inputs"])["geometry_id"], extraction["geometry_id"])
            self.assertFalse(read_json(sim["simulation_model"])["geometry_used_for_flight_dynamics"])

    def test_geometry_viewer_serializes_embedded_scene_safely(self) -> None:
        scene = {
            "schema_version": "de2sim.geometry_scene.v1",
            "source_geometry_id": "geometry-test",
            "display_classification": 'quote " backslash \\ newline \n unicode \u2028 end </script><script>alert(1)</script>',
            "vertices": [[0, 0, 0], [1, 0, 0], [0, 1, 0]],
            "triangles": [[0, 1, 2]],
            "bounding_box": {"min": {"x": 0, "y": 0, "z": 0}, "max": {"x": 1, "y": 1, "z": 0}},
            "center": {"x": 0.5, "y": 0.5, "z": 0},
            "dimensions": {"x": 1, "y": 1, "z": 0},
            "unit": "m",
            "source_format": "ascii_stl",
            "source_hash": "hash",
            "facet_count": 1,
            "linked_asot_ids": {"component": "component", "physical_model": "model", "parameters": {"x": "px", "y": "py", "z": "pz"}},
            "provenance_ids": ["prov"],
            "validation": {"status": "passed", "errors": []},
            "authoritativeness": "not_vendor_authoritative",
            "limitations": ["line one\nline two", 'quote " and slash \\', "closing </script> marker"],
        }
        html = render_geometry_viewer(scene)
        self.assertNotIn("</script><script>alert(1)", html)
        self.assertEqual(html.lower().count("</script>"), 2)
        self.assertIn("<\\/script>", html)
        embedded = embedded_json_payload(html, "geometry-scene")
        self.assertEqual(embedded["display_classification"], scene["display_classification"])
        self.assertEqual(embedded["limitations"], scene["limitations"])
        scripts = executable_scripts(html)
        self.assertEqual(len(scripts), 1)
        assert_no_raw_newline_in_js_string(self, scripts[0])
        with tempfile.TemporaryDirectory() as tmp:
            assert_node_check_passes_if_available(self, scripts[0], Path(tmp))

    def test_demo_package_includes_geometry_card_and_source_stl(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            engineering, approved, behavior_dir, simulation_dir = make_demo_inputs(root)
            geom = {
                "schema_version": "de2sim.geometry_extraction.v1",
                "geometry_id": "geometry-442731f9c74c1b85",
                "tolerances": {"absolute": 1e-06, "relative": 1e-09},
                "linkage": {"source_classification": "demonstration_cad_export", "authoritativeness": "not_vendor_authoritative"},
                "geometry": {
                    "source_path": "geometry/demo_uas.stl",
                    "source_format": "ascii_stl",
                    "source_sha256": "a480ea2f2c1951975008d48747d41bc6f7b65fa2483f2033b38801fe2c144ea1",
                    "facet_count": 164,
                    "vertex_count": 492,
                    "unique_vertex_count": 160,
                    "bounding_box_min": {"x": -0.6, "y": -0.6, "z": -0.12},
                    "bounding_box_max": {"x": 0.6, "y": 0.6, "z": 0.12},
                    "dimensions": {"x": 1.2, "y": 1.2, "z": 0.24},
                    "unit": "m",
                },
            }
            (behavior_dir / "geometry_extraction.json").write_text(json.dumps(geom), encoding="utf-8")
            (behavior_dir / "geometry_validation.json").write_text(json.dumps({"valid": True, "validation_status": "passed", "tolerances": {"absolute": 1e-06, "relative": 1e-09}}), encoding="utf-8")
            (behavior_dir / "geometry_linkage_report.json").write_text(json.dumps({"linked_component_id": "component-demo", "linked_physical_model_id": "model-demo", "linked_parameter_ids": {"x": "px", "y": "py", "z": "pz"}, "source_provenance_ids": ["provenance-geometry"]}), encoding="utf-8")
            (behavior_dir / "geometry_scene.json").write_text(json.dumps({"schema_version": "de2sim.geometry_scene.v1", "limitations": ["not vendor-authoritative geometry", "no aerodynamic derivation"]}), encoding="utf-8")
            (behavior_dir / "geometry_viewer.html").write_text("<!doctype html><title>geometry</title>", encoding="utf-8")
            with zipfile.ZipFile(engineering, "a") as archive:
                archive.writestr("geometry/demo_uas.stl", demo_uas_stl())
            result = build_demo_package(engineering, approved, behavior_dir, simulation_dir, root / "pkg", "DE2Sim v0.7.0-phase6c-geometry")
            second = build_demo_package(engineering, approved, behavior_dir, simulation_dir, root / "pkg2", "DE2Sim v0.7.0-phase6c-geometry")
            self.assertEqual(result["zip"].read_bytes(), second["zip"].read_bytes())
            dashboard = result["dashboard"].read_text(encoding="utf-8")
            self.assertIn("Nine-Stage Pipeline", dashboard)
            self.assertIn("CAD/Geometry Integration", dashboard)
            self.assertIn("viewers/geometry_viewer.html", dashboard)
            self.assertIn("Geometry Integration Summary", dashboard)
            self.assertIn("reports/geometry_integration_summary.md", dashboard)
            summary = (result["package_root"] / "reports" / "geometry_integration_summary.md").read_text(encoding="utf-8")
            self.assertIn("geometry-442731f9c74c1b85", summary)
            self.assertIn("geometry/demo_uas.stl", summary)
            self.assertIn("a480ea2f2c1951975008d48747d41bc6f7b65fa2483f2033b38801fe2c144ea1", summary)
            self.assertIn("ascii_stl", summary)
            self.assertIn("demonstration_cad_export", summary)
            self.assertIn("not_vendor_authoritative", summary)
            self.assertIn("Facet count: 164", summary)
            self.assertIn("Vertex count: 492", summary)
            self.assertIn("Unique vertex count: 160", summary)
            self.assertIn("Dimensions and unit: 1.2 x 1.2 x 0.24 m", summary)
            self.assertIn("Dimensional validation status: `passed`", summary)
            self.assertIn("Absolute validation tolerance: 1e-06", summary)
            self.assertIn("Relative validation tolerance: 1e-09", summary)
            self.assertIn("geometry_used_for_visualization: true", summary)
            self.assertIn("geometry_used_for_flight_dynamics: false", summary)
            self.assertIn("provenance-geometry", summary)
            self.assertIn("not vendor-authoritative geometry", summary)
            self.assertIn("no aerodynamic derivation", summary)
            self.assertNotIn("C:\\", summary)
            manifest = read_json(result["manifest"])
            paths = [item["relative_path"] for item in manifest["files"]]
            self.assertIn("artifacts/source_geometry/demo_uas.stl", paths)
            self.assertIn("reports/geometry_integration_summary.md", paths)
            report_hash = next(item["sha256"] for item in manifest["files"] if item["relative_path"] == "reports/geometry_integration_summary.md")
            reproducibility = read_json(result["reproducibility_report"])
            self.assertEqual(reproducibility["artifact_hashes"]["reports/geometry_integration_summary.md"], report_hash)
            with zipfile.ZipFile(result["zip"]) as archive:
                self.assertIn("DE2Sim_Submission_Demo/reports/geometry_integration_summary.md", archive.namelist())


if __name__ == "__main__":
    unittest.main()
