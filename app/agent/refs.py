"""Resolve values produced by earlier steps. Ambiguous matches are never guessed."""

from __future__ import annotations

import re
from typing import Any

from app.errors import AgentError, AmbiguousTargetError

_REF = re.compile(r"^([A-Za-z0-9_-]+)\.(match|latest|matches|operations|count|destination)$")


def resolve_arguments(value: Any, results: dict[str, dict]) -> Any:
    if isinstance(value, dict) and set(value.keys()) == {"$ref"}:
        return _resolve_ref(str(value["$ref"]), results)
    if isinstance(value, dict):
        return {key: resolve_arguments(item, results) for key, item in value.items()}
    if isinstance(value, list):
        return [resolve_arguments(item, results) for item in value]
    return value


def _resolve_ref(ref: str, results: dict[str, dict]) -> Any:
    match = _REF.match(ref)
    if match is None:
        raise AgentError(f"Could not resolve reference {ref}")
    step_id, kind = match.group(1), match.group(2)
    data = results.get(step_id)
    if data is None:
        raise AgentError(f"Step {step_id} has no result yet")
    matches = data.get("matches") or []
    if kind == "count":
        return data.get("count", len(matches))
    if kind == "matches":
        return [item["path"] for item in matches]
    if kind == "operations":
        return data.get("operations") or []
    if kind == "destination":
        destination = data.get("destination") or data.get("path")
        if not destination:
            raise AgentError("The previous step has no destination path")
        return destination
    if kind == "latest":
        if not data.get("latest"):
            raise AgentError("No file was found")
        return data["latest"]
    if not matches:
        raise AgentError("No matching file was found")
    if len(matches) > 1:
        paths = [item["path"] for item in matches[:20]]
        raise AmbiguousTargetError("Several matches were found. Specify one full path:\n" + "\n".join(paths), paths)
    return matches[0]["path"]
