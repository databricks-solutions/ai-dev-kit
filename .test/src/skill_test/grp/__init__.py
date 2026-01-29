"""Generate-Review-Promote pipeline for ground truth creation."""
from .executor import (
    # Core types
    ExecutionResult,
    CodeBlock,
    # Databricks execution types
    DatabricksExecutionConfig,
    DatabricksExecutionResult,
    CodeBlocksExecutionResult,
    # Local execution functions
    extract_code_blocks,
    verify_python_syntax,
    execute_python_block,
    verify_sql_structure,
    execute_code_blocks,
    # Databricks execution functions
    execute_python_on_databricks,
    execute_sql_on_databricks,
    execute_code_blocks_on_databricks,
    # MCP protocols
    MCPExecuteCommand,
    MCPExecuteSQL,
    MCPGetBestWarehouse,
    MCPGetBestCluster,
)
from .diagnosis import (
    SkillSection,
    Diagnosis,
    find_skill_files,
    extract_sections,
    find_relevant_sections,
    analyze_failure,
)
from .pipeline import (
    GRPCandidate,
    GRPResult,
    ApprovalMetadata,
    generate_candidate,
    save_candidates,
    promote_approved,
    grp_interactive,
)

__all__ = [
    # Executor - Core types
    "ExecutionResult",
    "CodeBlock",
    # Executor - Databricks types
    "DatabricksExecutionConfig",
    "DatabricksExecutionResult",
    "CodeBlocksExecutionResult",
    # Executor - Local functions
    "extract_code_blocks",
    "verify_python_syntax",
    "execute_python_block",
    "verify_sql_structure",
    "execute_code_blocks",
    # Executor - Databricks functions
    "execute_python_on_databricks",
    "execute_sql_on_databricks",
    "execute_code_blocks_on_databricks",
    # Executor - MCP protocols
    "MCPExecuteCommand",
    "MCPExecuteSQL",
    "MCPGetBestWarehouse",
    "MCPGetBestCluster",
    # Diagnosis
    "SkillSection",
    "Diagnosis",
    "find_skill_files",
    "extract_sections",
    "find_relevant_sections",
    "analyze_failure",
    # Pipeline
    "GRPCandidate",
    "GRPResult",
    "ApprovalMetadata",
    "generate_candidate",
    "save_candidates",
    "promote_approved",
    "grp_interactive",
]
