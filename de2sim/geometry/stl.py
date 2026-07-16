"""Safe, dependency-free STL parsing for Phase 6C geometry ingestion."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
from pathlib import Path, PurePosixPath
import re
import struct
from typing import Any


DEFAULT_MAX_SOURCE_SIZE = 5 * 1024 * 1024
DEFAULT_MAX_FACETS = 100_000
_BINARY_HEADER_BYTES = 80
_BINARY_COUNT_BYTES = 4
_BINARY_FACET_BYTES = 50


class STLParseError(Exception):
    """Controlled STL parsing failure."""


@dataclass(frozen=True)
class STLParseOptions:
    max_source_size: int = DEFAULT_MAX_SOURCE_SIZE
    max_facets: int = DEFAULT_MAX_FACETS


def parse_stl(path: Path | str, unit: str, options: STLParseOptions | None = None) -> dict[str, Any]:
    """Parse ASCII or binary STL and return deterministic extraction metadata."""
    source = Path(path)
    opts = options or STLParseOptions()
    if unit.strip() == "":
        raise STLParseError("geometry unit is missing; STL units must be supplied by trusted metadata")
    if not source.is_file():
        raise STLParseError(f"STL source does not exist: {source}")
    size = source.stat().st_size
    if size > opts.max_source_size:
        raise STLParseError(f"STL source exceeds maximum size: {size} > {opts.max_source_size}")
    data = source.read_bytes()
    source_hash = hashlib.sha256(data).hexdigest()
    fmt = _detect_format(data, opts)
    if fmt == "binary_stl":
        solid_name, triangles, normals = _parse_binary(data, opts)
    else:
        solid_name, triangles, normals = _parse_ascii(data, opts)
    return _metadata(source, source_hash, fmt, solid_name, triangles, normals, unit)


def _detect_format(data: bytes, opts: STLParseOptions) -> str:
    if _looks_ascii(data):
        return "ascii_stl"
    if len(data) >= _BINARY_HEADER_BYTES + _BINARY_COUNT_BYTES:
        count = struct.unpack("<I", data[_BINARY_HEADER_BYTES:_BINARY_HEADER_BYTES + _BINARY_COUNT_BYTES])[0]
        expected = _BINARY_HEADER_BYTES + _BINARY_COUNT_BYTES + count * _BINARY_FACET_BYTES
        if count <= opts.max_facets and expected == len(data):
            return "binary_stl"
        if count > opts.max_facets and expected >= len(data):
            raise STLParseError("impossible binary STL facet count")
        if expected > len(data) and not _looks_ascii(data):
            raise STLParseError("truncated binary STL")
    return "ascii_stl"


def _looks_ascii(data: bytes) -> bool:
    prefix = data[:512].lstrip().lower()
    return prefix.startswith(b"solid") and b"\x00" not in data[:1024]


def _parse_binary(data: bytes, opts: STLParseOptions) -> tuple[str, list[list[list[float]]], list[list[float]]]:
    if len(data) < _BINARY_HEADER_BYTES + _BINARY_COUNT_BYTES:
        raise STLParseError("truncated binary STL")
    count = struct.unpack("<I", data[_BINARY_HEADER_BYTES:_BINARY_HEADER_BYTES + _BINARY_COUNT_BYTES])[0]
    if count > opts.max_facets:
        raise STLParseError(f"STL facet count exceeds maximum: {count} > {opts.max_facets}")
    expected = _BINARY_HEADER_BYTES + _BINARY_COUNT_BYTES + count * _BINARY_FACET_BYTES
    if expected != len(data):
        raise STLParseError("truncated binary STL")
    triangles: list[list[list[float]]] = []
    normals: list[list[float]] = []
    offset = _BINARY_HEADER_BYTES + _BINARY_COUNT_BYTES
    for _index in range(count):
        values = struct.unpack("<12fH", data[offset:offset + _BINARY_FACET_BYTES])
        normals.append([_finite(values[0]), _finite(values[1]), _finite(values[2])])
        triangles.append(
            [
                [_finite(values[3]), _finite(values[4]), _finite(values[5])],
                [_finite(values[6]), _finite(values[7]), _finite(values[8])],
                [_finite(values[9]), _finite(values[10]), _finite(values[11])],
            ]
        )
        offset += _BINARY_FACET_BYTES
    name = data[:_BINARY_HEADER_BYTES].split(b"\x00", 1)[0].decode("ascii", errors="ignore").strip()
    return name, triangles, normals


_NUMBER = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
_FACET_RE = re.compile(
    rf"facet\s+normal\s+({_NUMBER})\s+({_NUMBER})\s+({_NUMBER})\s+"
    rf"outer\s+loop\s+"
    rf"vertex\s+({_NUMBER})\s+({_NUMBER})\s+({_NUMBER})\s+"
    rf"vertex\s+({_NUMBER})\s+({_NUMBER})\s+({_NUMBER})\s+"
    rf"vertex\s+({_NUMBER})\s+({_NUMBER})\s+({_NUMBER})\s+"
    rf"endloop\s+endfacet",
    re.IGNORECASE,
)


def _parse_ascii(data: bytes, opts: STLParseOptions) -> tuple[str, list[list[list[float]]], list[list[float]]]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise STLParseError("malformed ASCII STL: not valid UTF-8") from exc
    stripped = text.strip()
    if not stripped.lower().startswith("solid"):
        raise STLParseError("malformed ASCII STL: missing solid declaration")
    if not re.search(r"\bendsolid\b", stripped.splitlines()[-1], re.IGNORECASE):
        raise STLParseError("malformed ASCII STL: missing endsolid")
    solid_name = stripped.splitlines()[0].strip()[5:].strip()
    triangles: list[list[list[float]]] = []
    normals: list[list[float]] = []
    for match in _FACET_RE.finditer(stripped):
        values = [_finite(float(item)) for item in match.groups()]
        normals.append(values[0:3])
        triangles.append([values[3:6], values[6:9], values[9:12]])
        if len(triangles) > opts.max_facets:
            raise STLParseError(f"STL facet count exceeds maximum: {len(triangles)} > {opts.max_facets}")
    if not triangles:
        raise STLParseError("malformed ASCII STL: no facets")
    compact = re.sub(r"^\s*solid[^\n\r]*(?:\r?\n)?", "", stripped, count=1, flags=re.IGNORECASE)
    compact = _FACET_RE.sub("", compact)
    compact = re.sub(r"\s*endsolid[^\n\r]*\s*$", "", compact, flags=re.IGNORECASE)
    if compact.strip():
        raise STLParseError("malformed ASCII STL: unsupported tokens")
    return solid_name, triangles, normals


def _metadata(
    source: Path,
    source_hash: str,
    fmt: str,
    solid_name: str,
    triangles: list[list[list[float]]],
    normals: list[list[float]],
    unit: str,
) -> dict[str, Any]:
    vertices = [vertex for tri in triangles for vertex in tri]
    unique = sorted({_vertex_key(vertex) for vertex in vertices})
    mins = [min(vertex[axis] for vertex in vertices) for axis in range(3)]
    maxs = [max(vertex[axis] for vertex in vertices) for axis in range(3)]
    dimensions = {axis: _round(maxs[index] - mins[index]) for index, axis in enumerate(("x", "y", "z"))}
    center = {axis: _round((mins[index] + maxs[index]) / 2.0) for index, axis in enumerate(("x", "y", "z"))}
    degenerate = sum(1 for tri in triangles if _triangle_area2(tri) == 0.0)
    warnings = ["degenerate triangles detected"] if degenerate else []
    return {
        "source_path": PurePosixPath(source.name).as_posix(),
        "source_sha256": source_hash,
        "source_format": fmt,
        "declared_solid_name": solid_name,
        "facet_count": len(triangles),
        "vertex_count": len(vertices),
        "unique_vertex_count": len(unique),
        "degenerate_triangle_count": degenerate,
        "bounding_box_min": {axis: _round(mins[index]) for index, axis in enumerate(("x", "y", "z"))},
        "bounding_box_max": {axis: _round(maxs[index]) for index, axis in enumerate(("x", "y", "z"))},
        "dimensions": dimensions,
        "unit": unit,
        "center": center,
        "warnings": warnings,
        "validation_status": "parsed",
        "vertices": [[_round(coord) for coord in vertex] for vertex in vertices],
        "triangles": [[index * 3, index * 3 + 1, index * 3 + 2] for index in range(len(triangles))],
        "source_normals": [[_round(coord) for coord in normal] for normal in normals],
    }


def _finite(value: float) -> float:
    if not math.isfinite(value):
        raise STLParseError("STL contains NaN or infinite coordinate")
    return float(value)


def _vertex_key(vertex: list[float]) -> tuple[float, float, float]:
    return (_round(vertex[0]), _round(vertex[1]), _round(vertex[2]))


def _round(value: float) -> float:
    rounded = round(float(value), 9)
    return 0.0 if rounded == -0.0 else rounded


def _triangle_area2(tri: list[list[float]]) -> float:
    ax, ay, az = [tri[1][i] - tri[0][i] for i in range(3)]
    bx, by, bz = [tri[2][i] - tri[0][i] for i in range(3)]
    cross = (ay * bz - az * by, az * bx - ax * bz, ax * by - ay * bx)
    return _round(cross[0] * cross[0] + cross[1] * cross[1] + cross[2] * cross[2])
