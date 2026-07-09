"""Resource tracking manifest for cross-session continuity.

Tracks Databricks resources created through the MCP server in a local
`.databricks-resources.json` file. This allows agents to see what was
created in previous sessions and avoid duplicates.
"""

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Resource deleter registry
# ---------------------------------------------------------------------------
# Each tool module registers a callable that deletes a resource given its ID.
# This avoids hard-coding every resource type inside the manifest tool layer.
_RESOURCE_DELETERS: Dict[str, Callable[[str], None]] = {}


def register_deleter(resource_type: str, fn: Callable[[str], None]) -> None:
    """Register a delete function for a resource type.

    Tool modules call this at import time so the manifest tool layer can
    delete any tracked resource without knowing implementation details.

    Args:
        resource_type: The manifest resource type key (e.g. ``"job"``).
        fn: A callable that takes a ``resource_id`` string and deletes
            the corresponding Databricks resource.  Should raise on failure.
    """
    _RESOURCE_DELETERS[resource_type] = fn


MANIFEST_FILENAME = ".databricks-resources.json"
MANIFEST_VERSION = 1


def _get_manifest_path() -> Path:
    """Get the path to the manifest file.

    Looks for ``MANIFEST_FILENAME`` relative to CWD (MCP servers are
    launched from the project root).
    """
    return Path(os.getcwd()) / MANIFEST_FILENAME


def _read_manifest() -> Dict[str, Any]:
    """Read the manifest file, returning an empty structure if missing."""
    path = _get_manifest_path()
    if not path.exists():
        return {"version": MANIFEST_VERSION, "resources": []}
    try:
        with open(path, "r") as f:
            data = json.load(f)
        if not isinstance(data, dict) or "resources" not in data:
            return {"version": MANIFEST_VERSION, "resources": []}
        return data
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to read manifest %s: %s", path, exc)
        return {"version": MANIFEST_VERSION, "resources": []}


def _write_manifest(data: Dict[str, Any]) -> None:
    """Atomically write the manifest file."""
    path = _get_manifest_path()
    try:
        # Write to a temp file in the same directory, then rename
        fd, tmp_path = tempfile.mkstemp(dir=path.parent, prefix=".manifest-tmp-", suffix=".json")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(data, f, indent=2)
                f.write("\n")
            os.replace(tmp_path, path)
        except Exception:
            # Clean up temp file on failure
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
    except OSError as exc:
        logger.warning("Failed to write manifest %s: %s", path, exc)


def _now_iso() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def track_resource(
    resource_type: str,
    name: str,
    resource_id: str,
    url: Optional[str] = None,
) -> None:
    """Track a created/updated resource in the manifest.

    Upsert logic:
    - If a resource with the same type+id exists, update name/url/updated_at.
    - If a resource with the same type+name exists but different id, update the id.
    - Otherwise, append a new entry.

    This is best-effort: failures are logged but never raised.
    """
    try:
        data = _read_manifest()
        resources: List[Dict[str, Any]] = data.get("resources", [])
        now = _now_iso()

        # Try to find by type+id
        for r in resources:
            if r.get("type") == resource_type and r.get("id") == resource_id:
                r["name"] = name
                if url:
                    r["url"] = url
                r["updated_at"] = now
                _write_manifest(data)
                return

        # Try to find by type+name (handles ID changes across sessions)
        for r in resources:
            if r.get("type") == resource_type and r.get("name") == name:
                r["id"] = resource_id
                if url:
                    r["url"] = url
                r["updated_at"] = now
                _write_manifest(data)
                return

        # New resource
        entry: Dict[str, Any] = {
            "type": resource_type,
            "name": name,
            "id": resource_id,
            "created_at": now,
            "updated_at": now,
        }
        if url:
            entry["url"] = url
        resources.append(entry)
        data["resources"] = resources
        _write_manifest(data)
    except Exception as exc:
        logger.warning("Failed to track resource %s/%s: %s", resource_type, name, exc)


def remove_resource(resource_type: str, resource_id: str) -> bool:
    """Remove a resource from the manifest by type+id.

    Returns True if the resource was found and removed.
    """
    try:
        data = _read_manifest()
        resources = data.get("resources", [])
        original_count = len(resources)
        data["resources"] = [
            r for r in resources if not (r.get("type") == resource_type and r.get("id") == resource_id)
        ]
        if len(data["resources"]) < original_count:
            _write_manifest(data)
            return True
        return False
    except Exception as exc:
        logger.warning("Failed to remove resource %s/%s: %s", resource_type, resource_id, exc)
        return False


def list_resources(resource_type: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return tracked resources, optionally filtered by type."""
    data = _read_manifest()
    resources = data.get("resources", [])
    if resource_type:
        resources = [r for r in resources if r.get("type") == resource_type]
    return resources
