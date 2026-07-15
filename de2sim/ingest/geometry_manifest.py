"""Geometry manifest classification for Phase 1A.

Phase 1A records geometry files as package references only. It does not parse
or validate the contents as CAD or 3D geometry.
"""

from __future__ import annotations

from pathlib import PurePosixPath


GEOMETRY_EXTENSIONS = {".glb", ".gltf", ".obj", ".stl"}

_ROLE_FOLDERS = {
    "geometry": "geometry",
    "geometries": "geometry",
    "geom": "geometry",
    "models": "geometry",
    "model": "geometry",
    "mesh": "geometry",
    "meshes": "geometry",
    "sysml": "sysml",
    "sysmlv2": "sysml",
    "requirements": "requirements",
    "requirement": "requirements",
    "reqs": "requirements",
    "parameters": "parameters",
    "parameter": "parameters",
    "params": "parameters",
    "physical_models": "physical_model",
    "physical_model": "physical_model",
    "physics": "physical_model",
    "dynamics": "physical_model",
    "documentation": "documentation",
    "documents": "documentation",
    "docs": "documentation",
    "doc": "documentation",
}

_EXTENSION_ROLES = {
    ".glb": "geometry",
    ".gltf": "geometry",
    ".obj": "geometry",
    ".stl": "geometry",
    ".sysml": "sysml",
    ".xlsx": "parameters",
    ".csv": "requirements",
    ".json": "requirements",
    ".yaml": "requirements",
    ".yml": "requirements",
    ".md": "documentation",
    ".txt": "documentation",
    ".pdf": "documentation",
    ".docx": "documentation",
}

_ROLE_ALLOWED_EXTENSIONS = {
    "geometry": GEOMETRY_EXTENSIONS,
    "sysml": {".sysml", ".sysml.json"},
    "requirements": {".csv", ".json", ".yaml", ".yml", ".md", ".txt", ".pdf", ".docx"},
    "parameters": {".csv", ".json", ".yaml", ".yml", ".xlsx"},
    "physical_model": {".md", ".txt", ".pdf", ".docx", ".json", ".yaml", ".yml"},
    "documentation": {".csv", ".json", ".yaml", ".yml", ".md", ".txt", ".pdf", ".docx"},
}


def normalized_extension(relative_path: str) -> str:
    """Return the Phase 1A extension, including compound .sysml.json."""
    lower_name = PurePosixPath(relative_path).name.lower()
    if lower_name.endswith(".sysml.json"):
        return ".sysml.json"
    return PurePosixPath(lower_name).suffix


def classify_package_member(relative_path: str) -> tuple[str, list[str]]:
    """Classify a package file into a Phase 1A role."""
    warnings: list[str] = []
    path = PurePosixPath(relative_path)
    extension = normalized_extension(relative_path)

    folder_role = None
    for parent in path.parts[:-1]:
        normalized = parent.strip().lower().replace("-", "_").replace(" ", "_")
        if normalized in _ROLE_FOLDERS:
            folder_role = _ROLE_FOLDERS[normalized]
            break

    if folder_role:
        allowed = _ROLE_ALLOWED_EXTENSIONS.get(folder_role, set())
        if extension in allowed or not extension:
            return folder_role, warnings
        warnings.append(
            f"parent folder suggests {folder_role}, but extension {extension or '<none>'} is not recognized for that role"
        )
        return folder_role, warnings

    if extension == ".sysml.json":
        return "sysml", warnings

    return _EXTENSION_ROLES.get(extension, "unsupported"), warnings


def parser_status_for_role(role: str) -> str:
    """Return the Phase 1A parser status for a classified file role."""
    if role == "geometry":
        return "referenced_not_parsed"
    if role == "unsupported":
        return "unsupported"
    return "referenced_not_parsed"
