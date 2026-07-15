"""Secure engineering-package ZIP ingestion for DE2Sim Phase 1A."""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import mimetypes
import os
import shutil
import stat
import zipfile
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from de2sim.ingest.geometry_manifest import (
    classify_package_member,
    normalized_extension,
    parser_status_for_role,
)


SCHEMA_VERSION = "de2sim.package_manifest.v1"


class PackageValidationError(Exception):
    """Controlled validation failure for an engineering package."""


def sha256_file(path: Path) -> str:
    """Return the SHA-256 hex digest for a file."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_nonempty_directory(path: Path) -> bool:
    return path.is_dir() and any(path.iterdir())


def _zipinfo_is_symlink(info: zipfile.ZipInfo) -> bool:
    mode = (info.external_attr >> 16) & 0o170000
    return mode == stat.S_IFLNK


def _validate_member_name(member_name: str, extraction_root: Path) -> str:
    if not member_name or member_name.endswith("/"):
        raise PackageValidationError(f"unsafe archive member: {member_name!r}")

    if "\\" in member_name:
        windows_path = PureWindowsPath(member_name)
        if windows_path.is_absolute() or windows_path.drive:
            raise PackageValidationError(f"unsafe archive member uses an absolute or drive-qualified path: {member_name}")

    posix_path = PurePosixPath(member_name)
    windows_path = PureWindowsPath(member_name)
    if posix_path.is_absolute() or windows_path.is_absolute() or windows_path.drive:
        raise PackageValidationError(f"unsafe archive member uses an absolute or drive-qualified path: {member_name}")

    if any(part in ("", ".", "..") for part in posix_path.parts):
        raise PackageValidationError(f"unsafe archive member uses path traversal: {member_name}")

    relative_path = "/".join(posix_path.parts)
    destination = (extraction_root / Path(*posix_path.parts)).resolve()
    root = extraction_root.resolve()
    try:
        destination.relative_to(root)
    except ValueError as exc:
        raise PackageValidationError(
            f"unsafe archive member resolves outside the extraction directory: {member_name}"
        ) from exc

    return relative_path


def _media_type(path: str) -> str:
    extension = normalized_extension(path)
    if extension == ".glb":
        return "model/gltf-binary"
    if extension == ".gltf":
        return "model/gltf+json"
    if extension == ".obj":
        return "model/obj"
    if extension == ".stl":
        return "model/stl"
    if extension == ".sysml":
        return "text/plain"
    if extension in {".yaml", ".yml"}:
        return "application/x-yaml"
    guessed, _ = mimetypes.guess_type(path)
    return guessed or "application/octet-stream"


def _write_member(zf: zipfile.ZipFile, info: zipfile.ZipInfo, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zf.open(info, "r") as source, destination.open("wb") as target:
        shutil.copyfileobj(source, target)


def ingest_engineering_package(package_path: Path | str, output_dir: Path | str) -> Path:
    """Validate, extract, and write a deterministic package manifest."""
    package = Path(package_path)
    output = Path(output_dir)

    if not package.exists():
        raise PackageValidationError(f"engineering package does not exist: {package}")
    if not package.is_file():
        raise PackageValidationError(f"engineering package is not a regular file: {package}")
    if package.suffix.lower() != ".zip":
        raise PackageValidationError(f"engineering package must have a .zip extension: {package}")
    if not zipfile.is_zipfile(package):
        raise PackageValidationError(f"engineering package is not a valid ZIP archive: {package}")

    extraction_root = output / "work" / "package"
    if _is_nonempty_directory(extraction_root):
        raise PackageValidationError(f"extraction directory already exists and is not empty: {extraction_root}")

    output.mkdir(parents=True, exist_ok=True)
    extraction_root.mkdir(parents=True, exist_ok=True)

    file_entries: list[dict[str, Any]] = []
    archive_records: list[tuple[zipfile.ZipInfo, str]] = []
    package_digest = sha256_file(package)

    try:
        with zipfile.ZipFile(package, "r") as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                if _zipinfo_is_symlink(info):
                    raise PackageValidationError(f"unsafe archive member appears to be a symbolic link: {info.filename}")
                relative_path = _validate_member_name(info.filename, extraction_root)
                archive_records.append((info, relative_path))

            for info, relative_path in sorted(archive_records, key=lambda item: item[1]):
                destination = extraction_root / Path(*PurePosixPath(relative_path).parts)
                _write_member(zf, info, destination)
                role, warnings = classify_package_member(relative_path)
                extension = normalized_extension(relative_path)
                file_entries.append(
                    {
                        "relative_path": relative_path,
                        "role": role,
                        "extension": extension,
                        "media_type": _media_type(relative_path),
                        "size_bytes": destination.stat().st_size,
                        "sha256": sha256_file(destination),
                        "parser_status": parser_status_for_role(role),
                        "warnings": warnings,
                    }
                )
    except zipfile.BadZipFile as exc:
        raise PackageValidationError(f"engineering package is not a valid ZIP archive: {package}") from exc
    except OSError as exc:
        raise PackageValidationError(f"failed to extract engineering package: {exc}") from exc

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "package_filename": package.name,
        "package_sha256": package_digest,
        "generated_at_utc": _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "extraction_root": os.path.relpath(extraction_root.resolve(), output.resolve()).replace(os.sep, "/"),
        "file_count": len(file_entries),
        "warnings": [],
        "files": file_entries,
    }

    manifest_path = output / "package_manifest.json"
    with manifest_path.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(manifest, stream, indent=2, sort_keys=False)
        stream.write("\n")
    return manifest_path
