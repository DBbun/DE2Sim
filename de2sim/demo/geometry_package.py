"""Build a deterministic Phase 6C demo engineering package with STL geometry."""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
from pathlib import Path
import zipfile
from typing import Iterable


FIXED_ZIP_DT = (2026, 1, 1, 0, 0, 0)


class GeometryPackageError(Exception):
    """Controlled demo geometry package failure."""


def build_geometry_package(base_package: Path | str, output: Path | str) -> Path:
    base = Path(base_package)
    target = Path(output)
    if not base.is_file() or not zipfile.is_zipfile(base):
        raise GeometryPackageError(f"base package must be an existing ZIP: {base}")
    additions = _geometry_files()
    target.parent.mkdir(parents=True, exist_ok=True)
    rows: list[tuple[str, bytes]] = []
    with zipfile.ZipFile(base, "r") as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            rel = info.filename.replace("\\", "/")
            if rel == "geometry/demo_uas.glb":
                continue
            if rel in additions:
                continue
            rows.append((rel, archive.read(info)))
    rows.extend(sorted(additions.items()))
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for rel, data in sorted(rows, key=lambda item: item[0]):
            info = zipfile.ZipInfo(rel, FIXED_ZIP_DT)
            info.external_attr = 0o644 << 16
            archive.writestr(info, data)
    return target


def _geometry_files() -> dict[str, bytes]:
    stl = demo_uas_stl().encode("utf-8")
    linkage = {
        "schema_version": "de2sim.geometry_linkage.v1",
        "source_geometry": "geometry/demo_uas.stl",
        "source_classification": "demonstration_cad_export",
        "authoritativeness": "not_vendor_authoritative",
        "unit": "m",
        "component_source_key": "DemoUAS",
        "physical_model_source_key": "remaining_energy = battery_capacity - power_draw * time",
        "dimension_parameter_source_keys": {
            "x": "geometry_x_dimension",
            "y": "geometry_y_dimension",
            "z": "geometry_z_dimension",
        },
        "derived_visualization_role": "training_visualization",
    }
    return {
        "geometry/demo_uas.stl": stl,
        "geometry/geometry_linkage.json": _json_bytes(linkage),
        "parameters/geometry_parameters.csv": _parameters_csv(),
        "geometry/README.md": _readme().encode("utf-8"),
    }


def demo_uas_stl() -> str:
    triangles: list[tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]]] = []
    _box(triangles, -0.18, -0.12, -0.08, 0.18, 0.12, 0.08)
    _box(triangles, -0.52, -0.035, -0.03, 0.52, 0.035, 0.03)
    _box(triangles, -0.035, -0.52, -0.03, 0.035, 0.52, 0.03)
    for cx, cy in ((-0.48, -0.48), (-0.48, 0.48), (0.48, -0.48), (0.48, 0.48)):
        _disc(triangles, cx, cy, 0.12, 0.12, 16)
        _disc(triangles, cx, cy, -0.12, 0.12, 16, reverse=True)
    lines = ["solid demo_uas_phase6c"]
    for tri in triangles:
        normal = _normal(tri)
        lines.append(f"  facet normal {_f(normal[0])} {_f(normal[1])} {_f(normal[2])}")
        lines.append("    outer loop")
        for vertex in tri:
            lines.append(f"      vertex {_f(vertex[0])} {_f(vertex[1])} {_f(vertex[2])}")
        lines.append("    endloop")
        lines.append("  endfacet")
    lines.append("endsolid demo_uas_phase6c")
    return "\n".join(lines) + "\n"


def _box(tris: list, xmin: float, ymin: float, zmin: float, xmax: float, ymax: float, zmax: float) -> None:
    v = {
        "000": (xmin, ymin, zmin), "100": (xmax, ymin, zmin), "110": (xmax, ymax, zmin), "010": (xmin, ymax, zmin),
        "001": (xmin, ymin, zmax), "101": (xmax, ymin, zmax), "111": (xmax, ymax, zmax), "011": (xmin, ymax, zmax),
    }
    faces = [
        ("001", "101", "111", "011"), ("000", "010", "110", "100"), ("000", "001", "011", "010"),
        ("100", "110", "111", "101"), ("010", "011", "111", "110"), ("000", "100", "101", "001"),
    ]
    for a, b, c, d in faces:
        tris.append((v[a], v[b], v[c]))
        tris.append((v[a], v[c], v[d]))


def _disc(tris: list, cx: float, cy: float, z: float, radius: float, segments: int, reverse: bool = False) -> None:
    center = (cx, cy, z)
    for index in range(segments):
        a = 2.0 * math.pi * index / segments
        b = 2.0 * math.pi * (index + 1) / segments
        p1 = (round(cx + radius * math.cos(a), 9), round(cy + radius * math.sin(a), 9), z)
        p2 = (round(cx + radius * math.cos(b), 9), round(cy + radius * math.sin(b), 9), z)
        tris.append((center, p2, p1) if reverse else (center, p1, p2))


def _normal(tri: tuple[tuple[float, float, float], ...]) -> tuple[float, float, float]:
    ax, ay, az = [tri[1][i] - tri[0][i] for i in range(3)]
    bx, by, bz = [tri[2][i] - tri[0][i] for i in range(3)]
    nx, ny, nz = ay * bz - az * by, az * bx - ax * bz, ax * by - ay * bx
    length = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
    return (nx / length, ny / length, nz / length)


def _parameters_csv() -> bytes:
    stream = io.StringIO()
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(["parameter_id", "name", "value", "unit", "description"])
    writer.writerow(["geometry_x_dimension", "geometry_x_dimension", "1.20", "m", "Demonstration assumption for STL bounding-box x dimension; not vendor data."])
    writer.writerow(["geometry_y_dimension", "geometry_y_dimension", "1.20", "m", "Demonstration assumption for STL bounding-box y dimension; not vendor data."])
    writer.writerow(["geometry_z_dimension", "geometry_z_dimension", "0.24", "m", "Demonstration assumption for STL bounding-box z dimension; not vendor data."])
    return stream.getvalue().encode("utf-8")


def _readme() -> str:
    return "\n".join(
        [
            "# DE2Sim Phase 6C Geometry Demonstration",
            "",
            "This package contains a real ASCII STL mesh for a generic low-polygon UAS training visualization.",
            "The mesh is a demonstration CAD-export artifact, not vendor-authoritative vehicle geometry.",
            "Explicit demonstration dimensions are x=1.20 m, y=1.20 m, z=0.24 m and are validated against parameters/geometry_parameters.csv.",
            "The mesh is used for visualization only; it is not used for flight dynamics, mass properties, aerodynamics, survivability, certification, collision, material, or articulation modeling.",
            "",
        ]
    )


def _json_bytes(payload: dict) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _f(value: float) -> str:
    text = f"{value:.9f}".rstrip("0").rstrip(".")
    return "0" if text == "-0" else text


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build deterministic DE2Sim Phase 6C geometry demo package.")
    parser.add_argument("--base-package", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        print(build_geometry_package(args.base_package, args.output))
    except GeometryPackageError as exc:
        print(f"error: {exc}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
