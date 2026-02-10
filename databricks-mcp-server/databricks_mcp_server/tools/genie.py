"""Genie tools - Create, manage, and query Databricks Genie Spaces."""

from datetime import timedelta
from typing import Any, Dict, List, Optional

from databricks_tools_core.agent_bricks import AgentBricksManager
from databricks_tools_core.auth import get_workspace_client

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
def list_genie() -> List[Dict[str, Any]]:
    """
    List all Genie Spaces accessible to the current user.

    Returns:
        List of Genie Space summaries, each containing:
        - space_id: The Genie space ID
        - title: The space title/name
        - description: The description (if set)

    Example:
        >>> list_genie()
        [
            {"space_id": "abc123...", "title": "Sales Analytics", "description": "..."},
            {"space_id": "def456...", "title": "HR Metrics", "description": "..."}
        ]
    """
    try:
        w = get_workspace_client()
        response = w.genie.list_spaces()
        result = []
        if response.spaces:
            for space in response.spaces:
                result.append(
                    {
                        "space_id": space.space_id,
                        "title": space.title or "",
                        "description": space.description or "",
                    }
                )
        return result
    except Exception as e:
        return [{"error": str(e)}]


@mcp.tool
def create_or_update_genie(
    display_name: str,
    table_identifiers: List[str],
    warehouse_id: Optional[str] = None,
    description: Optional[str] = None,
    sample_questions: Optional[List[str]] = None,
    space_id: Optional[str] = None,
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
    """
    manager = _get_manager()

    # Auto-detect warehouse if not provided
    if warehouse_id is None:
        warehouse_id = manager.get_best_warehouse_id()
        if warehouse_id is None:
            return {"error": "No SQL warehouses available. Please provide a warehouse_id or create a warehouse."}

    operation = "created"

    if space_id:
        # Update existing space by ID
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
            )
        else:
            return {"error": f"Genie space {space_id} not found"}
    else:
        # Check if exists by name first
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
            )
            space_id = existing.space_id
        else:
            # Create new
            result = manager.genie_create(
                display_name=display_name,
                warehouse_id=warehouse_id,
                table_identifiers=table_identifiers,
                description=description,
            )
            space_id = result.get("space_id", "")

            # Add sample questions if provided
            if sample_questions and space_id:
                manager.genie_add_sample_questions_batch(space_id, sample_questions)

    response = {
        "space_id": space_id,
        "display_name": display_name,
        "operation": operation,
        "warehouse_id": warehouse_id,
        "table_count": len(table_identifiers),
    }

    # Track resource on successful create/update
    try:
        if space_id:
            from ..manifest import track_resource

            track_resource(
                resource_type="genie_space",
                name=display_name,
                resource_id=space_id,
            )
    except Exception:
        pass  # best-effort tracking

    return response


@mcp.tool
def get_genie(space_id: str) -> Dict[str, Any]:
    """
    Get a Genie Space by ID.

    Args:
        space_id: The Genie space ID

    Returns:
        Dictionary with Genie space details including:
        - space_id: The space ID
        - display_name: The display name
        - description: The description
        - warehouse_id: The SQL warehouse ID
        - table_identifiers: List of configured tables
        - sample_questions: List of sample questions

    Example:
        >>> get_genie("abc123...")
        {"space_id": "abc123...", "display_name": "Sales Analytics", ...}
    """
    manager = _get_manager()
    result = manager.genie_get(space_id)

    if not result:
        return {"error": f"Genie space {space_id} not found"}

    # Get sample questions
    questions_response = manager.genie_list_questions(space_id, question_type="SAMPLE_QUESTION")
    sample_questions = [q.get("question_text", "") for q in questions_response.get("curated_questions", [])]

    return {
        "space_id": result.get("space_id", space_id),
        "display_name": result.get("display_name", ""),
        "description": result.get("description", ""),
        "warehouse_id": result.get("warehouse_id", ""),
        "table_identifiers": result.get("table_identifiers", []),
        "sample_questions": sample_questions,
    }


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


# ============================================================================
# Genie Conversation API Tools
# ============================================================================


@mcp.tool
def ask_genie(
    space_id: str,
    question: str,
    timeout_seconds: int = 120,
) -> Dict[str, Any]:
    """
    Ask a natural language question to a Genie Space and get the answer.

    This tool sends a question to a Genie Space, which generates SQL,
    executes it, and returns the results.

    Args:
        space_id: The Genie Space ID to query
        question: The natural language question to ask
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
        >>> ask_genie(space_id="abc123", question="What were total sales last month?")
        {"question": "...", "status": "COMPLETED", "sql": "SELECT ...", "data": [[125430.50]], ...}
    """
    try:
        w = get_workspace_client()
        result = w.genie.start_conversation_and_wait(
            space_id=space_id,
            content=question,
            timeout=timedelta(seconds=timeout_seconds),
        )
        return _format_genie_response(question, result, space_id)
    except TimeoutError:
        return {
            "question": question,
            "status": "TIMEOUT",
            "error": f"Genie response timed out after {timeout_seconds}s",
        }
    except Exception as e:
        return {
            "question": question,
            "status": "ERROR",
            "error": str(e),
        }


@mcp.tool
def ask_genie_followup(
    space_id: str,
    conversation_id: str,
    question: str,
    timeout_seconds: int = 120,
) -> Dict[str, Any]:
    """
    Ask a follow-up question in an existing Genie conversation.

    Use this to ask follow-up questions that reference the previous context.
    For example, after asking "What were total sales?", you could follow up
    with "Break that down by region" without repeating the context.

    Args:
        space_id: The Genie Space ID
        conversation_id: The conversation_id from a previous ask_genie response
        question: The follow-up question
        timeout_seconds: Maximum time to wait for response (default 120)

    Returns:
        Same format as ask_genie

    Example:
        >>> result = ask_genie(space_id, "What were total sales last month?")
        >>> ask_genie_followup(space_id, result["conversation_id"], "Break that down by region")
    """
    try:
        w = get_workspace_client()
        result = w.genie.create_message_and_wait(
            space_id=space_id,
            conversation_id=conversation_id,
            content=question,
            timeout=timedelta(seconds=timeout_seconds),
        )
        return _format_genie_response(question, result, space_id)
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


def _format_genie_response(question: str, genie_message: Any, space_id: str) -> Dict[str, Any]:
    """Format a Genie SDK response into a clean dictionary.

    Args:
        question: The original question asked
        genie_message: The GenieMessage object from the SDK
        space_id: The Genie Space ID (needed to fetch query results)
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
                        w = get_workspace_client()
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
