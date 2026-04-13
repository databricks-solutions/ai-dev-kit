#!/usr/bin/env python3
"""
Supervisor Agent (MAS) Manager - CLI interface for MAS operations.

Usage:
    python mas_manager.py create_mas "Name" '{"agents": [...], "description": "...", "instructions": "..."}'
    python mas_manager.py get_mas TILE_ID
    python mas_manager.py find_mas "Name"
    python mas_manager.py update_mas TILE_ID '{"name": ..., "agents": [...], ...}'
    python mas_manager.py delete_mas TILE_ID
    python mas_manager.py list_mas
    python mas_manager.py add_examples TILE_ID '[{"question": "...", "guideline": "..."}]'
    python mas_manager.py add_examples_queued TILE_ID '[{"question": "...", "guideline": "..."}]'
    python mas_manager.py list_examples TILE_ID

Requires: databricks-tools-core package
"""

import json
import sys
from typing import Any, Dict, List, Optional

from databricks_tools_core.agent_bricks import (
    AgentBricksManager,
    EndpointStatus,
    get_tile_example_queue,
)


def _get_manager() -> AgentBricksManager:
    """Get AgentBricksManager instance."""
    return AgentBricksManager()


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
    """Create a new Supervisor Agent.

    Args:
        name: Display name for the MAS
        agents: List of agent configs, each with:
            - name: Agent identifier
            - description: What this agent handles (critical for routing)
            - ONE OF: endpoint_name, genie_space_id, ka_tile_id, uc_function_name, connection_name
        description: What this MAS does
        instructions: Routing rules for the supervisor

    Returns:
        Dict with tile_id, name, endpoint_status
    """
    manager = _get_manager()
    agent_list = _build_agent_list(agents)

    result = manager.mas_create(
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
    """Get a Supervisor Agent by tile ID.

    Args:
        tile_id: The MAS tile ID

    Returns:
        Dict with tile_id, name, description, endpoint_status, agents, instructions
    """
    manager = _get_manager()
    result = manager.mas_get(tile_id)

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
        "instructions": mas_data.get("instructions", ""),
    }


def find_mas(name: str) -> Dict[str, Any]:
    """Find a Supervisor Agent by name.

    Args:
        name: The display name to search for

    Returns:
        Dict with found, tile_id, name, endpoint_status if found
    """
    manager = _get_manager()
    result = manager.mas_find_by_name(name)

    if result is None:
        return {"found": False, "name": name}

    full_details = manager.mas_get(result.tile_id)
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
    """Update an existing Supervisor Agent.

    Args:
        tile_id: The MAS tile ID to update
        name: New display name (optional)
        agents: New agent list (optional)
        description: New description (optional)
        instructions: New routing instructions (optional)

    Returns:
        Dict with tile_id, name, endpoint_status
    """
    manager = _get_manager()

    # Get existing to merge
    existing = manager.mas_get(tile_id)
    if not existing:
        return {"error": f"Supervisor Agent {tile_id} not found"}

    mas_data = existing.get("multi_agent_supervisor", {})
    tile_data = mas_data.get("tile", {})

    # Use existing values if not provided
    final_name = name or tile_data.get("name", "")
    final_description = description or tile_data.get("description", "")
    final_instructions = instructions or mas_data.get("instructions", "")

    if agents:
        agent_list = _build_agent_list(agents)
    else:
        agent_list = mas_data.get("agents", [])

    result = manager.mas_update(
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
    """Delete a Supervisor Agent.

    Args:
        tile_id: The MAS tile ID to delete

    Returns:
        Dict with success status
    """
    manager = _get_manager()
    try:
        manager.delete(tile_id)
        return {"success": True, "tile_id": tile_id}
    except Exception as e:
        return {"success": False, "tile_id": tile_id, "error": str(e)}


def list_mas() -> List[Dict[str, Any]]:
    """List all Supervisor Agents.

    Returns:
        List of MAS summaries with tile_id, name, endpoint_status
    """
    manager = _get_manager()
    results = []

    # List all tiles and filter to MAS type
    tiles = manager.list_tiles()
    for tile in tiles:
        if tile.tile_type == "MULTI_AGENT_SUPERVISOR":
            details = manager.mas_get(tile.tile_id)
            if details:
                mas_data = details.get("multi_agent_supervisor", {})
                tile_data = mas_data.get("tile", {})
                status_data = mas_data.get("status", {})
                results.append({
                    "tile_id": tile.tile_id,
                    "name": tile_data.get("name", ""),
                    "endpoint_status": status_data.get("endpoint_status", "UNKNOWN"),
                    "agents_count": len(mas_data.get("agents", [])),
                })

    return results


def add_examples(
    tile_id: str,
    examples: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Add example questions to a Supervisor Agent.

    Args:
        tile_id: The MAS tile ID
        examples: List of example dicts with:
            - question: The example question
            - guideline: Optional routing guideline (e.g., "Should route to billing_agent")

    Returns:
        Dict with added_count and any errors
    """
    manager = _get_manager()

    # Check if MAS is online
    status = get_mas(tile_id)
    if "error" in status:
        return status

    if status.get("endpoint_status") != "ONLINE":
        return {
            "error": f"MAS is not ONLINE (status: {status.get('endpoint_status')}). "
            "Use add_examples_queued to queue examples for when it's ready.",
            "tile_id": tile_id,
        }

    # Add examples directly
    created = manager.mas_add_examples_batch(tile_id, examples)
    return {
        "tile_id": tile_id,
        "added_count": len(created),
        "total_requested": len(examples),
    }


def add_examples_queued(
    tile_id: str,
    examples: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Queue example questions to be added when MAS becomes ONLINE.

    If the MAS is already ONLINE, examples are added immediately.
    If not, they're queued and added automatically when the endpoint is ready.

    Args:
        tile_id: The MAS tile ID
        examples: List of example dicts with:
            - question: The example question
            - guideline: Optional routing guideline

    Returns:
        Dict with status (queued or added) and count
    """
    manager = _get_manager()

    # Check current status
    status = get_mas(tile_id)
    if "error" in status:
        return status

    if status.get("endpoint_status") == "ONLINE":
        # Add immediately
        created = manager.mas_add_examples_batch(tile_id, examples)
        return {
            "tile_id": tile_id,
            "status": "added",
            "added_count": len(created),
            "total_requested": len(examples),
        }
    else:
        # Queue for later
        queue = get_tile_example_queue()
        queue.start()
        queue.enqueue(tile_id, manager, examples, tile_type="mas")
        return {
            "tile_id": tile_id,
            "status": "queued",
            "queued_count": len(examples),
            "endpoint_status": status.get("endpoint_status"),
            "message": "Examples will be added automatically when endpoint becomes ONLINE",
        }


def list_examples(tile_id: str) -> Dict[str, Any]:
    """List all examples for a Supervisor Agent.

    Args:
        tile_id: The MAS tile ID

    Returns:
        Dict with examples list
    """
    manager = _get_manager()
    result = manager.mas_list_examples(tile_id)
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
            print("Usage: python mas_manager.py add_examples TILE_ID '[{\"question\": \"...\", \"guideline\": \"...\"}]'")
            sys.exit(1)
        tile_id = sys.argv[2]
        examples = json.loads(sys.argv[3])
        result = add_examples(tile_id, examples)
        _print_json(result)

    elif command == "add_examples_queued":
        if len(sys.argv) < 4:
            print("Usage: python mas_manager.py add_examples_queued TILE_ID '[{\"question\": \"...\", \"guideline\": \"...\"}]'")
            sys.exit(1)
        tile_id = sys.argv[2]
        examples = json.loads(sys.argv[3])
        result = add_examples_queued(tile_id, examples)
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
