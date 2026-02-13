"""
Agent Bricks Models - Type definitions for Agent Bricks API responses.

Based on api_ka.proto and api_mas.proto definitions.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, TypedDict


# ============================================================================
# Enums
# ============================================================================


class TileType(Enum):
    """Tile types from the protobuf definition."""

    UNSPECIFIED = 0
    KIE = 1  # Knowledge Indexing Engine
    T2T = 2  # Text to Text
    KA = 3  # Knowledge Assistant
    MAO = 4  # Deprecated
    MAS = 5  # Supervisor Agent (formerly Multi-Agent Supervisor)


class EndpointStatus(Enum):
    """Vector Search Endpoint status values."""

    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"
    PROVISIONING = "PROVISIONING"
    NOT_READY = "NOT_READY"


class Permission(Enum):
    """Standard Databricks permissions for sharing resources."""

    CAN_READ = "CAN_READ"  # View/read access
    CAN_WRITE = "CAN_WRITE"  # Write/edit access
    CAN_RUN = "CAN_RUN"  # Execute/run access
    CAN_MANAGE = "CAN_MANAGE"  # Full management access including ACLs
    CAN_VIEW = "CAN_VIEW"  # View metadata only


# ============================================================================
# Data Classes
# ============================================================================


@dataclass(frozen=True)
class KAIds:
    """Knowledge Assistant identifiers."""

    tile_id: str
    name: str


@dataclass(frozen=True)
class GenieIds:
    """Genie Space identifiers."""

    space_id: str
    display_name: str


@dataclass(frozen=True)
class MASIds:
    """Supervisor Agent identifiers."""

    tile_id: str
    name: str


# ============================================================================
# TypedDict Definitions (from api_ka.proto and api_mas.proto)
# ============================================================================


class TileDict(TypedDict, total=False):
    """Tile metadata common to KA and MAS."""

    tile_id: str
    name: str
    description: Optional[str]
    instructions: Optional[str]
    tile_type: str
    created_timestamp_ms: int
    last_updated_timestamp_ms: int
    user_id: str


class KnowledgeSourceDict(TypedDict, total=False):
    """Knowledge source configuration for KA."""

    knowledge_source_id: str
    files_source: Dict[str, Any]  # Contains: name, type, files: {path: ...}


class KnowledgeAssistantStatusDict(TypedDict):
    """KA endpoint status."""

    endpoint_status: str  # ONLINE, OFFLINE, PROVISIONING, NOT_READY


class KnowledgeAssistantDict(TypedDict, total=False):
    """Complete Knowledge Assistant response."""

    tile: TileDict
    knowledge_sources: List[KnowledgeSourceDict]
    status: KnowledgeAssistantStatusDict


class KnowledgeAssistantResponseDict(TypedDict):
    """GET /knowledge-assistants/{tile_id} response."""

    knowledge_assistant: KnowledgeAssistantDict


class KnowledgeAssistantExampleDict(TypedDict, total=False):
    """KA example question."""

    example_id: str
    question: str
    guidelines: List[str]
    feedback_records: List[Dict[str, Any]]


class KnowledgeAssistantListExamplesResponseDict(TypedDict, total=False):
    """List examples response."""

    examples: List[KnowledgeAssistantExampleDict]
    tile_id: str
    next_page_token: Optional[str]


class BaseAgentDict(TypedDict, total=False):
    """Agent configuration for MAS."""

    name: str
    description: str
    agent_type: str  # genie, ka, app, etc.
    genie_space: Optional[Dict[str, str]]  # {id: ...}
    serving_endpoint: Optional[Dict[str, str]]  # {name: ...}
    app: Optional[Dict[str, str]]  # {name: ...}
    unity_catalog_function: Optional[Dict[str, Any]]


class MultiAgentSupervisorStatusDict(TypedDict):
    """MAS endpoint status."""

    endpoint_status: str  # ONLINE, OFFLINE, PROVISIONING, NOT_READY


class MultiAgentSupervisorDict(TypedDict, total=False):
    """Complete Supervisor Agent response."""

    tile: TileDict
    agents: List[BaseAgentDict]
    status: MultiAgentSupervisorStatusDict


class MultiAgentSupervisorResponseDict(TypedDict):
    """GET /multi-agent-supervisors/{tile_id} response."""

    multi_agent_supervisor: MultiAgentSupervisorDict


class MultiAgentSupervisorExampleDict(TypedDict, total=False):
    """MAS example question."""

    example_id: str
    question: str
    guidelines: List[str]
    feedback_records: List[Dict[str, Any]]


class MultiAgentSupervisorListExamplesResponseDict(TypedDict, total=False):
    """List examples response."""

    examples: List[MultiAgentSupervisorExampleDict]
    tile_id: str
    next_page_token: Optional[str]


class GenieSpaceDict(TypedDict, total=False):
    """Genie Space (Data Room) response.

    Note: Genie uses /api/2.0/data-rooms endpoint (not defined in KA/MAS protos).
    """

    space_id: str
    id: str  # Same as space_id
    display_name: str
    description: Optional[str]
    warehouse_id: str
    table_identifiers: List[str]
    run_as_type: str  # VIEWER, OWNER, etc.
    created_timestamp: int
    last_updated_timestamp: int
    user_id: str
    folder_node_internal_name: Optional[str]
    sample_questions: Optional[List[str]]


class CuratedQuestionDict(TypedDict, total=False):
    """Curated question for Genie space."""

    question_id: str
    data_space_id: str
    question_text: str
    question_type: str  # SAMPLE_QUESTION, BENCHMARK
    answer_text: Optional[str]
    is_deprecated: bool


class GenieListQuestionsResponseDict(TypedDict, total=False):
    """List curated questions response."""

    curated_questions: List[CuratedQuestionDict]


class InstructionDict(TypedDict, total=False):
    """Genie instruction (text, SQL, or certified answer)."""

    instruction_id: str
    title: str
    content: str
    instruction_type: str  # TEXT_INSTRUCTION, SQL_INSTRUCTION, CERTIFIED_ANSWER


class GenieListInstructionsResponseDict(TypedDict, total=False):
    """List instructions response."""

    instructions: List[InstructionDict]


class EvaluationRunDict(TypedDict, total=False):
    """Evaluation run metadata."""

    mlflow_run_id: str
    tile_id: str
    name: Optional[str]
    created_timestamp_ms: int
    last_updated_timestamp_ms: int


class ListEvaluationRunsResponseDict(TypedDict, total=False):
    """List evaluation runs response."""

    evaluation_runs: List[EvaluationRunDict]
    next_page_token: Optional[str]
