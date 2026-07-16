"""Deterministic SHA-256 helpers for DE2Sim provenance."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


CHUNK_SIZE = 1024 * 1024


class HashingError(Exception):
    """Controlled hashing failure."""


def sha256_bytes(data: bytes) -> str:
    """Return the SHA-256 hex digest for bytes."""
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path | str, chunk_size: int = CHUNK_SIZE) -> str:
    """Return the SHA-256 hex digest for a file using chunked reads."""
    source = Path(path)
    try:
        digest = hashlib.sha256()
        with source.open("rb") as stream:
            for chunk in iter(lambda: stream.read(chunk_size), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except FileNotFoundError as exc:
        raise HashingError(f"file does not exist: {source}") from exc
    except OSError as exc:
        raise HashingError(f"failed to read file for SHA-256: {source}") from exc


def normalized_json_bytes(value: Any) -> bytes:
    """Return deterministic UTF-8 JSON bytes for hashing."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def sha256_normalized_json(value: Any) -> str:
    """Return the SHA-256 digest of normalized JSON."""
    return sha256_bytes(normalized_json_bytes(value))
