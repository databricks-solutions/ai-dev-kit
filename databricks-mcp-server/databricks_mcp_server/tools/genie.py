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


@mcp.tool(timeout=60)
def create_or_update_genie(
    display_name: str,
    table_identifiers: List[str],
    warehouse_id: Optional[str] = None,
    description: Optional[str] = None,
    sample_questions: Optional[List[str]] = None,
    space_id: Optional[str] = None,
    serialized_space: Optional[str] = None,
) -> Dict[str, Any]:
    """Create/update Genie Space for natural language SQL queries.

    table_identifiers: ["catalog.schema.table", ...]. description: Explains space purpose to users.
    sample_questions: Example questions shown to users. warehouse_id: auto-detected if omitted.
    serialized_space: Full config from migrate_genie(type="export"), preserves instructions/SQL examples.
    See databricks-genie skill for configuration details.
    Returns: {space_id, display_name, operation: created|updated, warehouse_id, table_count}."""
    try:
        description = with_description_footer(description)
        manager = _get_manager()

        # Auto-detect warehouse if not provided
        if warehouse_id is None:
            warehouse_id = manager.get_best_warehouse_id()
            if warehouse_id is None:
                return {"error": "No SQL warehouses available. Please provide a warehouse_id or create a warehouse."}

        operation = "created"

        # When serialized_space is provided
        if serialized_space:
            if space_id:
                # Update existing space with serialized config
                manager.genie_update_with_serialized_space(
                    space_id=space_id,
                    serialized_space=serialized_space,
                    title=display_name,
                    description=description,
                    warehouse_id=warehouse_id,
                )
                operation = "updated"
            else:
                # Check if exists by name, then create or update
                existing = manager.genie_find_by_name(display_name)
                if existing:
                    operation = "updated"
                    space_id = existing.space_id
                    manager.genie_update_with_serialized_space(
                        space_id=space_id,
                        serialized_space=serialized_space,
                        title=display_name,
                        description=description,
                        warehouse_id=warehouse_id,
                    )
                else:
                    result = manager.genie_import(
                        warehouse_id=warehouse_id,
                        serialized_space=serialized_space,
                        title=display_name,
                        description=description,
                    )
                    space_id = result.get("space_id", "")

        # When serialized_space is not provided
        else:
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


@mcp.tool(timeout=30)
def get_genie(space_id: Optional[str] = None, include_serialized_space: bool = False) -> Dict[str, Any]:
    """Get Genie Space details or list all. include_serialized_space=True for full config export.

    Returns: {space_id, display_name, description, warehouse_id, table_identifiers, sample_questions} or {spaces: [...]}."""
    if space_id:
        try:
            manager = _get_manager()
            result = manager.genie_get(space_id)

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

            if include_serialized_space:
                exported = manager.genie_export(space_id)
                response["serialized_space"] = exported.get("serialized_space", "")

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


@mcp.tool(timeout=30)
def delete_genie(space_id: str) -> Dict[str, Any]:
    """Delete a Genie Space. Returns: {success, space_id}."""
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


@mcp.tool(timeout=60)
def migrate_genie(
    type: str,
    space_id: Optional[str] = None,
    warehouse_id: Optional[str] = None,
    serialized_space: Optional[str] = None,
    title: Optional[str] = None,
    description: Optional[str] = None,
    parent_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Export/import Genie Space for cloning or cross-workspace migration.

    type="export": requires space_id. type="import": requires warehouse_id + serialized_space.
    Returns: export={space_id, title, serialized_space}, import={space_id, title, operation}."""
    if type == "export":
        if not space_id:
            return {"error": "space_id is required for type='export'"}
        manager = _get_manager()
        try:
            result = manager.genie_export(space_id)
            return {
                "space_id": result.get("space_id", space_id),
                "title": result.get("title", ""),
                "description": result.get("description", ""),
                "warehouse_id": result.get("warehouse_id", ""),
                "serialized_space": result.get("serialized_space", ""),
            }
        except Exception as e:
            return {"error": str(e), "space_id": space_id}

    elif type == "import":
        if not warehouse_id or not serialized_space:
            return {"error": "warehouse_id and serialized_space are required for type='import'"}
        manager = _get_manager()
        try:
            result = manager.genie_import(
                warehouse_id=warehouse_id,
                serialized_space=serialized_space,
                title=title,
                description=description,
                parent_path=parent_path,
            )
            imported_space_id = result.get("space_id", "")

            if imported_space_id:
                try:
                    from ..manifest import track_resource

                    track_resource(
                        resource_type="genie_space",
                        name=title or result.get("title", imported_space_id),
                        resource_id=imported_space_id,
                    )
                except Exception:
                    pass

            return {
                "space_id": imported_space_id,
                "title": result.get("title", title or ""),
                "description": result.get("description", description or ""),
                "operation": "imported",
            }
        except Exception as e:
            return {"error": str(e)}

    else:
        return {"error": f"Invalid type '{type}'. Must be 'export' or 'import'."}


# ============================================================================
# Genie Conversation API Tools
# ============================================================================


@mcp.tool(timeout=120)
def ask_genie(
    space_id: str,
    question: str,
    conversation_id: Optional[str] = None,
    timeout_seconds: int = 120,
) -> Dict[str, Any]:
    """Ask natural language question to Genie Space. Pass conversation_id for follow-ups.

    Returns: {question, conversation_id, message_id, status, sql, description, columns, data, row_count, text_response, error}."""
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
