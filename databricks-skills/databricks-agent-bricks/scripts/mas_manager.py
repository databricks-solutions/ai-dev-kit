#!/usr/bin/env python3
"""
Supervisor Agent (MAS) Manager - Self-contained CLI for MAS operations.

Usage:
    python mas_manager.py create_mas "Name" '{"agents": [...], "description": "...", "instructions": "..."}'
    python mas_manager.py get_mas TILE_ID
    python mas_manager.py find_mas "Name"
    python mas_manager.py update_mas TILE_ID '{"name": ..., "agents": [...], ...}'
    python mas_manager.py delete_mas TILE_ID
    python mas_manager.py list_mas
    python mas_manager.py add_examples TILE_ID '[{"question": "...", "guideline": "..."}]' [--wait]
    python mas_manager.py list_examples TILE_ID

    --wait on add_examples blocks until the MAS endpoint reaches ONLINE state
    (up to ~10 min after a create/update) before adding the examples.

Requires: databricks-sdk, requests
    pip install databricks-sdk requests
"""

import json
import logging
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

import requests
from databricks.sdk import WorkspaceClient

logger = logging.getLogger(__name__)


# ============================================================================
# Models
# ============================================================================


class TileType(Enum):
    """Tile types."""
    UNSPECIFIED = 0
    KIE = 1
    T2T = 2
    KA = 3
    MAO = 4
    MAS = 5


class EndpointStatus(Enum):
    """Endpoint status values."""
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"
    PROVISIONING = "PROVISIONING"
    NOT_READY = "NOT_READY"


@dataclass(frozen=True)
class MASIds:
    """Supervisor Agent identifiers."""
    tile_id: str
    name: str


# ============================================================================
# MAS Manager Class
# ============================================================================


class MASManager:
    """Manager for Supervisor Agent (MAS) operations.

    Uses raw HTTP API calls since there's no CLI for MAS operations.
    Authentication is handled via databricks-sdk WorkspaceClient.
    """

    def __init__(self, client: Optional[WorkspaceClient] = None):
        """Initialize the MAS Manager.

        Args:
            client: Optional WorkspaceClient (creates new one if not provided)
        """
        self.w: WorkspaceClient = client or WorkspaceClient()

    @staticmethod
    def sanitize_name(name: str) -> str:
        """Sanitize a name to ensure it's alphanumeric with only hyphens and underscores."""
        sanitized = name.replace(" ", "_")
        sanitized = re.sub(r"[^a-zA-Z0-9_-]", "_", sanitized)
        sanitized = re.sub(r"[_-]{2,}", "_", sanitized)
        sanitized = sanitized.strip("_-")
        if not sanitized:
            sanitized = "supervisor_agent"
        return sanitized

    # ========================================================================
    # MAS CRUD Operations
    # ========================================================================

    def create(
        self,
        name: str,
        agents: List[Dict[str, Any]],
        description: Optional[str] = None,
        instructions: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a Supervisor Agent with specified agents."""
        payload = {"name": self.sanitize_name(name), "agents": agents}
        if description:
            payload["description"] = description
        if instructions:
            payload["instructions"] = instructions
        return self._post("/api/2.0/multi-agent-supervisors", payload)

    def get(self, tile_id: str) -> Optional[Dict[str, Any]]:
        """Get MAS by tile_id."""
        try:
            return self._get(f"/api/2.0/multi-agent-supervisors/{tile_id}")
        except Exception as e:
            if "does not exist" in str(e).lower() or "not found" in str(e).lower():
                return None
            raise

    def update(
        self,
        tile_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        instructions: Optional[str] = None,
        agents: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Update a Supervisor Agent."""
        payload = {"tile_id": tile_id}
        if name:
            payload["name"] = self.sanitize_name(name)
        if description:
            payload["description"] = description
        if instructions:
            payload["instructions"] = instructions
        if agents:
            payload["agents"] = agents
        return self._patch(f"/api/2.0/multi-agent-supervisors/{tile_id}", payload)

    def delete(self, tile_id: str) -> None:
        """Delete a Supervisor Agent."""
        self._delete(f"/api/2.0/tiles/{tile_id}")

    def find_by_name(self, name: str) -> Optional[MASIds]:
        """Find a MAS by exact display name."""
        sanitized_name = self.sanitize_name(name)
        filter_q = f"name_contains={sanitized_name}&&tile_type=MAS"
        page_token = None
        while True:
            params = {"filter": filter_q}
            if page_token:
                params["page_token"] = page_token
            resp = self._get("/api/2.0/tiles", params=params)
            for t in resp.get("tiles", []):
                if t.get("name") == sanitized_name:
                    return MASIds(tile_id=t["tile_id"], name=sanitized_name)
            page_token = resp.get("next_page_token")
            if not page_token:
                break
        return None

    def list_all(self, page_size: int = 100) -> List[Dict[str, Any]]:
        """List all Supervisor Agents."""
        all_tiles = []
        filter_q = "tile_type=MAS"
        page_token = None

        while True:
            params = {"page_size": page_size, "filter": filter_q}
            if page_token:
                params["page_token"] = page_token

            resp = self._get("/api/2.0/tiles", params=params)
            for tile in resp.get("tiles", []):
                tile_type = tile.get("tile_type")
                if tile_type in ("MAS", "5"):
                    all_tiles.append(tile)

            page_token = resp.get("next_page_token")
            if not page_token:
                break

        return all_tiles

    def get_endpoint_status(self, tile_id: str) -> Optional[str]:
        """Get the endpoint status of a MAS."""
        mas = self.get(tile_id)
        if not mas:
            return None
        return mas.get("multi_agent_supervisor", {}).get("status", {}).get("endpoint_status")

    # ========================================================================
    # Examples Management
    # ========================================================================

    def create_example(self, tile_id: str, question: str, guidelines: Optional[List[str]] = None) -> Dict[str, Any]:
        """Create an example question for the MAS."""
        payload = {"tile_id": tile_id, "question": question}
        if guidelines:
            payload["guidelines"] = guidelines
        return self._post(f"/api/2.0/multi-agent-supervisors/{tile_id}/examples", payload)

    def list_examples(self, tile_id: str, page_size: int = 100) -> Dict[str, Any]:
        """List all examples for a MAS."""
        return self._get(f"/api/2.0/multi-agent-supervisors/{tile_id}/examples", params={"page_size": page_size})

    def delete_example(self, tile_id: str, example_id: str) -> None:
        """Delete an example from the MAS."""
        self._delete(f"/api/2.0/multi-agent-supervisors/{tile_id}/examples/{example_id}")

    def add_examples_batch(self, tile_id: str, questions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Add multiple example questions in parallel."""
        created_examples = []

        def create_example(q: Dict[str, Any]) -> Optional[Dict[str, Any]]:
            question_text = q.get("question", "")
            guidelines = q.get("guideline")
            if guidelines and isinstance(guidelines, str):
                guidelines = [guidelines]

            if not question_text:
                return None
            try:
                return self.create_example(tile_id, question_text, guidelines)
            except Exception as e:
                logger.error(f"Failed to add MAS example '{question_text[:50]}...': {e}")
                return None

        max_workers = min(2, len(questions))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_q = {executor.submit(create_example, q): q for q in questions}
            for future in as_completed(future_to_q):
                result = future.result()
                if result:
                    created_examples.append(result)

        return created_examples

    # ========================================================================
    # HTTP Helpers
    # ========================================================================

    def _handle_response_error(self, response: requests.Response, method: str, path: str) -> None:
        """Extract detailed error from response and raise."""
        if response.status_code >= 400:
            try:
                error_data = response.json()
                error_msg = error_data.get("message", error_data.get("error", str(error_data)))
                raise Exception(f"{method} {path} failed: {error_msg}")
            except ValueError:
                raise Exception(f"{method} {path} failed with status {response.status_code}: {response.text}")

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        headers = self.w.config.authenticate()
        url = f"{self.w.config.host}{path}"
        response = requests.get(url, headers=headers, params=params or {}, timeout=20)
        self._handle_response_error(response, "GET", path)
        return response.json()

    def _post(self, path: str, body: Dict[str, Any], timeout: int = 300) -> Dict[str, Any]:
        headers = self.w.config.authenticate()
        headers["Content-Type"] = "application/json"
        url = f"{self.w.config.host}{path}"
        response = requests.post(url, headers=headers, json=body, timeout=timeout)
        self._handle_response_error(response, "POST", path)
        return response.json()

    def _patch(self, path: str, body: Dict[str, Any]) -> Dict[str, Any]:
        headers = self.w.config.authenticate()
        headers["Content-Type"] = "application/json"
        url = f"{self.w.config.host}{path}"
        response = requests.patch(url, headers=headers, json=body, timeout=20)
        self._handle_response_error(response, "PATCH", path)
        return response.json()

    def _delete(self, path: str) -> Dict[str, Any]:
        headers = self.w.config.authenticate()
        url = f"{self.w.config.host}{path}"
        response = requests.delete(url, headers=headers, timeout=20)
        self._handle_response_error(response, "DELETE", path)
        return response.json()


# ============================================================================
# CLI Functions
# ============================================================================


def _get_manager() -> MASManager:
    """Get MASManager instance."""
    return MASManager()


def _build_agent_list(agents: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    """Build agent list for API from simplified config."""
    agent_list = []
    for agent in agents:
        agent_name = agent.get("name", "")
        agent_description = agent.get("description", "")

        agent_config = {
            "name": agent_name,
            "description": agent_description,
        }

        if agent.get("genie_space_id"):
            agent_config["agent_type"] = "genie"
            agent_config["genie_space"] = {"id": agent.get("genie_space_id")}
        elif agent.get("ka_tile_id"):
            ka_tile_id = agent.get("ka_tile_id")
            tile_id_prefix = ka_tile_id.split("-")[0]
            agent_config["agent_type"] = "serving_endpoint"
            agent_config["serving_endpoint"] = {"name": f"ka-{tile_id_prefix}-endpoint"}
        elif agent.get("uc_function_name"):
            uc_function_name = agent.get("uc_function_name")
            uc_parts = uc_function_name.split(".")
            agent_config["agent_type"] = "unity_catalog_function"
            agent_config["unity_catalog_function"] = {
                "uc_path": {
                    "catalog": uc_parts[0],
                    "schema": uc_parts[1],
                    "name": uc_parts[2],
                }
            }
        elif agent.get("connection_name"):
            agent_config["agent_type"] = "external_mcp_server"
            agent_config["external_mcp_server"] = {"connection_name": agent.get("connection_name")}
        else:
            agent_config["agent_type"] = "serving_endpoint"
            agent_config["serving_endpoint"] = {"name": agent.get("endpoint_name")}

        agent_list.append(agent_config)
    return agent_list


def create_mas(
    name: str,
    agents: List[Dict[str, str]],
    description: str = None,
    instructions: str = None,
) -> Dict[str, Any]:
    """Create a new Supervisor Agent."""
    manager = _get_manager()
    agent_list = _build_agent_list(agents)

    result = manager.create(
        name=name,
        agents=agent_list,
        description=description,
        instructions=instructions,
    )

    mas_data = result.get("multi_agent_supervisor", {})
    tile_data = mas_data.get("tile", {})
    status_data = mas_data.get("status", {})

    return {
        "tile_id": tile_data.get("tile_id", ""),
        "name": tile_data.get("name", name),
        "endpoint_status": status_data.get("endpoint_status", "UNKNOWN"),
        "agents_count": len(agents),
    }


def get_mas(tile_id: str) -> Dict[str, Any]:
    """Get a Supervisor Agent by tile ID."""
    manager = _get_manager()
    result = manager.get(tile_id)

    if not result:
        return {"error": f"Supervisor Agent {tile_id} not found"}

    mas_data = result.get("multi_agent_supervisor", {})
    tile_data = mas_data.get("tile", {})
    status_data = mas_data.get("status", {})

    return {
        "tile_id": tile_data.get("tile_id", tile_id),
        "name": tile_data.get("name", ""),
        "description": tile_data.get("description", ""),
        "endpoint_status": status_data.get("endpoint_status", "UNKNOWN"),
        "agents": mas_data.get("agents", []),
        # instructions live on the tile, not on the mas_data root
        "instructions": tile_data.get("instructions", ""),
    }


def find_mas(name: str) -> Dict[str, Any]:
    """Find a Supervisor Agent by name."""
    manager = _get_manager()
    result = manager.find_by_name(name)

    if result is None:
        return {"found": False, "name": name}

    full_details = manager.get(result.tile_id)
    if full_details:
        mas_data = full_details.get("multi_agent_supervisor", {})
        status_data = mas_data.get("status", {})
        return {
            "found": True,
            "tile_id": result.tile_id,
            "name": result.name,
            "endpoint_status": status_data.get("endpoint_status", "UNKNOWN"),
            "agents_count": len(mas_data.get("agents", [])),
        }

    return {
        "found": True,
        "tile_id": result.tile_id,
        "name": result.name,
    }


def update_mas(
    tile_id: str,
    name: str = None,
    agents: List[Dict[str, str]] = None,
    description: str = None,
    instructions: str = None,
) -> Dict[str, Any]:
    """Update an existing Supervisor Agent."""
    manager = _get_manager()

    existing = manager.get(tile_id)
    if not existing:
        return {"error": f"Supervisor Agent {tile_id} not found"}

    mas_data = existing.get("multi_agent_supervisor", {})
    tile_data = mas_data.get("tile", {})

    final_name = name or tile_data.get("name", "")
    final_description = description or tile_data.get("description", "")
    # instructions live on the tile in GET responses, not on the mas_data root
    final_instructions = instructions or tile_data.get("instructions", "")

    if agents:
        agent_list = _build_agent_list(agents)
    else:
        agent_list = mas_data.get("agents", [])

    result = manager.update(
        tile_id=tile_id,
        name=final_name,
        description=final_description,
        instructions=final_instructions,
        agents=agent_list,
    )

    updated_data = result.get("multi_agent_supervisor", {})
    updated_tile = updated_data.get("tile", {})
    updated_status = updated_data.get("status", {})

    return {
        "tile_id": updated_tile.get("tile_id", tile_id),
        "name": updated_tile.get("name", final_name),
        "endpoint_status": updated_status.get("endpoint_status", "UNKNOWN"),
    }


def delete_mas(tile_id: str) -> Dict[str, Any]:
    """Delete a Supervisor Agent."""
    manager = _get_manager()
    try:
        manager.delete(tile_id)
        return {"success": True, "tile_id": tile_id}
    except Exception as e:
        return {"success": False, "tile_id": tile_id, "error": str(e)}


def list_mas() -> List[Dict[str, Any]]:
    """List all Supervisor Agents."""
    manager = _get_manager()
    results = []

    tiles = manager.list_all()
    for tile in tiles:
        tile_id = tile.get("tile_id")
        details = manager.get(tile_id)
        if details:
            mas_data = details.get("multi_agent_supervisor", {})
            tile_data = mas_data.get("tile", {})
            status_data = mas_data.get("status", {})
            results.append({
                "tile_id": tile_id,
                "name": tile_data.get("name", ""),
                "endpoint_status": status_data.get("endpoint_status", "UNKNOWN"),
                "agents_count": len(mas_data.get("agents", [])),
            })

    return results


def add_examples(
    tile_id: str,
    examples: List[Dict[str, Any]],
    wait_for_online: bool = False,
    wait_timeout_seconds: int = 900,
    poll_interval_seconds: float = 30.0,
) -> Dict[str, Any]:
    """Add example questions to a Supervisor Agent.

    Examples can only be added once the MAS endpoint is ONLINE. Right after
    create_mas or a big update_mas the endpoint is NOT_READY and takes up to
    ~10 min to come ONLINE.

    If wait_for_online=True, this call BLOCKS synchronously until the endpoint
    reaches ONLINE (polling every `poll_interval_seconds`, up to
    `wait_timeout_seconds`). Default timeout 15 min covers the ~10 min
    provisioning with some headroom. The caller's process MUST stay alive for
    the whole duration — there is no background queue.

    If wait_for_online=False (default) and the endpoint is not ONLINE, returns
    an error immediately without adding anything. Retry later once ONLINE.
    """
    manager = _get_manager()

    status = get_mas(tile_id)
    if "error" in status:
        return status

    current = status.get("endpoint_status")

    if current != "ONLINE":
        if not wait_for_online:
            return {
                "error": f"MAS is not ONLINE (status: {current}). "
                "Retry once it's ONLINE, or pass wait_for_online=True "
                "(--wait on the CLI) to block until it comes up.",
                "tile_id": tile_id,
                "endpoint_status": current,
            }

        # Block-and-poll until ONLINE or timeout.
        deadline = time.monotonic() + wait_timeout_seconds
        while time.monotonic() < deadline:
            current = manager.get_endpoint_status(tile_id)
            if current == "ONLINE":
                break
            time.sleep(poll_interval_seconds)
        else:
            return {
                "error": f"Timed out after {wait_timeout_seconds}s waiting for MAS "
                f"to reach ONLINE (last status: {current}).",
                "tile_id": tile_id,
                "endpoint_status": current,
            }

    created = manager.add_examples_batch(tile_id, examples)
    return {
        "tile_id": tile_id,
        "added_count": len(created),
        "total_requested": len(examples),
        "endpoint_status": current,
    }


def list_examples(tile_id: str) -> Dict[str, Any]:
    """List all examples for a Supervisor Agent."""
    manager = _get_manager()
    result = manager.list_examples(tile_id)
    return {
        "tile_id": tile_id,
        "examples": result.get("examples", []),
        "count": len(result.get("examples", [])),
    }


def _print_json(data: Any) -> None:
    """Print data as formatted JSON."""
    print(json.dumps(data, indent=2))


def main():
    """CLI entry point."""
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]

    if command == "create_mas":
        if len(sys.argv) < 4:
            print("Usage: python mas_manager.py create_mas NAME '{\"agents\": [...], ...}'")
            sys.exit(1)
        name = sys.argv[2]
        config = json.loads(sys.argv[3])
        result = create_mas(
            name=name,
            agents=config.get("agents", []),
            description=config.get("description"),
            instructions=config.get("instructions"),
        )
        _print_json(result)

    elif command == "get_mas":
        if len(sys.argv) < 3:
            print("Usage: python mas_manager.py get_mas TILE_ID")
            sys.exit(1)
        result = get_mas(sys.argv[2])
        _print_json(result)

    elif command == "find_mas":
        if len(sys.argv) < 3:
            print("Usage: python mas_manager.py find_mas NAME")
            sys.exit(1)
        result = find_mas(sys.argv[2])
        _print_json(result)

    elif command == "update_mas":
        if len(sys.argv) < 4:
            print("Usage: python mas_manager.py update_mas TILE_ID '{\"name\": ..., \"agents\": [...], ...}'")
            sys.exit(1)
        tile_id = sys.argv[2]
        config = json.loads(sys.argv[3])
        result = update_mas(
            tile_id=tile_id,
            name=config.get("name"),
            agents=config.get("agents"),
            description=config.get("description"),
            instructions=config.get("instructions"),
        )
        _print_json(result)

    elif command == "delete_mas":
        if len(sys.argv) < 3:
            print("Usage: python mas_manager.py delete_mas TILE_ID")
            sys.exit(1)
        result = delete_mas(sys.argv[2])
        _print_json(result)

    elif command == "list_mas":
        result = list_mas()
        _print_json(result)

    elif command == "add_examples":
        if len(sys.argv) < 4:
            print("Usage: python mas_manager.py add_examples TILE_ID '[{\"question\": \"...\", \"guideline\": \"...\"}]' [--wait]")
            sys.exit(1)
        tile_id = sys.argv[2]
        examples = json.loads(sys.argv[3])
        wait = "--wait" in sys.argv[4:]
        result = add_examples(tile_id, examples, wait_for_online=wait)
        _print_json(result)

    elif command == "list_examples":
        if len(sys.argv) < 3:
            print("Usage: python mas_manager.py list_examples TILE_ID")
            sys.exit(1)
        result = list_examples(sys.argv[2])
        _print_json(result)

    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
