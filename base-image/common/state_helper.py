"""Helpers for persisting per-request state in the artifact store."""

from __future__ import annotations

import os
from typing import Any, Dict

from storage_helper import object_exists, read_json, write_json

ARTIFACT_BUCKET = os.getenv("ARTIFACT_BUCKET", "fave-artifacts")


def state_uri(request_id: str) -> str:
    """Return canonical URI for the request state file."""
    return f"s3://{ARTIFACT_BUCKET}/requests/{request_id}/metadata/state.json"


def load_state(request_id: str) -> Dict[str, Any]:
    """Load state.json if it exists, else return default skeleton."""
    uri = state_uri(request_id)
    if object_exists(uri):
        return read_json(uri)
    return {"request_id": request_id, "status": "INIT", "stages": []}


def save_state(request_id: str, data: Dict[str, Any]) -> str:
    """Overwrite the state file."""
    data.setdefault("request_id", request_id)
    return write_json(data, state_uri(request_id))


def update_state(request_id: str, **patch: Any) -> Dict[str, Any]:
    """Load state, update with provided fields, and persist."""
    state = load_state(request_id)
    state.update(patch)
    save_state(request_id, state)
    return state


def append_stage_entry(request_id: str, entry: Dict[str, Any]) -> Dict[str, Any]:
    """Append a stage log entry to the state."""
    state = load_state(request_id)
    stages = state.setdefault("stages", [])
    stages.append(entry)
    save_state(request_id, state)
    return state
