"""
Databricks Apps - App Lifecycle Management

Functions for managing Databricks Apps lifecycle using the Databricks SDK.
"""

import time
import base64
import json
import os
import socket
import ssl
import struct
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from databricks.sdk.service.apps import App, AppDeployment

from ..auth import get_workspace_client


def create_app(
    name: str,
    description: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create a new Databricks App.

    Args:
        name: App name (must be unique within the workspace).
        description: Optional human-readable description.

    Returns:
        Dictionary with app details including name, url, and status.
    """
    w = get_workspace_client()
    # SDK compatibility: newer databricks-sdk expects App object as the
    # first positional arg (app=...), while older versions accepted kwargs.
    try:
        app = w.apps.create(name=name, description=description)
    except TypeError as e:
        if "unexpected keyword argument 'name'" not in str(e):
            raise
        app = w.apps.create(app=App(name=name, description=description))

    # In newer SDK versions, create() returns a Wait[App].
    if hasattr(app, "result"):
        app = app.result()
    return _app_to_dict(app)


def get_app(name: str) -> Dict[str, Any]:
    """
    Get details for a Databricks App.

    Args:
        name: App name.

    Returns:
        Dictionary with app details including name, url, status, and active deployment.
    """
    w = get_workspace_client()
    app = w.apps.get(name=name)
    return _app_to_dict(app)


def list_apps(
    name_contains: Optional[str] = None,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """
    List Databricks Apps in the workspace.

    Returns a limited number of apps, optionally filtered by name substring.
    Apps are returned in API order (most recently created first).

    Args:
        name_contains: Optional substring filter applied to app names
            (case-insensitive). Only apps whose name contains this string
            are returned.
        limit: Maximum number of apps to return (default: 20).
            Use 0 for no limit (returns all apps).

    Returns:
        List of dictionaries with app details.
    """
    w = get_workspace_client()
    results: List[Dict[str, Any]] = []

    for app in w.apps.list():
        if name_contains and name_contains.lower() not in (getattr(app, "name", "") or "").lower():
            continue
        results.append(_app_to_dict(app))
        if limit and len(results) >= limit:
            break

    return results


def deploy_app(
    app_name: str,
    source_code_path: str,
    mode: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Deploy a Databricks App from a workspace source path.

    Args:
        app_name: Name of the app to deploy.
        source_code_path: Workspace path to the app source code
            (e.g., /Workspace/Users/user@example.com/my_app).
        mode: Optional deployment mode (e.g., "snapshot").

    Returns:
        Dictionary with deployment details including deployment_id and status.
    """
    w = get_workspace_client()
    normalized_source_code_path = _normalize_workspace_source_path(source_code_path)
    normalized_mode = _normalize_deploy_mode(mode)

    # Capture currently active deployment so we can detect rollout transition.
    previous_deployment_id: Optional[str] = None
    try:
        current = w.apps.get(name=app_name)
        if getattr(current, "active_deployment", None):
            previous_deployment_id = getattr(current.active_deployment, "deployment_id", None)
    except Exception:
        # Best effort only; deployment can still proceed.
        previous_deployment_id = None

    last_error: Exception | None = None
    deployment: Any = None
    for _ in range(5):
        try:
            deployment = w.apps.deploy(
                app_name=app_name,
                app_deployment=AppDeployment(
                    source_code_path=normalized_source_code_path,
                    mode=normalized_mode,
                ),
            )
            break
        except Exception as e:
            last_error = e
            # New app creation can take a short time to become deployable.
            time.sleep(2)
    if deployment is None:
        assert last_error is not None
        raise last_error

    # SDK compatibility: newer databricks-sdk may return Wait[AppDeployment].
    if hasattr(deployment, "result"):
        deployment = deployment.result()

    result = _deployment_to_dict(deployment)
    new_deployment_id = result.get("deployment_id")

    # In some API/SDK combinations, the immediate deploy response can still point
    # to the previously active deployment. Poll briefly for the active deployment
    # to transition so callers can reliably detect a redeploy.
    if not new_deployment_id or (previous_deployment_id and new_deployment_id == previous_deployment_id):
        deadline = time.time() + 60
        while time.time() < deadline:
            try:
                current = w.apps.get(name=app_name)
                active = getattr(current, "active_deployment", None)
                active_id = getattr(active, "deployment_id", None) if active else None
                if active_id and active_id != previous_deployment_id:
                    return _deployment_to_dict(active)
            except Exception:
                # transient read failures during rollout; retry
                pass
            time.sleep(2)

    return result


def _normalize_workspace_source_path(source_code_path: str) -> str:
    """Normalize app source path to a workspace absolute path."""
    path = (source_code_path or "").strip()
    if not path:
        return path
    if path.startswith("/Workspace/"):
        return path
    # Accept common workspace-root shortcuts and normalize.
    if path.startswith(("/Users/", "/Shared/", "/Repos/")):
        return f"/Workspace{path}"
    return path


def _normalize_deploy_mode(mode: Optional[str]) -> Optional[str]:
    """Normalize deployment mode to the API-expected uppercase form."""
    if mode is None:
        return None
    normalized = mode.strip()
    if not normalized:
        return None
    return normalized.upper()


def delete_app(name: str) -> Dict[str, str]:
    """
    Delete a Databricks App.

    Args:
        name: App name to delete.

    Returns:
        Dictionary confirming deletion.
    """
    w = get_workspace_client()
    w.apps.delete(name=name)
    return {"name": name, "status": "deleted"}


def get_app_logs(
    app_name: str,
    deployment_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Get logs for a Databricks App deployment.

    If deployment_id is not provided, gets logs for the active deployment.

    Args:
        app_name: App name.
        deployment_id: Optional specific deployment ID. If None, uses the
            active deployment.

    Returns:
        Dictionary with deployment logs.
    """
    w = get_workspace_client()

    # If no deployment_id, get the active one
    if not deployment_id:
        app = w.apps.get(name=app_name)
        if app.active_deployment:
            deployment_id = app.active_deployment.deployment_id
        else:
            return {"app_name": app_name, "error": "No active deployment found"}
    if not deployment_id:
        return {"app_name": app_name, "error": "No deployment ID available"}

    logs = _get_app_logs_via_logz_ws(app_name=app_name, deployment_id=deployment_id)
    source = "logz_ws"

    return {
        "app_name": app_name,
        "deployment_id": deployment_id,
        "logs": logs,
        "logs_source": source,
    }


def _ws_send_text(sock: socket.socket, text: str) -> None:
    payload = text.encode("utf-8")
    first = 0x81  # FIN + text
    length = len(payload)
    mask_bit = 0x80  # client->server frames must be masked

    if length < 126:
        header = bytes([first, mask_bit | length])
    elif length < 65536:
        header = bytes([first, mask_bit | 126]) + struct.pack("!H", length)
    else:
        header = bytes([first, mask_bit | 127]) + struct.pack("!Q", length)

    mask = os.urandom(4)
    masked_payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
    sock.sendall(header + mask + masked_payload)


def _ws_recv_frame(sock: socket.socket) -> tuple[int, bytes] | tuple[None, None]:
    header = sock.recv(2)
    if not header:
        return None, None

    b1, b2 = header[0], header[1]
    opcode = b1 & 0x0F
    masked = (b2 & 0x80) != 0
    length = b2 & 0x7F

    if length == 126:
        length = struct.unpack("!H", sock.recv(2))[0]
    elif length == 127:
        length = struct.unpack("!Q", sock.recv(8))[0]

    mask = sock.recv(4) if masked else None
    payload = b""
    while len(payload) < length:
        chunk = sock.recv(length - len(payload))
        if not chunk:
            break
        payload += chunk

    if masked and mask:
        payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
    return opcode, payload


def _get_app_logs_via_logz_ws(app_name: str, deployment_id: Optional[str]) -> str:
    """Fetch app logs from app /logz websocket stream."""
    w = get_workspace_client()
    app = w.apps.get(name=app_name)
    app_url = (getattr(app, "url", None) or "").rstrip("/")
    if not app_url:
        raise ValueError(f"App {app_name!r} has no URL; cannot fetch /logz logs")

    parsed = urlparse(app_url)
    host = parsed.netloc
    if not host:
        raise ValueError(f"Invalid app URL: {app_url!r}")

    auth_headers = w.config.authenticate()
    authorization = auth_headers.get("Authorization")
    if not authorization:
        raise ValueError("No authorization header available for /logz websocket")

    ws_path = "/logz/stream"
    key_b64 = base64.b64encode(os.urandom(16)).decode("ascii")
    request = (
        f"GET {ws_path} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key_b64}\r\n"
        "Sec-WebSocket-Version: 13\r\n"
        f"Authorization: {authorization}\r\n"
        f"Origin: {app_url}\r\n"
        "\r\n"
    )

    raw = socket.create_connection((host, 443), timeout=10)
    tls = ssl.create_default_context().wrap_socket(raw, server_hostname=host)
    try:
        tls.sendall(request.encode("utf-8"))
        response = b""
        while b"\r\n\r\n" not in response:
            chunk = tls.recv(4096)
            if not chunk:
                break
            response += chunk
        status_line = response.split(b"\r\n", 1)[0].decode("utf-8", errors="replace")
        if " 101 " not in status_line:
            raise RuntimeError(f"WebSocket upgrade failed: {status_line}")

        # Send search term; deployment_id narrows logs to a specific rollout.
        _ws_send_text(tls, deployment_id or "")
        tls.settimeout(1.5)

        lines: list[str] = []
        deadline = time.time() + 8
        max_entries = 500

        while time.time() < deadline and len(lines) < max_entries:
            try:
                opcode, payload = _ws_recv_frame(tls)
            except socket.timeout:
                break

            if opcode is None or opcode == 0x8:  # EOF / close
                break
            if opcode == 0x9:  # ping -> pong
                first = 0x8A
                plen = len(payload)
                if plen < 126:
                    header = bytes([first, 0x80 | plen])
                elif plen < 65536:
                    header = bytes([first, 0x80 | 126]) + struct.pack("!H", plen)
                else:
                    header = bytes([first, 0x80 | 127]) + struct.pack("!Q", plen)
                mask = os.urandom(4)
                masked_payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
                tls.sendall(header + mask + masked_payload)
                continue
            if opcode != 0x1:
                continue

            text = payload.decode("utf-8", errors="replace")
            if text == "\x00":
                break
            if not text.strip():
                continue

            try:
                entry = json.loads(text)
                ts = entry.get("timestamp", "")
                source = entry.get("source", "")
                severity = entry.get("severity", "")
                message = entry.get("message", "")
                prefix = " ".join(x for x in [str(ts), str(source), str(severity)] if x).strip()
                lines.append(f"{prefix}: {message}" if prefix else str(message))
            except Exception:
                lines.append(text)

        return "\n".join(lines).strip()
    finally:
        try:
            tls.close()
        except Exception:
            pass


def _app_to_dict(app: Any) -> Dict[str, Any]:
    """Convert an App SDK object to a dictionary."""
    result = {
        "name": getattr(app, "name", None),
        "description": getattr(app, "description", None),
        "url": getattr(app, "url", None),
        "status": None,
        "create_time": str(getattr(app, "create_time", None)),
        "update_time": str(getattr(app, "update_time", None)),
    }

    # Extract status from compute_status or status
    compute_status = getattr(app, "compute_status", None)
    if compute_status:
        result["status"] = getattr(compute_status, "state", None)
        if result["status"]:
            result["status"] = str(result["status"])

    # Extract active deployment info
    active_deployment = getattr(app, "active_deployment", None)
    if active_deployment:
        result["active_deployment"] = _deployment_to_dict(active_deployment)

    return result


def _deployment_to_dict(deployment: Any) -> Dict[str, Any]:
    """Convert an AppDeployment SDK object to a dictionary."""
    result = {
        "deployment_id": getattr(deployment, "deployment_id", None),
        "source_code_path": getattr(deployment, "source_code_path", None),
        "mode": str(getattr(deployment, "mode", None)),
        "create_time": str(getattr(deployment, "create_time", None)),
    }

    status = getattr(deployment, "status", None)
    if status:
        result["state"] = str(getattr(status, "state", None))
        result["message"] = getattr(status, "message", None)

    return result
