"""Agent Bricks tools - Manage Knowledge Assistants (KA) and Supervisor Agents (MAS).

For Genie Space tools, see genie.py
"""

from typing import Any, Dict, List, Optional

from databricks_tools_core.agent_bricks import (
    AgentBricksManager,
    EndpointStatus,
    get_tile_example_queue,
)
from databricks_tools_core.identity import with_description_footer

from ..manifest import register_deleter
from ..server import mcp

# Singleton manager instance
_manager: Optional[AgentBricksManager] = None


def _get_manager() -> AgentBricksManager:
    """Get or create the singleton AgentBricksManager instance."""
    global _manager
    if _manager is None:
        _manager = AgentBricksManager()
    return _manager


def _delete_ka_resource(resource_id: str) -> None:
    _get_manager().delete(resource_id)


def _delete_mas_resource(resource_id: str) -> None:
    _get_manager().delete(resource_id)


register_deleter("knowledge_assistant", _delete_ka_resource)
register_deleter("multi_agent_supervisor", _delete_mas_resource)


# ============================================================================
# Internal action handlers
# ============================================================================


def _ka_create_or_update(
    name: str,
    volume_path: str,
    description: str = None,
    instructions: str = None,
    tile_id: str = None,
    add_examples_from_volume: bool = True,
) -> Dict[str, Any]:
    """Create or update a Knowledge Assistant."""
    if not name:
        return {"error": "Missing required parameter 'name' for create_or_update action"}
    if not volume_path:
        return {"error": "Missing required parameter 'volume_path' for create_or_update action"}

    description = with_description_footer(description)
    manager = _get_manager()

    # Build knowledge source from volume path
    knowledge_sources = [
        {
            "files_source": {
                "name": f"source_{name.replace(' ', '_').lower()}",
                "type": "files",
                "files": {"path": volume_path},
            }
        }
    ]

    # Create or update the KA
    result = manager.ka_create_or_update(
        name=name,
        knowledge_sources=knowledge_sources,
        description=description,
        instructions=instructions,
        tile_id=tile_id,
    )

    # Extract tile info
    ka_data = result.get("knowledge_assistant", {})
    tile_data = ka_data.get("tile", {})
    status_data = ka_data.get("status", {})

    response_tile_id = tile_data.get("tile_id", "")
    endpoint_status = status_data.get("endpoint_status", "UNKNOWN")

    response = {
        "tile_id": response_tile_id,
        "name": tile_data.get("name", name),
        "operation": result.get("operation", "created"),
        "endpoint_status": endpoint_status,
        "examples_queued": 0,
    }

    # Scan volume for examples if requested
    if add_examples_from_volume and response_tile_id:
        examples = manager.scan_volume_for_examples(volume_path)
        if examples:
            # If endpoint is ONLINE, add examples directly
            if endpoint_status == EndpointStatus.ONLINE.value:
                created = manager.ka_add_examples_batch(response_tile_id, examples)
                response["examples_added"] = len(created)
            else:
                # Queue examples for when endpoint becomes ready
                queue = get_tile_example_queue()
                queue.enqueue(response_tile_id, manager, examples, tile_type="KA")
                response["examples_queued"] = len(examples)

    # Track resource on successful create/update
    try:
        if response_tile_id:
            from ..manifest import track_resource

            track_resource(
                resource_type="knowledge_assistant",
                name=response.get("name", name),
                resource_id=response_tile_id,
            )
    except Exception:
        pass  # best-effort tracking

    return response


def _ka_get(tile_id: str) -> Dict[str, Any]:
    """Get a Knowledge Assistant by tile ID."""
    if not tile_id:
        return {"error": "Missing required parameter 'tile_id' for get action"}

    manager = _get_manager()
    result = manager.ka_get(tile_id)

    if not result:
        return {"error": f"Knowledge Assistant {tile_id} not found"}

    ka_data = result.get("knowledge_assistant", {})
    tile_data = ka_data.get("tile", {})
    status_data = ka_data.get("status", {})

    # Get examples count
    examples_response = manager.ka_list_examples(tile_id)
    examples_count = len(examples_response.get("examples", []))

    return {
        "tile_id": tile_data.get("tile_id", tile_id),
        "name": tile_data.get("name", ""),
        "description": tile_data.get("description", ""),
        "endpoint_status": status_data.get("endpoint_status", "UNKNOWN"),
        "knowledge_sources": ka_data.get("knowledge_sources", []),
        "examples_count": examples_count,
        "instructions": ka_data.get("instructions", ""),
    }


def _ka_find_by_name(name: str) -> Dict[str, Any]:
    """Find a Knowledge Assistant by name."""
    if not name:
        return {"error": "Missing required parameter 'name' for find_by_name action"}

    manager = _get_manager()
    result = manager.find_by_name(name)

    if result is None:
        return {"found": False, "name": name}

    # Fetch full details to get endpoint status
    full_details = manager.ka_get(result.tile_id)
    endpoint_status = "UNKNOWN"
    if full_details:
        endpoint_status = (
            full_details.get("knowledge_assistant", {}).get("status", {}).get("endpoint_status", "UNKNOWN")
        )

    # Endpoint name uses only the first segment of the tile_id (before the first hyphen)
    tile_id_prefix = result.tile_id.split("-")[0]
    return {
        "found": True,
        "tile_id": result.tile_id,
        "name": result.name,
        "endpoint_name": f"ka-{tile_id_prefix}-endpoint",
        "endpoint_status": endpoint_status,
    }


def _ka_delete(tile_id: str) -> Dict[str, Any]:
    """Delete a Knowledge Assistant."""
    if not tile_id:
        return {"error": "Missing required parameter 'tile_id' for delete action"}

    manager = _get_manager()
    try:
        manager.delete(tile_id)
        try:
            from ..manifest import remove_resource

            remove_resource(resource_type="knowledge_assistant", resource_id=tile_id)
        except Exception:
            pass
        return {"success": True, "tile_id": tile_id}
    except Exception as e:
        return {"success": False, "tile_id": tile_id, "error": str(e)}


def _mas_create_or_update(
    name: str,
    agents: List[Dict[str, str]],
    description: str = None,
    instructions: str = None,
    tile_id: str = None,
    examples: List[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Create or update a Supervisor Agent."""
    if not name:
        return {"error": "Missing required parameter 'name' for create_or_update action"}
    if not agents:
        return {"error": "Missing required parameter 'agents' for create_or_update action"}

    description = with_description_footer(description)
    manager = _get_manager()

    # Validate and build agent list for API
    agent_list = []
    for i, agent in enumerate(agents):
        agent_name = agent.get("name", "")
        if not agent_name:
            return {"error": f"Agent at index {i} is missing required 'name' field"}

        agent_description = agent.get("description", "")
        if not agent_description:
            return {"error": f"Agent '{agent_name}' is missing required 'description' field"}

        has_endpoint = bool(agent.get("endpoint_name"))
        has_genie = bool(agent.get("genie_space_id"))
        has_ka = bool(agent.get("ka_tile_id"))
        has_uc_function = bool(agent.get("uc_function_name"))
        has_connection = bool(agent.get("connection_name"))

        # Count how many agent types are specified
        agent_type_count = sum([has_endpoint, has_genie, has_ka, has_uc_function, has_connection])
        if agent_type_count > 1:
            return {
                "error": (
                    f"Agent '{agent_name}' has multiple agent types. "
                    "Provide only one of: 'endpoint_name', 'genie_space_id', "
                    "'ka_tile_id', 'uc_function_name', or 'connection_name'."
                )
            }
        if agent_type_count == 0:
            return {
                "error": (
                    f"Agent '{agent_name}' must have one of: 'endpoint_name', "
                    "'genie_space_id', 'ka_tile_id', 'uc_function_name', or 'connection_name'"
                )
            }

        agent_config = {
            "name": agent_name,
            "description": agent_description,
        }

        if has_genie:
            agent_config["agent_type"] = "genie"
            agent_config["genie_space"] = {"id": agent.get("genie_space_id")}
        elif has_ka:
            # KA tiles are referenced via their serving endpoint
            # Endpoint name uses the first segment of the tile_id
            ka_tile_id = agent.get("ka_tile_id")
            tile_id_prefix = ka_tile_id.split("-")[0]
            agent_config["agent_type"] = "serving_endpoint"
            agent_config["serving_endpoint"] = {"name": f"ka-{tile_id_prefix}-endpoint"}
        elif has_uc_function:
            uc_function_name = agent.get("uc_function_name")
            uc_parts = uc_function_name.split(".")
            if len(uc_parts) != 3:
                return {
                    "error": (
                        f"Agent '{agent_name}': uc_function_name must be in format "
                        f"'catalog.schema.function_name', got '{uc_function_name}'"
                    )
                }
            agent_config["agent_type"] = "unity_catalog_function"
            agent_config["unity_catalog_function"] = {
                "uc_path": {
                    "catalog": uc_parts[0],
                    "schema": uc_parts[1],
                    "name": uc_parts[2],
                }
            }
        elif has_connection:
            agent_config["agent_type"] = "external_mcp_server"
            agent_config["external_mcp_server"] = {"connection_name": agent.get("connection_name")}
        else:
            agent_config["agent_type"] = "serving_endpoint"
            agent_config["serving_endpoint"] = {"name": agent.get("endpoint_name")}

        agent_list.append(agent_config)

    operation = "created"
    response_tile_id = tile_id

    if tile_id:
        # Check if exists
        existing = manager.mas_get(tile_id)
        if existing:
            operation = "updated"
            result = manager.mas_update(
                tile_id=tile_id,
                name=name,
                description=description,
                instructions=instructions,
                agents=agent_list,
            )
        else:
            return {"error": f"MAS {tile_id} not found"}
    else:
        # Check if exists by name
        existing = manager.mas_find_by_name(name)
        if existing:
            operation = "updated"
            response_tile_id = existing.tile_id
            result = manager.mas_update(
                tile_id=existing.tile_id,
                name=name,
                description=description,
                instructions=instructions,
                agents=agent_list,
            )
        else:
            # Create new
            result = manager.mas_create(
                name=name,
                agents=agent_list,
                description=description,
                instructions=instructions,
            )
            response_tile_id = result.get("multi_agent_supervisor", {}).get("tile", {}).get("tile_id", "")

    # Extract status
    mas_data = result.get("multi_agent_supervisor", {})
    tile_data = mas_data.get("tile", {})
    status_data = mas_data.get("status", {})
    endpoint_status = status_data.get("endpoint_status", "UNKNOWN")

    response = {
        "tile_id": response_tile_id or tile_data.get("tile_id", ""),
        "name": tile_data.get("name", name),
        "operation": operation,
        "endpoint_status": endpoint_status,
        "agents_count": len(agents),
    }

    # Add examples if provided
    if examples and response["tile_id"]:
        if endpoint_status == EndpointStatus.ONLINE.value:
            created = manager.mas_add_examples_batch(response["tile_id"], examples)
            response["examples_added"] = len(created)
        else:
            # Queue examples for when endpoint becomes ready
            queue = get_tile_example_queue()
            queue.enqueue(response["tile_id"], manager, examples, tile_type="MAS")
            response["examples_queued"] = len(examples)

    # Track resource on successful create/update
    try:
        mas_tile_id = response.get("tile_id")
        if mas_tile_id:
            from ..manifest import track_resource

            track_resource(
                resource_type="multi_agent_supervisor",
                name=response.get("name", name),
                resource_id=mas_tile_id,
            )
    except Exception:
        pass  # best-effort tracking

    return response


def _mas_get(tile_id: str) -> Dict[str, Any]:
    """Get a Supervisor Agent by tile ID."""
    if not tile_id:
        return {"error": "Missing required parameter 'tile_id' for get action"}

    manager = _get_manager()
    result = manager.mas_get(tile_id)

    if not result:
        return {"error": f"Supervisor Agent {tile_id} not found"}

    mas_data = result.get("multi_agent_supervisor", {})
    tile_data = mas_data.get("tile", {})
    status_data = mas_data.get("status", {})

    # Get examples count
    examples_response = manager.mas_list_examples(tile_id)
    examples_count = len(examples_response.get("examples", []))

    return {
        "tile_id": tile_data.get("tile_id", tile_id),
        "name": tile_data.get("name", ""),
        "description": tile_data.get("description", ""),
        "endpoint_status": status_data.get("endpoint_status", "UNKNOWN"),
        "agents": mas_data.get("agents", []),
        "examples_count": examples_count,
        "instructions": mas_data.get("instructions", ""),
    }


def _mas_find_by_name(name: str) -> Dict[str, Any]:
    """Find a Supervisor Agent by name."""
    if not name:
        return {"error": "Missing required parameter 'name' for find_by_name action"}

    manager = _get_manager()
    result = manager.mas_find_by_name(name)

    if result is None:
        return {"found": False, "name": name}

    # Fetch full details to get endpoint status and agents
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
        "endpoint_status": "UNKNOWN",
        "agents_count": 0,
    }


def _mas_delete(tile_id: str) -> Dict[str, Any]:
    """Delete a Supervisor Agent."""
    if not tile_id:
        return {"error": "Missing required parameter 'tile_id' for delete action"}

    manager = _get_manager()
    try:
        manager.delete(tile_id)
        try:
            from ..manifest import remove_resource

            remove_resource(resource_type="multi_agent_supervisor", resource_id=tile_id)
        except Exception:
            pass
        return {"success": True, "tile_id": tile_id}
    except Exception as e:
        return {"success": False, "tile_id": tile_id, "error": str(e)}


# ============================================================================
# Consolidated MCP Tools
# ============================================================================


@mcp.tool
def manage_ka(
    action: str,
    name: str = None,
    volume_path: str = None,
    description: str = None,
    instructions: str = None,
    tile_id: str = None,
    add_examples_from_volume: bool = True,
) -> Dict[str, Any]:
    """
    Create or update a Knowledge Assistant (KA) with document knowledge sources.

    A Knowledge Assistant is a document-based Q&A system that uses RAG to answer
    questions from indexed documents (PDFs, text files, etc.).

    Actions:
    - create_or_update: Create or update a KA (requires name, volume_path)
    - get: Get KA details by tile_id
    - find_by_name: Find a KA by exact name
    - delete: Delete a KA by tile_id

    Args:
        action: "create_or_update", "get", "find_by_name", or "delete"
        name: Name for the KA (for create_or_update, find_by_name)
        volume_path: Path to the volume folder containing documents
            (e.g., "/Volumes/catalog/schema/volume/folder") (for create_or_update)
        description: Optional description of what the KA does (for create_or_update)
        instructions: Optional instructions for how the KA should answer (for create_or_update)
        tile_id: The KA tile ID (for get, delete, or update via create_or_update)
        add_examples_from_volume: If True, scan the volume for JSON files
            containing question/guideline pairs and add them as examples (for create_or_update)

    Returns:
        Dict with operation result. Varies by action:
        - create_or_update: tile_id, name, operation, endpoint_status, examples_queued
        - get: tile_id, name, description, endpoint_status, knowledge_sources, examples_count
        - find_by_name: found, tile_id, name, endpoint_name, endpoint_status
        - delete: success, tile_id

    Example:
        >>> manage_ka(
        ...     action="create_or_update",
        ...     name="HR Policy Assistant",
        ...     volume_path="/Volumes/my_catalog/my_schema/raw_data/hr_docs",
        ...     description="Answers questions about HR policies",
        ...     instructions="Be helpful and cite specific policies when answering"
        ... )
        {
            "tile_id": "01abc...",
            "name": "HR_Policy_Assistant",
            "operation": "created",
            "endpoint_status": "PROVISIONING",
            "examples_queued": 5
        }
    """
    action = action.lower()

    if action == "create_or_update":
        return _ka_create_or_update(
            name=name,
            volume_path=volume_path,
            description=description,
            instructions=instructions,
            tile_id=tile_id,
            add_examples_from_volume=add_examples_from_volume,
        )
    elif action == "get":
        return _ka_get(tile_id=tile_id)
    elif action == "find_by_name":
        return _ka_find_by_name(name=name)
    elif action == "delete":
        return _ka_delete(tile_id=tile_id)
    else:
        return {"error": f"Invalid action '{action}'. Must be one of: create_or_update, get, find_by_name, delete"}


@mcp.tool
def manage_mas(
    action: str,
    name: str = None,
    agents: List[Dict[str, str]] = None,
    description: str = None,
    instructions: str = None,
    tile_id: str = None,
    examples: List[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Create or update a Supervisor Agent (formerly Multi-Agent Supervisor, MAS).

    A Supervisor Agent orchestrates multiple agents, routing user queries to the appropriate
    specialized agent based on the query content. Supports model serving endpoints,
    Genie spaces, Knowledge Assistants, UC functions, and external MCP servers as agents.

    Actions:
    - create_or_update: Create or update a Supervisor Agent (requires name, agents)
    - get: Get Supervisor Agent details by tile_id
    - find_by_name: Find a Supervisor Agent by exact name
    - delete: Delete a Supervisor Agent by tile_id

    Args:
        action: "create_or_update", "get", "find_by_name", or "delete"
        name: Name for the Supervisor Agent (for create_or_update, find_by_name)
        agents: List of agent configurations (for create_or_update). Each agent requires:
            - name: Agent identifier (used internally for routing)
            - description: What this agent handles (critical for routing decisions)
            - endpoint_name: Model serving endpoint name (for custom agents)
            - genie_space_id: Genie space ID (for SQL-based data agents)
            - ka_tile_id: Knowledge Assistant tile ID (for document Q&A agents)
            - uc_function_name: Unity Catalog function name in format 'catalog.schema.function_name'
            - connection_name: Unity Catalog connection name (for external MCP servers)
            Note: Provide exactly one of: endpoint_name, genie_space_id,
                ka_tile_id, uc_function_name, or connection_name.
        description: Optional description of what the MAS does (for create_or_update)
        instructions: Optional routing instructions for the supervisor (for create_or_update)
        tile_id: The Supervisor Agent tile ID (for get, delete, or update via create_or_update)
        examples: Optional list of example questions (for create_or_update), each with:
            - question: The example question
            - guideline: Expected routing behavior or answer guidelines

    Returns:
        Dict with operation result. Varies by action:
        - create_or_update: tile_id, name, operation, endpoint_status, agents_count
        - get: tile_id, name, description, endpoint_status, agents, examples_count
        - find_by_name: found, tile_id, name, endpoint_status, agents_count
        - delete: success, tile_id

    Example:
        >>> manage_mas(
        ...     action="create_or_update",
        ...     name="Customer Support MAS",
        ...     agents=[
        ...         {
        ...             "name": "policy_agent",
        ...             "ka_tile_id": "f32c5f73-466b-...",
        ...             "description": "Answers questions about company policies and procedures"
        ...         },
        ...         {
        ...             "name": "analytics_agent",
        ...             "genie_space_id": "01abc123...",
        ...             "description": "Answers data questions about usage and metrics"
        ...         }
        ...     ],
        ...     description="Routes customer queries to specialized agents",
        ...     instructions="Route policy questions to policy_agent, data questions to analytics_agent."
        ... )
        {
            "tile_id": "01xyz...",
            "name": "Customer_Support_MAS",
            "operation": "created",
            "endpoint_status": "PROVISIONING",
            "agents_count": 2
        }
    """
    action = action.lower()

    if action == "create_or_update":
        return _mas_create_or_update(
            name=name,
            agents=agents,
            description=description,
            instructions=instructions,
            tile_id=tile_id,
            examples=examples,
        )
    elif action == "get":
        return _mas_get(tile_id=tile_id)
    elif action == "find_by_name":
        return _mas_find_by_name(name=name)
    elif action == "delete":
        return _mas_delete(tile_id=tile_id)
    else:
        return {"error": f"Invalid action '{action}'. Must be one of: create_or_update, get, find_by_name, delete"}
