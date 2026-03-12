"""Genie tools - Create, manage, and query Databricks Genie Spaces."""

from datetime import timedelta
from typing import Any, Dict, List, Optional

from databricks_tools_core.agent_bricks import AgentBricksManager
from databricks_tools_core.auth import get_workspace_client
from databricks_tools_core.identity import with_description_footer

from ..manifest import register_deleter
from ..server import mcp

# Singleton manager instance for space management operations
_manager: Optional[AgentBricksManager] = None


def _get_manager() -> AgentBricksManager:
    """Get or create the singleton AgentBricksManager instance."""
    global _manager
    if _manager is None:
        _manager = AgentBricksManager()
    return _manager


def _delete_genie_resource(resource_id: str) -> None:
    _get_manager().genie_delete(resource_id)


register_deleter("genie_space", _delete_genie_resource)


# ============================================================================
# Genie Space Management Tools
# ============================================================================


@mcp.tool
def create_or_update_genie(
    display_name: str,
    table_identifiers: List[str],
    warehouse_id: Optional[str] = None,
    description: Optional[str] = None,
    sample_questions: Optional[List[str]] = None,
    space_id: Optional[str] = None,
    serialized_space: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create or update a Genie Space for SQL-based data exploration.

    A Genie Space allows users to ask natural language questions about data
    and get SQL-generated answers. It connects to tables in Unity Catalog.

    Args:
        display_name: Display name for the Genie space
        table_identifiers: List of tables to include
            (e.g., ["catalog.schema.customers", "catalog.schema.orders"])
        warehouse_id: SQL warehouse ID. If not provided, auto-detects the best
            available warehouse (prefers running, smaller warehouses)
        description: Optional description of what the Genie space does
        sample_questions: Optional list of sample questions to help users
        space_id: Optional existing space_id to update instead of create
        serialized_space: Optional JSON string containing full space configuration
            (settings, instructions). Use this to import/clone a Genie space
            exported via get_genie with include_serialized_space=True.

    Returns:
        Dictionary with:
        - space_id: The Genie space ID
        - display_name: The display name
        - operation: 'created' or 'updated'
        - warehouse_id: The warehouse being used
        - table_count: Number of tables configured

    Example:
        >>> create_or_update_genie(
        ...     display_name="Sales Analytics",
        ...     table_identifiers=["catalog.sales.orders", "catalog.sales.customers"],
        ...     description="Explore sales data with natural language",
        ...     sample_questions=["What were total sales last month?"]
        ... )
        {"space_id": "abc123...", "display_name": "Sales Analytics", "operation": "created", ...}

        Clone a space:
        >>> source = get_genie(space_id="abc123", include_serialized_space=True)
        >>> create_or_update_genie(
        ...     display_name="Sales Analytics (Copy)",
        ...     table_identifiers=source["table_identifiers"],
        ...     serialized_space=source["serialized_space"]
        ... )
    """
    try:
        description = with_description_footer(description)
        manager = _get_manager()

        # Auto-detect warehouse if not provided
        if warehouse_id is None:
            warehouse_id = manager.get_best_warehouse_id()
            if warehouse_id is None:
                return {"error": "No SQL warehouses available. Please provide a warehouse_id or create a warehouse."}

        operation = "created"

        if space_id:
            existing = manager.genie_get(space_id)
            if existing:
                operation = "updated"
                manager.genie_update(
                    space_id=space_id,
                    display_name=display_name,
                    description=description,
                    warehouse_id=warehouse_id,
                    table_identifiers=table_identifiers,
                    sample_questions=sample_questions,
                    serialized_space=serialized_space,
                )
            else:
                return {"error": f"Genie space {space_id} not found"}
        else:
            existing = manager.genie_find_by_name(display_name)
            if existing:
                operation = "updated"
                manager.genie_update(
                    space_id=existing.space_id,
                    display_name=display_name,
                    description=description,
                    warehouse_id=warehouse_id,
                    table_identifiers=table_identifiers,
                    sample_questions=sample_questions,
                    serialized_space=serialized_space,
                )
                space_id = existing.space_id
            else:
                result = manager.genie_create(
                    display_name=display_name,
                    warehouse_id=warehouse_id,
                    table_identifiers=table_identifiers,
                    description=description,
                    serialized_space=serialized_space,
                )
                space_id = result.get("space_id", "")

                if sample_questions and space_id:
                    manager.genie_add_sample_questions_batch(space_id, sample_questions)

        response = {
            "space_id": space_id,
            "display_name": display_name,
            "operation": operation,
            "warehouse_id": warehouse_id,
            "table_count": len(table_identifiers),
        }

        try:
            if space_id:
                from ..manifest import track_resource

                track_resource(
                    resource_type="genie_space",
                    name=display_name,
                    resource_id=space_id,
                )
        except Exception:
            pass

        return response

    except Exception as e:
        return {"error": f"Failed to create/update Genie space '{display_name}': {e}"}


@mcp.tool
def get_genie(
    space_id: Optional[str] = None,
    include_serialized_space: bool = False,
) -> Dict[str, Any]:
    """
    Get details of a Genie Space, or list all spaces.

    Pass a space_id to get one space's details (including tables, sample
    questions). Omit space_id to list all accessible spaces.

    Args:
        space_id: The Genie space ID. If omitted, lists all spaces.
        include_serialized_space: If True, includes the serialized_space field
            containing the full space configuration (settings, instructions).
            Useful for exporting a space to clone or import elsewhere.

    Returns:
        Single space dict (if space_id provided) or {"spaces": [...]}.

    Example:
        >>> get_genie("abc123...")
        {"space_id": "abc123...", "display_name": "Sales Analytics", ...}

        >>> get_genie()
        {"spaces": [{"space_id": "abc123...", "title": "Sales Analytics", ...}, ...]}

        Export for cloning:
        >>> get_genie("abc123...", include_serialized_space=True)
        {"space_id": "abc123...", ..., "serialized_space": "{...}"}
    """
    if space_id:
        try:
            manager = _get_manager()
            result = manager.genie_get(space_id, include_serialized_space=include_serialized_space)

            if not result:
                return {"error": f"Genie space {space_id} not found"}

            questions_response = manager.genie_list_questions(space_id, question_type="SAMPLE_QUESTION")
            sample_questions = [q.get("question_text", "") for q in questions_response.get("curated_questions", [])]

            response = {
                "space_id": result.get("space_id", space_id),
                "display_name": result.get("display_name", ""),
                "description": result.get("description", ""),
                "warehouse_id": result.get("warehouse_id", ""),
                "table_identifiers": result.get("table_identifiers", []),
                "sample_questions": sample_questions,
            }

            if include_serialized_space and result.get("serialized_space"):
                response["serialized_space"] = result["serialized_space"]

            return response
        except Exception as e:
            return {"error": f"Failed to get Genie space {space_id}: {e}"}

    # List all spaces
    try:
        w = get_workspace_client()
        response = w.genie.list_spaces()
        spaces = []
        if response.spaces:
            for space in response.spaces:
                spaces.append(
                    {
                        "space_id": space.space_id,
                        "title": space.title or "",
                        "description": space.description or "",
                    }
                )
        return {"spaces": spaces}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool
def delete_genie(space_id: str) -> Dict[str, Any]:
    """
    Delete a Genie Space.

    Args:
        space_id: The Genie space ID to delete

    Returns:
        Dictionary with:
        - success: True if deleted
        - space_id: The deleted space ID

    Example:
        >>> delete_genie("abc123...")
        {"success": True, "space_id": "abc123..."}
    """
    manager = _get_manager()
    try:
        manager.genie_delete(space_id)
        try:
            from ..manifest import remove_resource

            remove_resource(resource_type="genie_space", resource_id=space_id)
        except Exception:
            pass
        return {"success": True, "space_id": space_id}
    except Exception as e:
        return {"success": False, "space_id": space_id, "error": str(e)}


@mcp.tool
def clone_genie(
    source_space_id: str,
    new_display_name: str,
    warehouse_id: Optional[str] = None,
    description: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Clone a Genie Space by exporting its full configuration and creating a new space.

    Exports the source space (including settings, instructions, sample questions)
    and imports it as a new space. Useful for promoting spaces across environments
    or creating variants for different teams.

    Args:
        source_space_id: The Genie space ID to clone from
        new_display_name: Display name for the cloned space
        warehouse_id: Optional warehouse ID for the clone. If not provided,
            uses the same warehouse as the source space.
        description: Optional description for the clone. If not provided,
            uses the source space's description.

    Returns:
        Dictionary with:
        - space_id: The new cloned space ID
        - display_name: The new display name
        - source_space_id: The original space ID
        - operation: 'cloned'

    Example:
        >>> clone_genie(
        ...     source_space_id="abc123...",
        ...     new_display_name="Sales Analytics (Staging)",
        ... )
        {"space_id": "def456...", "display_name": "Sales Analytics (Staging)", ...}
    """
    try:
        manager = _get_manager()

        source = manager.genie_get(source_space_id, include_serialized_space=True)
        if not source:
            return {"error": f"Source Genie space {source_space_id} not found"}

        target_warehouse = warehouse_id or source.get("warehouse_id")
        if not target_warehouse:
            target_warehouse = manager.get_best_warehouse_id()
            if not target_warehouse:
                return {"error": "No SQL warehouses available. Please provide a warehouse_id."}

        target_description = description or source.get("description", "")

        result = manager.genie_create(
            display_name=new_display_name,
            warehouse_id=target_warehouse,
            table_identifiers=source.get("table_identifiers", []),
            description=target_description,
            serialized_space=source.get("serialized_space"),
        )

        new_space_id = result.get("space_id", "")

        try:
            if new_space_id:
                from ..manifest import track_resource

                track_resource(
                    resource_type="genie_space",
                    name=new_display_name,
                    resource_id=new_space_id,
                )
        except Exception:
            pass

        return {
            "space_id": new_space_id,
            "display_name": new_display_name,
            "source_space_id": source_space_id,
            "operation": "cloned",
            "warehouse_id": target_warehouse,
            "table_count": len(source.get("table_identifiers", [])),
        }

    except Exception as e:
        return {"error": f"Failed to clone Genie space: {e}"}


@mcp.tool
def manage_genie_instructions(
    space_id: str,
    action: str = "list",
    instruction_type: Optional[str] = None,
    title: Optional[str] = None,
    content: Optional[str] = None,
    instructions: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    """
    Manage instructions for a Genie Space (list, add text notes, add SQL examples).

    Instructions guide how Genie interprets questions and generates SQL.
    Text instructions provide general guidance; SQL instructions provide
    example queries that Genie can reference.

    Args:
        space_id: The Genie space ID
        action: One of:
            - "list": List all instructions in the space
            - "add_text": Add a text instruction/note
            - "add_sql": Add a SQL query example
            - "add_sql_function": Add a certified SQL function
            - "add_batch": Add multiple SQL instructions at once
        instruction_type: Not needed — determined by action
        title: Title for the instruction (required for add_text, add_sql)
        content: Content of the instruction (required for add_text, add_sql,
            add_sql_function)
        instructions: For add_batch: list of {"title": str, "content": str}
            dicts to add as SQL instructions

    Returns:
        For "list": {"instructions": [...]} with all instructions
        For "add_*": The created instruction dict
        For "add_batch": {"added": int, "results": [...]}

    Example:
        >>> manage_genie_instructions(space_id="abc123", action="list")
        {"instructions": [{"title": "...", "content": "...", "instruction_type": "..."}, ...]}

        >>> manage_genie_instructions(
        ...     space_id="abc123",
        ...     action="add_text",
        ...     title="Date handling",
        ...     content="When users say 'last month', use date_trunc('month', current_date()) - interval 1 month"
        ... )

        >>> manage_genie_instructions(
        ...     space_id="abc123",
        ...     action="add_sql",
        ...     title="Revenue by region",
        ...     content="SELECT region, SUM(amount) as revenue FROM sales GROUP BY region"
        ... )

        >>> manage_genie_instructions(
        ...     space_id="abc123",
        ...     action="add_batch",
        ...     instructions=[
        ...         {"title": "Top customers",
        ...          "content": "SELECT customer, SUM(amount) FROM orders GROUP BY 1 LIMIT 10"},
        ...         {"title": "Monthly trend",
        ...          "content": "SELECT date_trunc('month', order_date), COUNT(*) FROM orders GROUP BY 1"},
        ...     ]
        ... )
    """
    try:
        manager = _get_manager()

        if action == "list":
            result = manager.genie_list_instructions(space_id)
            return {"instructions": result.get("instructions", [])}

        elif action == "add_text":
            if not content:
                return {"error": "content is required for add_text"}
            return manager.genie_add_text_instruction(space_id, content=content, title=title or "Notes")

        elif action == "add_sql":
            if not title or not content:
                return {"error": "title and content are required for add_sql"}
            return manager.genie_add_sql_instruction(space_id, title=title, content=content)

        elif action == "add_sql_function":
            if not content:
                return {"error": "content (function name) is required for add_sql_function"}
            return manager.genie_add_sql_function(space_id, function_name=content)

        elif action == "add_batch":
            if not instructions:
                return {"error": "instructions list is required for add_batch"}
            results = manager.genie_add_sql_instructions_batch(space_id, instructions)
            return {"added": len(results), "results": results}

        else:
            return {"error": f"Unknown action '{action}'. Use: list, add_text, add_sql, add_sql_function, add_batch"}

    except Exception as e:
        return {"error": f"Failed to manage instructions for space {space_id}: {e}"}


# ============================================================================
# Genie Conversation API Tools
# ============================================================================


@mcp.tool
def ask_genie(
    space_id: str,
    question: str,
    conversation_id: Optional[str] = None,
    timeout_seconds: int = 120,
) -> Dict[str, Any]:
    """
    Ask a natural language question to a Genie Space and get the answer.

    Starts a new conversation, or continues an existing one if conversation_id
    is provided. Genie generates SQL, executes it, and returns the results.

    Args:
        space_id: The Genie Space ID to query
        question: The natural language question to ask
        conversation_id: Optional ID from a previous ask_genie response.
            If provided, continues that conversation (follow-up question).
            If omitted, starts a new conversation.
        timeout_seconds: Maximum time to wait for response (default 120)

    Returns:
        Dictionary with:
        - question: The original question
        - conversation_id: ID for follow-up questions
        - message_id: The message ID
        - status: COMPLETED, FAILED, or CANCELLED
        - sql: The SQL query Genie generated (if successful)
        - description: Genie's interpretation of the question
        - columns: List of column names in the result
        - data: Query results as list of rows
        - row_count: Number of rows returned
        - text_response: Natural language summary of results
        - error: Error message (if failed)

    Example:
        >>> result = ask_genie(space_id="abc123", question="What were total sales?")
        >>> ask_genie(space_id="abc123", question="Break that down by region",
        ...           conversation_id=result["conversation_id"])
    """
    try:
        w = get_workspace_client()

        if conversation_id:
            result = w.genie.create_message_and_wait(
                space_id=space_id,
                conversation_id=conversation_id,
                content=question,
                timeout=timedelta(seconds=timeout_seconds),
            )
        else:
            result = w.genie.start_conversation_and_wait(
                space_id=space_id,
                content=question,
                timeout=timedelta(seconds=timeout_seconds),
            )

        return _format_genie_response(question, result, space_id, w)
    except TimeoutError:
        return {
            "question": question,
            "conversation_id": conversation_id,
            "status": "TIMEOUT",
            "error": f"Genie response timed out after {timeout_seconds}s",
        }
    except Exception as e:
        return {
            "question": question,
            "conversation_id": conversation_id,
            "status": "ERROR",
            "error": str(e),
        }


# ============================================================================
# Helper Functions
# ============================================================================


def _format_genie_response(question: str, genie_message: Any, space_id: str, w: Any) -> Dict[str, Any]:
    """Format a Genie SDK response into a clean dictionary.

    Args:
        question: The original question asked
        genie_message: The GenieMessage object from the SDK
        space_id: The Genie Space ID (needed to fetch query results)
        w: The WorkspaceClient instance to use for fetching query results
    """
    result = {
        "question": question,
        "conversation_id": genie_message.conversation_id,
        "message_id": genie_message.id,
        "status": str(genie_message.status.value) if genie_message.status else "UNKNOWN",
    }

    # Extract data from attachments
    if genie_message.attachments:
        for attachment in genie_message.attachments:
            # Query attachment (SQL and results)
            if attachment.query:
                result["sql"] = attachment.query.query or ""
                result["description"] = attachment.query.description or ""

                # Get row count from metadata
                if attachment.query.query_result_metadata:
                    result["row_count"] = attachment.query.query_result_metadata.row_count

                # Fetch actual data (columns and rows)
                if attachment.attachment_id:
                    try:
                        data_result = w.genie.get_message_query_result_by_attachment(
                            space_id=space_id,
                            conversation_id=genie_message.conversation_id,
                            message_id=genie_message.id,
                            attachment_id=attachment.attachment_id,
                        )
                        if data_result.statement_response:
                            sr = data_result.statement_response
                            # Get columns
                            if sr.manifest and sr.manifest.schema and sr.manifest.schema.columns:
                                result["columns"] = [c.name for c in sr.manifest.schema.columns]
                            # Get data
                            if sr.result and sr.result.data_array:
                                result["data"] = sr.result.data_array
                    except Exception:
                        # If data fetch fails, continue without it
                        pass

            # Text attachment (explanation)
            if attachment.text:
                result["text_response"] = attachment.text.content or ""

    return result
