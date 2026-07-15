"""JSON I/O for DE2Sim ASOT documents."""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from typing import Any

from de2sim.asot.schema import ASOTDocument


class ASOTIOError(Exception):
    """Controlled ASOT JSON I/O failure."""


def _json_text(document: ASOTDocument) -> str:
    return json.dumps(document.to_dict(), indent=2, sort_keys=False, ensure_ascii=False) + "\n"


def write_asot_json(document: ASOTDocument, path: Path | str) -> Path:
    """Write an ASOT document as deterministic UTF-8 JSON with atomic replacement."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    text = _json_text(document)
    temp_name = ""
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            newline="\n",
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temp_name = stream.name
            stream.write(text)
        os.replace(temp_name, target)
    except OSError as exc:
        if temp_name:
            try:
                Path(temp_name).unlink()
            except OSError:
                pass
        raise ASOTIOError(f"failed to write ASOT JSON: {exc}") from exc
    return target


def read_asot_json(path: Path | str) -> ASOTDocument:
    """Read ASOT JSON and raise controlled errors for malformed JSON."""
    source = Path(path)
    try:
        text = source.read_text(encoding="utf-8")
        payload: Any = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ASOTIOError(f"malformed ASOT JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}") from exc
    except OSError as exc:
        raise ASOTIOError(f"failed to read ASOT JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ASOTIOError("ASOT JSON root must be an object")
    return ASOTDocument.from_dict(payload)


def asot_json_text(document: ASOTDocument) -> str:
    """Return the deterministic JSON representation used for file output."""
    return _json_text(document)
