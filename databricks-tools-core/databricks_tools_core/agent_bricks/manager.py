"""
Agent Bricks Manager - Manage Genie Spaces, Knowledge Assistants, and Multi-Agent Supervisors.

Unified wrapper for Agent Bricks tiles with operations for:
- Knowledge Assistants (KA): Document-based Q&A systems
- Multi-Agent Supervisors (MAS): Multi-agent orchestration
- Genie Spaces: SQL-based data exploration
"""

import json
import logging
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Tuple

import requests
from databricks.sdk import WorkspaceClient

from ..auth import get_workspace_client
from .models import (
    EndpointStatus,
    GenieIds,
    GenieListInstructionsResponseDict,
    GenieListQuestionsResponseDict,
    GenieSpaceDict,
    KAIds,
    KnowledgeAssistantListExamplesResponseDict,
    KnowledgeAssistantResponseDict,
    ListEvaluationRunsResponseDict,
    MASIds,
    MultiAgentSupervisorListExamplesResponseDict,
    MultiAgentSupervisorResponseDict,
    Permission,
    TileType,
)

logger = logging.getLogger(__name__)


class AgentBricksManager:
    """Unified wrapper for Agent Bricks tiles.

    Works with:
    - /2.0/knowledge-assistants* (KA)
    - /2.0/multi-agent-supervisors* (MAS)
    - /2.0/data-rooms* (Genie)
    - /2.0/tiles* (common operations)

    Key operations:
        Common tile ops:
        - delete(tile_id): Delete any tile
        - share(tile_id, changes): Share tile with users/groups

        KA-specific ops (prefixed with ka_):
        - ka_create(): Create KA with knowledge sources
        - ka_get(): Get KA by tile_id
        - ka_update(): Update KA configuration
        - ka_create_or_update(): Create or update a KA
        - ka_sync_sources(): Trigger re-index
        - ka_get_endpoint_status(): Get endpoint status
        - ka_add_examples_batch(): Add example questions

        MAS-specific ops (prefixed with mas_):
        - mas_create(): Create MAS with agents
        - mas_get(): Get MAS by tile_id
        - mas_update(): Update MAS configuration
        - mas_get_endpoint_status(): Get endpoint status
        - mas_add_examples_batch(): Add example questions

        Genie-specific ops (prefixed with genie_):
        - genie_create(): Create Genie space
        - genie_get(): Get Genie space
        - genie_update(): Update Genie space
        - genie_delete(): Delete Genie space
        - genie_add_sample_questions_batch(): Add sample questions
        - genie_add_sql_instructions_batch(): Add SQL examples
        - genie_add_benchmarks_batch(): Add benchmarks
    """

    def __init__(
        self,
        client: Optional[WorkspaceClient] = None,
        default_timeout_s: int = 600,
        default_poll_s: float = 2.0,
    ):
        """
        Initialize the Agent Bricks Manager.

        Args:
            client: Optional WorkspaceClient (creates new one if not provided)
            default_timeout_s: Default timeout for polling operations
            default_poll_s: Default poll interval in seconds
        """
        self.w: WorkspaceClient = client or get_workspace_client()
        self.default_timeout_s = default_timeout_s
        self.default_poll_s = default_poll_s

    @staticmethod
    def sanitize_name(name: str) -> str:
        """Sanitize a name to ensure it's alphanumeric with only hyphens and underscores.

        Args:
            name: The original name

        Returns:
            Sanitized name that complies with Databricks naming requirements
        """
        # Replace spaces with underscores
        sanitized = name.replace(" ", "_")

        # Replace any character that is not alphanumeric, hyphen, or underscore
        sanitized = re.sub(r"[^a-zA-Z0-9_-]", "_", sanitized)

        # Remove consecutive underscores or hyphens
        sanitized = re.sub(r"[_-]{2,}", "_", sanitized)

        # Remove leading/trailing underscores or hyphens
        sanitized = sanitized.strip("_-")

        # If the name is empty after sanitization, use a default
        if not sanitized:
            sanitized = "knowledge_assistant"

        logger.debug(f"Sanitized name: '{name}' -> '{sanitized}'")
        return sanitized

    # ========================================================================
    # Common Tile Operations
    # ========================================================================

    def delete(self, tile_id: str) -> None:
        """Delete any tile (KA or MAS) by ID."""
        self._delete(f"/api/2.0/tiles/{tile_id}")

    def share(self, tile_id: str, changes: List[Dict[str, Any]]) -> None:
        """Share a tile with specified permissions.

        Args:
            tile_id: The tile ID
            changes: List of permission changes, each containing:
                - principal: User/group (e.g., "users:email@company.com")
                - add: List of permissions to grant
                - remove: List of permissions to revoke

        Example:
            >>> manager.share(
            ...     tile_id,
            ...     changes=[
            ...         {
            ...             "principal": "users:john@company.com",
            ...             "add": [Permission.CAN_READ, Permission.CAN_RUN],
            ...             "remove": []
            ...         }
            ...     ]
            ... )
        """
        # Convert Permission enums to strings
        processed_changes = []
        for change in changes:
            processed_change = {
                "principal": change["principal"],
                "add": [
                    p.value if isinstance(p, Permission) else p
                    for p in change.get("add", [])
                ],
                "remove": [
                    p.value if isinstance(p, Permission) else p
                    for p in change.get("remove", [])
                ],
            }
            processed_changes.append(processed_change)

        self._post(
            f"/api/2.0/knowledge-assistants/{tile_id}/share",
            {"changes": processed_changes},
        )

    # ========================================================================
    # Discovery & Listing
    # ========================================================================

    def list_all_agent_bricks(
        self, tile_type: Optional[TileType] = None, page_size: int = 100
    ) -> List[Dict[str, Any]]:
        """List all agent bricks (tiles) in the workspace.

        Args:
            tile_type: Specific tile type to filter for. If None, returns all.
            page_size: Number of results per page.

        Returns:
            List of Tile dictionaries.
        """
        all_tiles = []

        # Build filter query
        filter_q = f"tile_type={tile_type.name}" if tile_type else None
        page_token = None

        while True:
            params = {"page_size": page_size}
            if filter_q:
                params["filter"] = filter_q
            if page_token:
                params["page_token"] = page_token

            resp = self._get("/api/2.0/tiles", params=params)

            for tile in resp.get("tiles", []):
                if tile_type:
                    tile_type_value = tile.get("tile_type")
                    if (
                        tile_type_value == tile_type.value
                        or tile_type_value == tile_type.name
                    ):
                        all_tiles.append(tile)
                else:
                    all_tiles.append(tile)

            page_token = resp.get("next_page_token")
            if not page_token:
                break

        return all_tiles

    def find_by_name(self, name: str) -> Optional[KAIds]:
        """Find a KA by exact display name."""
        filter_q = f"name_contains={name}&&tile_type=KA"
        page_token = None
        while True:
            params = {"filter": filter_q}
            if page_token:
                params["page_token"] = page_token
            resp = self._get("/api/2.0/tiles", params=params)
            for t in resp.get("tiles", []):
                if t.get("name") == name:
                    return KAIds(tile_id=t["tile_id"], name=name)
            page_token = resp.get("next_page_token")
            if not page_token:
                break
        return None

    def mas_find_by_name(self, name: str) -> Optional[MASIds]:
        """Find a MAS by exact display name."""
        filter_q = f"name_contains={name}&&tile_type=MAS"
        page_token = None
        while True:
            params = {"filter": filter_q}
            if page_token:
                params["page_token"] = page_token
            resp = self._get("/api/2.0/tiles", params=params)
            for t in resp.get("tiles", []):
                if t.get("name") == name:
                    return MASIds(tile_id=t["tile_id"], name=name)
            page_token = resp.get("next_page_token")
            if not page_token:
                break
        return None

    def genie_find_by_name(self, display_name: str) -> Optional[GenieIds]:
        """Find a Genie space by exact display name."""
        page_token = None
        while True:
            params = {}
            if page_token:
                params["page_token"] = page_token
            resp = self._get("/api/2.0/data-rooms", params=params)
            for space in resp.get("data_rooms", []):
                if space.get("display_name") == display_name:
                    return GenieIds(
                        space_id=space["space_id"], display_name=display_name
                    )
            page_token = resp.get("next_page_token")
            if not page_token:
                break
        return None

    # ========================================================================
    # Knowledge Assistant (KA) Operations
    # ========================================================================

    def ka_create(
        self,
        name: str,
        knowledge_sources: List[Dict[str, Any]],
        description: Optional[str] = None,
        instructions: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a Knowledge Assistant with specified knowledge sources.

        Args:
            name: Name for the KA
            knowledge_sources: List of knowledge source dictionaries:
                {
                    "files_source": {
                        "name": "source_name",
                        "type": "files",
                        "files": {"path": "/Volumes/catalog/schema/path"}
                    }
                }
            description: Optional description
            instructions: Optional instructions

        Returns:
            KA creation response with tile info
        """
        sanitized_name = self.sanitize_name(name)
        payload: Dict[str, Any] = {
            "name": sanitized_name,
            "knowledge_sources": knowledge_sources,
        }
        if instructions:
            payload["instructions"] = instructions
        if description:
            payload["description"] = description

        logger.debug(f"Creating KA with payload: {payload}")
        return self._post("/api/2.0/knowledge-assistants", payload)

    def ka_get(self, tile_id: str) -> Optional[KnowledgeAssistantResponseDict]:
        """Get KA by tile_id.

        Returns:
            KA data dictionary or None if not found.
        """
        try:
            return self._get(f"/api/2.0/knowledge-assistants/{tile_id}")
        except Exception as e:
            if "does not exist" in str(e).lower() or "not found" in str(e).lower():
                return None
            raise

    def ka_get_endpoint_status(self, tile_id: str) -> Optional[str]:
        """Get the endpoint status of a Knowledge Assistant.

        Returns:
            Status string (ONLINE, OFFLINE, PROVISIONING, NOT_READY) or None
        """
        ka = self.ka_get(tile_id)
        if not ka:
            return None
        return (
            ka.get("knowledge_assistant", {}).get("status", {}).get("endpoint_status")
        )

    def ka_is_ready_for_update(self, tile_id: str) -> bool:
        """Check if a KA is ready to be updated (status is ONLINE)."""
        status = self.ka_get_endpoint_status(tile_id)
        return status == EndpointStatus.ONLINE.value

    def ka_wait_for_ready_status(
        self, tile_id: str, timeout: int = 60, poll_interval: int = 5
    ) -> bool:
        """Wait for a KA to be ready for updates.

        Returns:
            True if ready within timeout, False otherwise.
        """
        start_time = time.time()
        while time.time() - start_time < timeout:
            if self.ka_is_ready_for_update(tile_id):
                logger.info(
                    f"KA {tile_id} is ready (status: {EndpointStatus.ONLINE.value})"
                )
                return True
            current_status = self.ka_get_endpoint_status(tile_id)
            logger.info(f"KA {tile_id} status: {current_status}, waiting...")
            time.sleep(poll_interval)

        logger.warning(f"Timeout waiting for KA {tile_id} to be ready")
        return False

    def ka_update(
        self,
        tile_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        instructions: Optional[str] = None,
        knowledge_sources: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Update KA metadata and/or knowledge sources.

        Args:
            tile_id: The KA tile ID
            name: Optional new name
            description: Optional new description
            instructions: Optional new instructions
            knowledge_sources: Optional new sources (replaces existing)

        Returns:
            Updated KA data
        """
        # Update metadata if provided
        if name is not None or description is not None or instructions is not None:
            body: Dict[str, Any] = {}
            if name is not None:
                body["name"] = name
            if description is not None:
                body["description"] = description
            if instructions is not None:
                body["instructions"] = instructions
            self._patch(f"/api/2.0/knowledge-assistants/{tile_id}", body)

        # Update knowledge sources if provided
        if knowledge_sources is not None:
            current_ka = self.ka_get(tile_id)
            if not current_ka:
                raise ValueError(f"Knowledge Assistant {tile_id} not found")

            current_name = current_ka["knowledge_assistant"]["tile"]["name"]
            current_sources = current_ka.get("knowledge_assistant", {}).get(
                "knowledge_sources", []
            )

            source_ids_to_remove = [
                s.get("knowledge_source_id")
                for s in current_sources
                if s.get("knowledge_source_id")
            ]

            body = {"name": current_name}
            if knowledge_sources:
                body["add_knowledge_sources"] = knowledge_sources
            if source_ids_to_remove:
                body["remove_knowledge_source_ids"] = source_ids_to_remove

            if knowledge_sources or source_ids_to_remove:
                self._patch(f"/api/2.0/knowledge-assistants/{tile_id}", body)

        return self.ka_get(tile_id)

    def ka_create_or_update(
        self,
        name: str,
        knowledge_sources: List[Dict[str, Any]],
        description: Optional[str] = None,
        instructions: Optional[str] = None,
        tile_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create or update a Knowledge Assistant.

        Args:
            name: Name for the KA
            knowledge_sources: List of knowledge source dictionaries
            description: Optional description
            instructions: Optional instructions
            tile_id: Optional existing tile_id to update

        Returns:
            KA data with 'operation' field ('created' or 'updated')
        """
        sanitized_name = self.sanitize_name(name)
        existing_ka = None
        operation = "created"

        if tile_id:
            existing_ka = self.ka_get(tile_id)
            if existing_ka:
                operation = "updated"

        if existing_ka:
            if not self.ka_is_ready_for_update(tile_id):
                current_status = self.ka_get_endpoint_status(tile_id)
                raise Exception(
                    f"Knowledge Assistant {tile_id} is not ready for update "
                    f"(status: {current_status}). Wait or delete and create new."
                )

            result = self.ka_update(
                tile_id,
                name=sanitized_name,
                description=description,
                instructions=instructions,
                knowledge_sources=knowledge_sources,
            )
        else:
            result = self.ka_create(
                name=sanitized_name,
                knowledge_sources=knowledge_sources,
                description=description,
                instructions=instructions,
            )

        if result:
            result["operation"] = operation
        return result

    def ka_sync_sources(self, tile_id: str) -> None:
        """Trigger indexing/sync of all knowledge sources."""
        self._post(
            f"/api/2.0/knowledge-assistants/{tile_id}/sync-knowledge-sources", {}
        )

    def ka_reconcile_model(self, tile_id: str) -> None:
        """Reconcile KA to latest model."""
        self._patch(f"/api/2.0/knowledge-assistants/{tile_id}/reconcile-model", {})

    def ka_wait_until_ready(
        self,
        tile_id: str,
        timeout_s: Optional[int] = None,
        poll_s: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Wait until KA is ready (not in PROVISIONING state)."""
        timeout_s = timeout_s or self.default_timeout_s
        poll_s = poll_s or self.default_poll_s
        deadline = time.time() + timeout_s

        while True:
            ka = self.ka_get(tile_id)
            status = (
                ka.get("knowledge_assistant", {})
                .get("status", {})
                .get("endpoint_status")
            )
            if status and status != "PROVISIONING":
                return ka
            if time.time() >= deadline:
                return ka
            time.sleep(poll_s)

    def ka_wait_until_endpoint_online(
        self,
        tile_id: str,
        timeout_s: Optional[int] = None,
        poll_s: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Wait for endpoint_status==ONLINE."""
        timeout_s = timeout_s or self.default_timeout_s
        poll_s = poll_s or self.default_poll_s
        deadline = time.time() + timeout_s
        start_time = time.time()
        last_status = None
        ka = None

        while True:
            try:
                ka = self.ka_get(tile_id)
                status = (
                    ka.get("knowledge_assistant", {})
                    .get("status", {})
                    .get("endpoint_status")
                )

                if status != last_status:
                    elapsed = int(time.time() - start_time)
                    logger.info(f"[{elapsed}s] KA status: {last_status} -> {status}")
                    last_status = status

                if status == "ONLINE":
                    return ka
            except Exception as e:
                elapsed = int(time.time() - start_time)
                if "does not exist" in str(e) and elapsed < 60:
                    logger.debug(f"[{elapsed}s] KA not yet available, waiting...")
                else:
                    raise

            if time.time() >= deadline:
                if ka:
                    return ka
                raise TimeoutError(
                    f"KA {tile_id} was not found within {timeout_s} seconds"
                )
            time.sleep(poll_s)

    # ========================================================================
    # KA Examples Management
    # ========================================================================

    def ka_create_example(
        self, tile_id: str, question: str, guidelines: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Create an example question for the KA."""
        payload = {"tile_id": tile_id, "question": question}
        if guidelines:
            payload["guidelines"] = guidelines
        return self._post(f"/api/2.0/knowledge-assistants/{tile_id}/examples", payload)

    def ka_list_examples(
        self, tile_id: str, page_size: int = 100, page_token: Optional[str] = None
    ) -> KnowledgeAssistantListExamplesResponseDict:
        """List all examples for a KA."""
        params = {"page_size": page_size}
        if page_token:
            params["page_token"] = page_token
        return self._get(
            f"/api/2.0/knowledge-assistants/{tile_id}/examples", params=params
        )

    def ka_delete_example(self, tile_id: str, example_id: str) -> None:
        """Delete an example from the KA."""
        self._delete(f"/api/2.0/knowledge-assistants/{tile_id}/examples/{example_id}")

    def ka_add_examples_batch(
        self, tile_id: str, questions: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Add multiple example questions in parallel.

        Args:
            tile_id: The KA tile ID
            questions: List of {'question': str, 'guideline': Optional[str]}

        Returns:
            List of created examples
        """
        created_examples = []

        def create_example(q: Dict[str, Any]) -> Optional[Dict[str, Any]]:
            question_text = q.get("question", "")
            guideline = q.get("guideline")
            guidelines = [guideline] if guideline else None

            if not question_text:
                return None
            try:
                example = self.ka_create_example(tile_id, question_text, guidelines)
                logger.info(f"Added example: {question_text[:50]}...")
                return example
            except Exception as e:
                logger.error(f"Failed to add example '{question_text[:50]}...': {e}")
                return None

        max_workers = min(2, len(questions))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_q = {executor.submit(create_example, q): q for q in questions}
            for future in as_completed(future_to_q):
                result = future.result()
                if result:
                    created_examples.append(result)

        return created_examples

    def ka_list_evaluation_runs(
        self, tile_id: str, page_size: int = 100, page_token: Optional[str] = None
    ) -> ListEvaluationRunsResponseDict:
        """List all evaluation runs for a KA."""
        params = {"page_size": page_size}
        if page_token:
            params["page_token"] = page_token
        return self._get(f"/api/2.0/tiles/{tile_id}/evaluation-runs", params=params)

    # ========================================================================
    # KA Helper Methods
    # ========================================================================

    @staticmethod
    def ka_get_knowledge_sources_from_volumes(
        volume_paths: List[Tuple[str, Optional[str]]],
    ) -> List[Dict[str, Any]]:
        """Convert volume paths to knowledge source dictionaries.

        Args:
            volume_paths: List of (volume_path, description) tuples

        Returns:
            List of knowledge source dictionaries for KA API

        Example:
            >>> paths = [
            ...     ('/Volumes/main/default/docs', 'Documentation'),
            ...     ('/Volumes/main/default/guides', None)
            ... ]
            >>> sources = AgentBricksManager.ka_get_knowledge_sources_from_volumes(paths)
        """
        knowledge_sources = []

        for idx, (volume_path, description) in enumerate(volume_paths):
            path_parts = volume_path.rstrip("/").split("/")
            source_name = path_parts[-1] if path_parts else f"source_{idx + 1}"
            source_name = source_name.replace(" ", "_").replace(".", "_")

            knowledge_source = {
                "files_source": {
                    "name": source_name,
                    "type": "files",
                    "files": {"path": volume_path},
                }
            }
            knowledge_sources.append(knowledge_source)

        return knowledge_sources

    # ========================================================================
    # Multi-Agent Supervisor (MAS) Operations
    # ========================================================================

    def mas_create(
        self,
        name: str,
        agents: List[Dict[str, Any]],
        description: Optional[str] = None,
        instructions: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a Multi-Agent Supervisor with specified agents.

        Args:
            name: Name for the MAS
            agents: List of agent configurations (BaseAgent format):
                {
                    "name": "Agent Name",
                    "description": "Description",
                    "agent_type": "genie",  # or "ka", "app", etc.
                    "genie_space": {"id": "space_id"}  # or serving_endpoint, app
                }
            description: Optional description
            instructions: Optional instructions

        Returns:
            MAS creation response
        """
        payload = {"name": self.sanitize_name(name), "agents": agents}
        if description:
            payload["description"] = description
        if instructions:
            payload["instructions"] = instructions

        logger.info(f"Creating MAS with name={name}, {len(agents)} agents")
        return self._post("/api/2.0/multi-agent-supervisors", payload)

    def mas_get(self, tile_id: str) -> Optional[MultiAgentSupervisorResponseDict]:
        """Get MAS by tile_id."""
        try:
            return self._get(f"/api/2.0/multi-agent-supervisors/{tile_id}")
        except Exception as e:
            if "does not exist" in str(e).lower() or "not found" in str(e).lower():
                return None
            raise

    def mas_update(
        self,
        tile_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        instructions: Optional[str] = None,
        agents: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Update a Multi-Agent Supervisor."""
        payload = {"tile_id": tile_id}
        if name:
            payload["name"] = self.sanitize_name(name)
        if description:
            payload["description"] = description
        if instructions:
            payload["instructions"] = instructions
        if agents:
            payload["agents"] = agents

        logger.info(f"Updating MAS {tile_id}")
        return self._patch(f"/api/2.0/multi-agent-supervisors/{tile_id}", payload)

    def mas_get_endpoint_status(self, tile_id: str) -> Optional[str]:
        """Get the endpoint status of a MAS."""
        mas = self.mas_get(tile_id)
        if not mas:
            return None
        return (
            mas.get("multi_agent_supervisor", {})
            .get("status", {})
            .get("endpoint_status")
        )

    # ========================================================================
    # MAS Examples Management
    # ========================================================================

    def mas_create_example(
        self, tile_id: str, question: str, guidelines: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Create an example question for the MAS."""
        payload = {"tile_id": tile_id, "question": question}
        if guidelines:
            payload["guidelines"] = guidelines
        return self._post(
            f"/api/2.0/multi-agent-supervisors/{tile_id}/examples", payload
        )

    def mas_list_examples(
        self, tile_id: str, page_size: int = 100, page_token: Optional[str] = None
    ) -> MultiAgentSupervisorListExamplesResponseDict:
        """List all examples for a MAS."""
        params = {"page_size": page_size}
        if page_token:
            params["page_token"] = page_token
        return self._get(
            f"/api/2.0/multi-agent-supervisors/{tile_id}/examples", params=params
        )

    def mas_update_example(
        self,
        tile_id: str,
        example_id: str,
        question: Optional[str] = None,
        guidelines: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Update an example in a MAS."""
        payload = {"tile_id": tile_id, "example_id": example_id}
        if question:
            payload["question"] = question
        if guidelines:
            payload["guidelines"] = guidelines
        return self._patch(
            f"/api/2.0/multi-agent-supervisors/{tile_id}/examples/{example_id}", payload
        )

    def mas_delete_example(self, tile_id: str, example_id: str) -> None:
        """Delete an example from the MAS."""
        self._delete(
            f"/api/2.0/multi-agent-supervisors/{tile_id}/examples/{example_id}"
        )

    def mas_add_examples_batch(
        self, tile_id: str, questions: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
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
                example = self.mas_create_example(tile_id, question_text, guidelines)
                logger.info(f"Added MAS example: {question_text[:50]}...")
                return example
            except Exception as e:
                logger.error(
                    f"Failed to add MAS example '{question_text[:50]}...': {e}"
                )
                return None

        max_workers = min(2, len(questions))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_q = {executor.submit(create_example, q): q for q in questions}
            for future in as_completed(future_to_q):
                result = future.result()
                if result:
                    created_examples.append(result)

        return created_examples

    def mas_list_evaluation_runs(
        self, tile_id: str, page_size: int = 100, page_token: Optional[str] = None
    ) -> ListEvaluationRunsResponseDict:
        """List all evaluation runs for a MAS."""
        params = {"page_size": page_size}
        if page_token:
            params["page_token"] = page_token
        return self._get(f"/api/2.0/tiles/{tile_id}/evaluation-runs", params=params)

    # ========================================================================
    # Genie Space Operations
    # ========================================================================

    def genie_get(self, space_id: str) -> Optional[GenieSpaceDict]:
        """Get Genie space by ID."""
        try:
            return self._get(f"/api/2.0/data-rooms/{space_id}")
        except Exception as e:
            if "does not exist" in str(e).lower() or "not found" in str(e).lower():
                return None
            raise

    def genie_create(
        self,
        display_name: str,
        warehouse_id: str,
        table_identifiers: List[str],
        description: Optional[str] = None,
        parent_folder_path: Optional[str] = None,
        parent_folder_id: Optional[str] = None,
        create_dir: bool = True,
        run_as_type: str = "VIEWER",
    ) -> Dict[str, Any]:
        """Create a Genie space.

        Args:
            display_name: Display name for the space
            warehouse_id: SQL warehouse ID to use
            table_identifiers: List of tables (e.g., ["catalog.schema.table"])
            description: Optional description
            parent_folder_path: Optional workspace folder path
            parent_folder_id: Optional parent folder ID
            create_dir: Whether to create parent folder if missing
            run_as_type: Run as type (default: "VIEWER")

        Returns:
            Created Genie space data
        """
        if parent_folder_path and parent_folder_id:
            raise ValueError(
                "Cannot specify both parent_folder_path and parent_folder_id"
            )

        room_payload = {
            "display_name": display_name,
            "warehouse_id": warehouse_id,
            "table_identifiers": table_identifiers,
            "run_as_type": run_as_type,
        }

        if description:
            room_payload["description"] = description

        # Resolve parent folder
        if parent_folder_path:
            if create_dir:
                try:
                    self.w.workspace.mkdirs(parent_folder_path)
                except Exception as e:
                    logger.warning(
                        f"Could not create directory {parent_folder_path}: {e}"
                    )
                    raise

            try:
                folder_status = self._get(
                    "/api/2.0/workspace/get-status", params={"path": parent_folder_path}
                )
                parent_folder_id = folder_status["object_id"]
            except Exception as e:
                raise ValueError(
                    f"Failed to get folder ID for path '{parent_folder_path}': {str(e)}"
                )

        if parent_folder_id:
            room_payload["parent_folder"] = f"folders/{parent_folder_id}"

        return self._post("/api/2.0/data-rooms/", room_payload)

    def genie_update(
        self,
        space_id: str,
        display_name: Optional[str] = None,
        description: Optional[str] = None,
        warehouse_id: Optional[str] = None,
        table_identifiers: Optional[List[str]] = None,
        sample_questions: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Update a Genie space.

        Args:
            space_id: The Genie space ID
            display_name: Optional new display name
            description: Optional new description
            warehouse_id: Optional new warehouse ID
            table_identifiers: Optional new table identifiers
            sample_questions: Optional sample questions (replaces all existing)

        Returns:
            Updated Genie space data
        """
        current_space = self.genie_get(space_id)
        if not current_space:
            raise ValueError(f"Genie space {space_id} not found")

        update_payload = {
            "id": space_id,
            "space_id": current_space.get("space_id", space_id),
            "display_name": display_name or current_space.get("display_name"),
            "warehouse_id": warehouse_id or current_space.get("warehouse_id"),
            "table_identifiers": table_identifiers
            if table_identifiers is not None
            else current_space.get("table_identifiers", []),
            "run_as_type": current_space.get("run_as_type", "VIEWER"),
        }

        if description is not None:
            update_payload["description"] = description
        elif current_space.get("description"):
            update_payload["description"] = current_space["description"]

        # Preserve timestamps and user info
        for field in [
            "created_timestamp",
            "last_updated_timestamp",
            "user_id",
            "folder_node_internal_name",
        ]:
            if current_space.get(field):
                update_payload[field] = current_space[field]

        result = self._patch(f"/api/2.0/data-rooms/{space_id}", update_payload)

        if sample_questions is not None:
            self.genie_update_sample_questions(space_id, sample_questions)

        return result

    def genie_delete(self, space_id: str) -> None:
        """Delete a Genie space."""
        self._delete(f"/api/2.0/data-rooms/{space_id}")

    def genie_list_questions(
        self, space_id: str, question_type: str = "SAMPLE_QUESTION"
    ) -> GenieListQuestionsResponseDict:
        """List curated questions for a Genie space."""
        return self._get(
            f"/api/2.0/data-rooms/{space_id}/curated-questions",
            params={"question_type": question_type},
        )

    def genie_list_instructions(
        self, space_id: str
    ) -> GenieListInstructionsResponseDict:
        """List all instructions for a Genie space."""
        return self._get(f"/api/2.0/data-rooms/{space_id}/instructions")

    def genie_update_sample_questions(
        self, space_id: str, questions: List[str]
    ) -> Dict[str, Any]:
        """Replace all sample questions for a Genie space.

        Args:
            space_id: The Genie space ID
            questions: New list of questions (replaces ALL existing)

        Returns:
            Batch action response
        """
        existing = self.genie_list_questions(space_id, question_type="SAMPLE_QUESTION")
        existing_ids = [
            q.get("curated_question_id") or q.get("id")
            for q in existing.get("curated_questions", [])
            if q.get("curated_question_id") or q.get("id")
        ]

        actions = []

        # Delete existing
        for question_id in existing_ids:
            actions.append(
                {"action_type": "DELETE", "curated_question_id": question_id}
            )

        # Create new
        for question_text in questions:
            actions.append(
                {
                    "action_type": "CREATE",
                    "curated_question": {
                        "data_room_id": space_id,
                        "question_text": question_text,
                        "question_type": "SAMPLE_QUESTION",
                    },
                }
            )

        return self._post(
            f"/api/2.0/data-rooms/{space_id}/curated-questions/batch-actions",
            {"actions": actions},
        )

    def genie_add_sample_questions_batch(
        self, space_id: str, questions: List[str]
    ) -> Dict[str, Any]:
        """Add multiple sample questions (without replacing existing)."""
        actions = [
            {
                "action_type": "CREATE",
                "curated_question": {
                    "data_space_id": space_id,
                    "question_text": q,
                    "question_type": "SAMPLE_QUESTION",
                },
            }
            for q in questions
        ]
        return self._post(
            f"/api/2.0/data-rooms/{space_id}/curated-questions/batch-actions",
            {"actions": actions},
        )

    def genie_add_curated_question(
        self,
        space_id: str,
        question_text: str,
        question_type: str,
        answer_text: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Add a curated question (low-level)."""
        curated_question = {
            "data_space_id": space_id,
            "question_text": question_text,
            "question_type": question_type,
            "is_deprecated": False,
        }
        if answer_text:
            curated_question["answer_text"] = answer_text

        return self._post(
            f"/api/2.0/data-rooms/{space_id}/curated-questions",
            {"curated_question": curated_question, "data_space_id": space_id},
        )

    def genie_add_sample_question(
        self, space_id: str, question_text: str
    ) -> Dict[str, Any]:
        """Add a single sample question."""
        return self.genie_add_curated_question(
            space_id, question_text, "SAMPLE_QUESTION"
        )

    def genie_add_instruction(
        self, space_id: str, title: str, content: str, instruction_type: str
    ) -> Dict[str, Any]:
        """Add an instruction (low-level)."""
        payload = {
            "title": title,
            "content": content,
            "instruction_type": instruction_type,
        }
        return self._post(f"/api/2.0/data-rooms/{space_id}/instructions", payload)

    def genie_add_text_instruction(
        self, space_id: str, content: str, title: str = "Notes"
    ) -> Dict[str, Any]:
        """Add general text instruction/notes."""
        return self.genie_add_instruction(space_id, title, content, "TEXT_INSTRUCTION")

    def genie_add_sql_instruction(
        self, space_id: str, title: str, content: str
    ) -> Dict[str, Any]:
        """Add a SQL query example instruction."""
        return self.genie_add_instruction(space_id, title, content, "SQL_INSTRUCTION")

    def genie_add_sql_function(
        self, space_id: str, function_name: str
    ) -> Dict[str, Any]:
        """Add a SQL function (certified answer)."""
        return self.genie_add_instruction(
            space_id, "SQL Function", function_name, "CERTIFIED_ANSWER"
        )

    def genie_add_sql_instructions_batch(
        self, space_id: str, sql_instructions: List[Dict[str, str]]
    ) -> List[Dict[str, Any]]:
        """Add multiple SQL instructions.

        Args:
            space_id: The Genie space ID
            sql_instructions: List of {'title': str, 'content': str}

        Returns:
            List of created instructions
        """
        results = []
        for instr in sql_instructions:
            try:
                result = self.genie_add_sql_instruction(
                    space_id, instr["title"], instr["content"]
                )
                results.append(result)
                logger.info(f"Added SQL instruction: {instr['title'][:50]}...")
            except Exception as e:
                logger.error(f"Failed to add SQL instruction '{instr['title']}': {e}")
        return results

    def genie_add_sql_functions_batch(
        self, space_id: str, function_names: List[str]
    ) -> List[Dict[str, Any]]:
        """Add multiple SQL functions (certified answers)."""
        results = []
        for func_name in function_names:
            try:
                result = self.genie_add_sql_function(space_id, func_name)
                results.append(result)
                logger.info(f"Added SQL function: {func_name}")
            except Exception as e:
                logger.error(f"Failed to add SQL function '{func_name}': {e}")
        return results

    def genie_add_benchmark(
        self, space_id: str, question_text: str, answer_text: str
    ) -> Dict[str, Any]:
        """Add a benchmark question with expected answer."""
        return self.genie_add_curated_question(
            space_id, question_text, "BENCHMARK", answer_text
        )

    def genie_add_benchmarks_batch(
        self, space_id: str, benchmarks: List[Dict[str, str]]
    ) -> List[Dict[str, Any]]:
        """Add multiple benchmarks.

        Args:
            space_id: The Genie space ID
            benchmarks: List of {'question_text': str, 'answer_text': str}

        Returns:
            List of created benchmarks
        """
        results = []
        for bm in benchmarks:
            try:
                result = self.genie_add_benchmark(
                    space_id, bm["question_text"], bm["answer_text"]
                )
                results.append(result)
                logger.info(f"Added benchmark: {bm['question_text'][:50]}...")
            except Exception as e:
                logger.error(
                    f"Failed to add benchmark '{bm['question_text'][:50]}...': {e}"
                )
        return results

    # ========================================================================
    # Low-level HTTP Wrappers
    # ========================================================================

    def _handle_response_error(
        self, response: requests.Response, method: str, path: str
    ) -> None:
        """Extract detailed error from response and raise."""
        if response.status_code >= 400:
            try:
                error_data = response.json()
                error_msg = error_data.get(
                    "message", error_data.get("error", str(error_data))
                )
                detailed_error = f"{method} {path} failed: {error_msg}"
                logger.error(
                    f"API Error: {detailed_error}\nFull response: {json.dumps(error_data, indent=2)}"
                )
                raise Exception(detailed_error)
            except ValueError:
                error_text = response.text
                detailed_error = f"{method} {path} failed with status {response.status_code}: {error_text}"
                logger.error(f"API Error: {detailed_error}")
                raise Exception(detailed_error)

    def _get(
        self, path: str, params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        headers = self.w.config.authenticate()
        url = f"{self.w.config.host}{path}"
        response = requests.get(url, headers=headers, params=params or {}, timeout=20)
        if response.status_code >= 400:
            self._handle_response_error(response, "GET", path)
        return response.json()

    def _post(
        self, path: str, body: Dict[str, Any], timeout: int = 300
    ) -> Dict[str, Any]:
        headers = self.w.config.authenticate()
        headers["Content-Type"] = "application/json"
        url = f"{self.w.config.host}{path}"
        response = requests.post(url, headers=headers, json=body, timeout=timeout)
        if response.status_code >= 400:
            self._handle_response_error(response, "POST", path)
        return response.json()

    def _patch(self, path: str, body: Dict[str, Any]) -> Dict[str, Any]:
        headers = self.w.config.authenticate()
        headers["Content-Type"] = "application/json"
        url = f"{self.w.config.host}{path}"
        response = requests.patch(url, headers=headers, json=body, timeout=20)
        if response.status_code >= 400:
            self._handle_response_error(response, "PATCH", path)
        return response.json()

    def _delete(self, path: str) -> Dict[str, Any]:
        headers = self.w.config.authenticate()
        url = f"{self.w.config.host}{path}"
        response = requests.delete(url, headers=headers, timeout=20)
        if response.status_code >= 400:
            self._handle_response_error(response, "DELETE", path)
        return response.json()

    # ========================================================================
    # Warehouse Auto-Detection (for Genie)
    # ========================================================================

    def get_best_warehouse_id(self) -> Optional[str]:
        """Get the best available SQL warehouse ID for Genie spaces.

        Prioritizes running warehouses, then starting ones, preferring smaller sizes.

        Returns:
            Warehouse ID string, or None if no warehouses available.
        """
        try:
            warehouses = list(self.w.warehouses.list())
            if not warehouses:
                return None

            # Sort by state (RUNNING first) and size (smaller first)
            size_order = [
                "2X-Small",
                "X-Small",
                "Small",
                "Medium",
                "Large",
                "X-Large",
                "2X-Large",
                "3X-Large",
                "4X-Large",
            ]

            def sort_key(wh):
                state_priority = (
                    0
                    if wh.state.value == "RUNNING"
                    else (1 if wh.state.value == "STARTING" else 2)
                )
                try:
                    size_priority = size_order.index(wh.cluster_size)
                except ValueError:
                    size_priority = 99
                return (state_priority, size_priority)

            warehouses_sorted = sorted(warehouses, key=sort_key)
            return warehouses_sorted[0].id if warehouses_sorted else None
        except Exception as e:
            logger.warning(f"Failed to get warehouses: {e}")
            return None

    # ========================================================================
    # Volume Scanning (for KA examples from PDF JSON files)
    # ========================================================================

    def scan_volume_for_examples(self, volume_path: str) -> List[Dict[str, Any]]:
        """Scan a volume folder for JSON files containing question/guideline pairs.

        These JSON files are typically created by the PDF generation tool and contain:
        - question: A question that can be answered by the document
        - guideline: How to evaluate if the answer is correct

        Args:
            volume_path: Path to the volume folder (e.g., "/Volumes/catalog/schema/volume/folder")

        Returns:
            List of dicts with 'question' and optionally 'guideline' keys
        """
        examples = []
        try:
            # List files in the volume
            files = list(self.w.files.list_directory_contents(volume_path))

            for file_info in files:
                if file_info.path and file_info.path.endswith(".json"):
                    try:
                        # Read the JSON file
                        response = self.w.files.download(file_info.path)
                        content = response.read().decode("utf-8")
                        data = json.loads(content)

                        # Extract question and guideline if present
                        if "question" in data:
                            example = {"question": data["question"]}
                            if "guideline" in data:
                                example["guideline"] = data["guideline"]
                            examples.append(example)
                            logger.debug(
                                f"Found example in {file_info.path}: {data['question'][:50]}..."
                            )
                    except Exception as e:
                        logger.warning(
                            f"Failed to read JSON file {file_info.path}: {e}"
                        )
                        continue

            logger.info(f"Found {len(examples)} examples in {volume_path}")
        except Exception as e:
            logger.warning(f"Failed to scan volume {volume_path} for examples: {e}")

        return examples


# ============================================================================
# TileExampleQueue - Background queue for adding examples to tiles
# ============================================================================


class TileExampleQueue:
    """Background queue for adding examples to tiles (KA/MAS) that aren't ready yet.

    This queue polls tiles periodically and attempts to add examples once
    the endpoint status is ONLINE.
    """

    def __init__(self, poll_interval: float = 30.0, max_attempts: int = 120):
        """Initialize the queue.

        Args:
            poll_interval: Seconds between status checks (default: 30)
            max_attempts: Maximum poll attempts before giving up (default: 120 = 1 hour)
        """
        self.queue: Dict[
            str, Tuple[AgentBricksManager, List[Dict[str, Any]], str, float, int]
        ] = {}
        self.lock = threading.Lock()
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.poll_interval = poll_interval
        self.max_attempts = max_attempts

    def enqueue(
        self,
        tile_id: str,
        manager: AgentBricksManager,
        questions: List[Dict[str, Any]],
        tile_type: str = "KA",
    ) -> None:
        """Add a tile and its questions to the processing queue.

        Args:
            tile_id: The tile ID
            manager: AgentBricksManager instance
            questions: List of question dictionaries
            tile_type: Type of tile ('KA' or 'MAS')
        """
        with self.lock:
            self.queue[tile_id] = (manager, questions, tile_type, time.time(), 0)
            logger.info(
                f"Enqueued {len(questions)} examples for {tile_type} {tile_id} "
                f"(will add when endpoint is ready)"
            )

        # Start background thread if not running
        if not self.running:
            self.start()

    def start(self) -> None:
        """Start the background processing thread."""
        if not self.running:
            self.running = True
            self.thread = threading.Thread(target=self._process_loop, daemon=True)
            self.thread.start()
            logger.info("Started tile example queue background processor")

    def stop(self) -> None:
        """Stop the background processing thread."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        logger.info("Stopped tile example queue background processor")

    def _process_loop(self) -> None:
        """Background loop that checks tile status and adds examples when ready."""
        while self.running:
            try:
                # Get snapshot of queue to process
                with self.lock:
                    items_to_process = list(self.queue.items())

                # Process each tile
                for tile_id, (
                    manager,
                    questions,
                    tile_type,
                    enqueue_time,
                    attempt_count,
                ) in items_to_process:
                    try:
                        # Check if max attempts exceeded
                        if attempt_count >= self.max_attempts:
                            elapsed_time = time.time() - enqueue_time
                            logger.error(
                                f"{tile_type} {tile_id} exceeded max attempts ({self.max_attempts}). "
                                f"Elapsed: {elapsed_time:.0f}s. Removing from queue. "
                                f"Failed to add {len(questions)} examples."
                            )
                            with self.lock:
                                self.queue.pop(tile_id, None)
                            continue

                        # Increment attempt count
                        with self.lock:
                            if tile_id in self.queue:
                                self.queue[tile_id] = (
                                    manager,
                                    questions,
                                    tile_type,
                                    enqueue_time,
                                    attempt_count + 1,
                                )

                        # Check endpoint status
                        if tile_type == "KA":
                            status = manager.ka_get_endpoint_status(tile_id)
                        elif tile_type == "MAS":
                            status = manager.mas_get_endpoint_status(tile_id)
                        else:
                            logger.error(f"Unknown tile type: {tile_type}")
                            with self.lock:
                                self.queue.pop(tile_id, None)
                            continue

                        logger.debug(
                            f"{tile_type} {tile_id} status: {status} (attempt {attempt_count + 1}/{self.max_attempts})"
                        )

                        # Add examples if ONLINE
                        if status == EndpointStatus.ONLINE.value:
                            logger.info(
                                f"{tile_type} {tile_id} is ONLINE, adding {len(questions)} examples..."
                            )

                            if tile_type == "KA":
                                created = manager.ka_add_examples_batch(
                                    tile_id, questions
                                )
                            else:
                                created = manager.mas_add_examples_batch(
                                    tile_id, questions
                                )

                            elapsed_time = time.time() - enqueue_time
                            logger.info(
                                f"Added {len(created)} examples to {tile_type} {tile_id} "
                                f"after {attempt_count + 1} attempts ({elapsed_time:.0f}s)"
                            )

                            with self.lock:
                                self.queue.pop(tile_id, None)

                    except Exception as e:
                        logger.error(f"Error processing {tile_type} {tile_id}: {e}")
                        with self.lock:
                            self.queue.pop(tile_id, None)

            except Exception as e:
                logger.error(f"Error in queue processor: {e}")

            time.sleep(self.poll_interval)


# Global singleton queue instance
_tile_example_queue: Optional[TileExampleQueue] = None
_queue_lock = threading.Lock()


def get_tile_example_queue() -> TileExampleQueue:
    """Get or create the global tile example queue instance."""
    global _tile_example_queue
    if _tile_example_queue is None:
        with _queue_lock:
            if _tile_example_queue is None:
                _tile_example_queue = TileExampleQueue()
    return _tile_example_queue
