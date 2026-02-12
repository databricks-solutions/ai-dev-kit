"""Execute code blocks from skill responses to verify they work."""

import ast
import re
import time
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict, Any, Callable, Protocol


@dataclass
class ExecutionResult:
    """Result of code block execution."""

    success: bool
    output: str
    error: Optional[str] = None
    execution_time_ms: float = 0


@dataclass
class DatabricksExecutionConfig:
    """Configuration for Databricks code execution.

    By default, uses serverless compute. Only specify cluster_id if you
    explicitly need a specific cluster.
    """

    cluster_id: Optional[str] = None  # Only set if user explicitly specifies
    warehouse_id: Optional[str] = None  # Auto-detected via MCP if None
    use_serverless: bool = True  # Default to serverless compute
    context_id: Optional[str] = None  # Session persistence for reuse
    catalog: str = "main"
    schema: str = "skill_test"
    timeout: int = 120


@dataclass
class DatabricksExecutionResult(ExecutionResult):
    """Extended result with Databricks-specific metadata."""

    cluster_id: Optional[str] = None
    warehouse_id: Optional[str] = None
    context_id: Optional[str] = None  # For session reuse
    context_destroyed: bool = False
    execution_mode: str = "local"  # "databricks", "local", "dry_run"


@dataclass
class CodeBlock:
    """Extracted code block with metadata."""

    language: str
    code: str
    line_number: int


def extract_code_blocks(response: str) -> List[CodeBlock]:
    """Extract code blocks from markdown response."""
    pattern = r"```(\w+)\n(.*?)```"
    blocks = []

    for match in re.finditer(pattern, response, re.DOTALL):
        language = match.group(1).lower()
        code = match.group(2)
        line_number = response[: match.start()].count("\n") + 1
        blocks.append(CodeBlock(language, code, line_number))

    return blocks


# Databricks-specific imports that may not be available locally but are valid
DATABRICKS_IMPORTS = {
    "pyspark",
    "databricks",
    "mlflow",
    "delta",
    "dlt",
    "dbutils",
    "koalas",
    "pandas_on_spark",
}


def verify_python_syntax(code: str) -> Tuple[bool, Optional[str]]:
    """Verify Python code syntax without execution."""
    try:
        ast.parse(code)
        return True, None
    except SyntaxError as e:
        return False, f"Line {e.lineno}: {e.msg}"


def execute_python_block(code: str, timeout_seconds: int = 30, verify_imports: bool = True) -> ExecutionResult:
    """
    Execute Python code block.

    For safety, this verifies syntax and imports.
    Full execution requires sandbox environment.
    """
    start_time = time.time()

    # Verify syntax
    syntax_ok, syntax_error = verify_python_syntax(code)
    if not syntax_ok:
        return ExecutionResult(
            success=False,
            output="",
            error=f"Syntax error: {syntax_error}",
            execution_time_ms=(time.time() - start_time) * 1000,
        )

    # Verify imports resolve
    if verify_imports:
        try:
            tree = ast.parse(code)
            imports = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.append(alias.name.split(".")[0])
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imports.append(node.module.split(".")[0])

            for imp in imports:
                # Skip Databricks-specific imports that aren't available locally
                if imp in DATABRICKS_IMPORTS:
                    continue
                try:
                    __import__(imp)
                except ImportError as e:
                    return ExecutionResult(
                        success=False,
                        output="",
                        error=f"Import error: {e}",
                        execution_time_ms=(time.time() - start_time) * 1000,
                    )
        except Exception as e:
            return ExecutionResult(
                success=False,
                output="",
                error=f"Import analysis failed: {e}",
                execution_time_ms=(time.time() - start_time) * 1000,
            )

    return ExecutionResult(
        success=True,
        output="Syntax valid, imports resolved",
        error=None,
        execution_time_ms=(time.time() - start_time) * 1000,
    )


def verify_sql_structure(code: str) -> ExecutionResult:
    """Verify SQL code structure (cannot actually execute)."""
    issues = []

    # Check for valid SQL statements
    statements = [
        "SELECT", "CREATE", "INSERT", "UPDATE", "DELETE", "WITH", "MERGE",
        "ALTER", "DROP", "GRANT", "REVOKE", "SET", "SHOW", "DESCRIBE", "MATCH",
    ]
    has_statement = any(stmt in code.upper() for stmt in statements)
    if not has_statement:
        issues.append("No recognizable SQL statement found")

    # Check balanced constructs
    if code.count("(") != code.count(")"):
        issues.append("Unbalanced parentheses")

    if issues:
        return ExecutionResult(success=False, output="", error="; ".join(issues))

    return ExecutionResult(success=True, output="SQL structure valid", error=None)


def execute_code_blocks(response: str) -> Tuple[int, int, List[Dict[str, Any]]]:
    """
    Execute all code blocks in a response locally (syntax/import validation only).

    Returns: (total_blocks, passed_blocks, execution_details)
    """
    blocks = extract_code_blocks(response)
    details = []
    passed = 0

    for block in blocks:
        if block.language == "python":
            result = execute_python_block(block.code)
        elif block.language == "sql":
            result = verify_sql_structure(block.code)
        else:
            # Skip unknown languages
            continue

        details.append(
            {
                "language": block.language,
                "line": block.line_number,
                "success": result.success,
                "output": result.output,
                "error": result.error,
                "execution_time_ms": result.execution_time_ms,
            }
        )

        if result.success:
            passed += 1

    return len(blocks), passed, details


# =============================================================================
# Databricks Execution Functions (via MCP tools)
# =============================================================================


class MCPExecuteCommand(Protocol):
    """Protocol for MCP execute_databricks_command tool."""

    def __call__(
        self,
        code: str,
        cluster_id: Optional[str] = None,
        context_id: Optional[str] = None,
        language: str = "python",
        timeout: int = 120,
        destroy_context_on_completion: bool = False,
    ) -> Dict[str, Any]: ...


class MCPExecuteSQL(Protocol):
    """Protocol for MCP execute_sql tool."""

    def __call__(
        self,
        sql_query: str,
        warehouse_id: Optional[str] = None,
        catalog: Optional[str] = None,
        schema: Optional[str] = None,
        timeout: int = 180,
    ) -> List[Dict[str, Any]]: ...


class MCPGetBestWarehouse(Protocol):
    """Protocol for MCP get_best_warehouse tool."""

    def __call__(self) -> Optional[str]: ...


class MCPGetBestCluster(Protocol):
    """Protocol for MCP get_best_cluster tool."""

    def __call__(self) -> Dict[str, Any]: ...


def execute_python_on_databricks(
    code: str,
    config: DatabricksExecutionConfig,
    mcp_execute_command: MCPExecuteCommand,
    mcp_get_best_cluster: Optional[MCPGetBestCluster] = None,
) -> DatabricksExecutionResult:
    """
    Execute Python code on Databricks via MCP tools.

    Uses serverless compute by default. Only uses a cluster if explicitly
    specified in config or if serverless is unavailable.

    Args:
        code: Python code to execute
        config: Execution configuration
        mcp_execute_command: MCP tool for executing code on Databricks
        mcp_get_best_cluster: Optional MCP tool for auto-detecting cluster

    Returns:
        DatabricksExecutionResult with execution details
    """
    start_time = time.time()

    # First validate syntax locally
    syntax_ok, syntax_error = verify_python_syntax(code)
    if not syntax_ok:
        return DatabricksExecutionResult(
            success=False,
            output="",
            error=f"Syntax error: {syntax_error}",
            execution_time_ms=(time.time() - start_time) * 1000,
            execution_mode="local",
        )

    # Determine cluster to use (serverless is default, so cluster_id may be None)
    cluster_id = config.cluster_id
    if cluster_id is None and not config.use_serverless and mcp_get_best_cluster:
        # Only auto-detect cluster if not using serverless
        try:
            result = mcp_get_best_cluster()
            cluster_id = result.get("cluster_id")
        except Exception as e:
            return DatabricksExecutionResult(
                success=False,
                output="",
                error=f"Failed to find cluster: {e}",
                execution_time_ms=(time.time() - start_time) * 1000,
                execution_mode="local",
            )

    # Execute on Databricks
    try:
        result = mcp_execute_command(
            code=code,
            cluster_id=cluster_id,  # None means serverless
            context_id=config.context_id,
            language="python",
            timeout=config.timeout,
            destroy_context_on_completion=False,  # Keep context for reuse
        )

        success = result.get("success", False)
        output = result.get("output", "")
        error = result.get("error")
        context_id = result.get("context_id")
        actual_cluster_id = result.get("cluster_id")

        return DatabricksExecutionResult(
            success=success,
            output=output if success else "",
            error=error,
            execution_time_ms=(time.time() - start_time) * 1000,
            cluster_id=actual_cluster_id,
            context_id=context_id,
            context_destroyed=result.get("context_destroyed", False),
            execution_mode="databricks",
        )

    except Exception as e:
        return DatabricksExecutionResult(
            success=False,
            output="",
            error=f"Databricks execution failed: {e}",
            execution_time_ms=(time.time() - start_time) * 1000,
            execution_mode="local",
        )


def execute_sql_on_databricks(
    sql_code: str,
    config: DatabricksExecutionConfig,
    mcp_execute_sql: MCPExecuteSQL,
    mcp_get_best_warehouse: Optional[MCPGetBestWarehouse] = None,
) -> DatabricksExecutionResult:
    """
    Execute SQL code on Databricks via MCP tools.

    Auto-detects the best warehouse if not specified in config.

    Args:
        sql_code: SQL code to execute
        config: Execution configuration
        mcp_execute_sql: MCP tool for executing SQL
        mcp_get_best_warehouse: Optional MCP tool for auto-detecting warehouse

    Returns:
        DatabricksExecutionResult with execution details
    """
    start_time = time.time()

    # First validate SQL structure locally
    local_result = verify_sql_structure(sql_code)
    if not local_result.success:
        return DatabricksExecutionResult(
            success=False,
            output="",
            error=local_result.error,
            execution_time_ms=(time.time() - start_time) * 1000,
            execution_mode="local",
        )

    # Determine warehouse to use
    warehouse_id = config.warehouse_id
    if warehouse_id is None and mcp_get_best_warehouse:
        try:
            warehouse_id = mcp_get_best_warehouse()
        except Exception as e:
            return DatabricksExecutionResult(
                success=False,
                output="",
                error=f"Failed to find warehouse: {e}",
                execution_time_ms=(time.time() - start_time) * 1000,
                execution_mode="local",
            )

    # Execute on Databricks
    try:
        result = mcp_execute_sql(
            sql_query=sql_code,
            warehouse_id=warehouse_id,
            catalog=config.catalog,
            schema=config.schema,
            timeout=config.timeout,
        )

        # mcp_execute_sql returns list of rows on success
        output = str(result) if result else "Query executed successfully"

        return DatabricksExecutionResult(
            success=True,
            output=output,
            error=None,
            execution_time_ms=(time.time() - start_time) * 1000,
            warehouse_id=warehouse_id,
            execution_mode="databricks",
        )

    except Exception as e:
        error_msg = str(e)
        return DatabricksExecutionResult(
            success=False,
            output="",
            error=f"SQL execution failed: {error_msg}",
            execution_time_ms=(time.time() - start_time) * 1000,
            warehouse_id=warehouse_id,
            execution_mode="databricks",
        )


@dataclass
class CodeBlocksExecutionResult:
    """Result of executing multiple code blocks."""

    total_blocks: int
    passed_blocks: int
    details: List[Dict[str, Any]]
    context_id: Optional[str] = None  # For session reuse
    execution_mode: str = "local"


def execute_code_blocks_on_databricks(
    response: str,
    config: DatabricksExecutionConfig,
    mcp_execute_command: MCPExecuteCommand,
    mcp_execute_sql: MCPExecuteSQL,
    mcp_get_best_warehouse: Optional[MCPGetBestWarehouse] = None,
    mcp_get_best_cluster: Optional[MCPGetBestCluster] = None,
) -> CodeBlocksExecutionResult:
    """
    Execute all code blocks in a response on Databricks.

    Preserves execution context across Python blocks for state sharing.
    Uses serverless compute by default.

    Args:
        response: Markdown response containing code blocks
        config: Databricks execution configuration
        mcp_execute_command: MCP tool for Python execution
        mcp_execute_sql: MCP tool for SQL execution
        mcp_get_best_warehouse: Optional MCP tool for warehouse detection
        mcp_get_best_cluster: Optional MCP tool for cluster detection

    Returns:
        CodeBlocksExecutionResult with execution details
    """
    blocks = extract_code_blocks(response)
    details = []
    passed = 0
    current_context_id = config.context_id

    for block in blocks:
        if block.language == "python":
            # Update config with current context for session persistence
            block_config = DatabricksExecutionConfig(
                cluster_id=config.cluster_id,
                warehouse_id=config.warehouse_id,
                use_serverless=config.use_serverless,
                context_id=current_context_id,
                catalog=config.catalog,
                schema=config.schema,
                timeout=config.timeout,
            )

            result = execute_python_on_databricks(
                block.code,
                block_config,
                mcp_execute_command,
                mcp_get_best_cluster,
            )

            # Preserve context for next block
            if result.context_id:
                current_context_id = result.context_id

        elif block.language == "sql":
            result = execute_sql_on_databricks(
                block.code,
                config,
                mcp_execute_sql,
                mcp_get_best_warehouse,
            )
        else:
            # Skip unknown languages
            continue

        details.append(
            {
                "language": block.language,
                "line": block.line_number,
                "success": result.success,
                "output": result.output,
                "error": result.error,
                "execution_time_ms": result.execution_time_ms,
                "execution_mode": result.execution_mode,
                "cluster_id": result.cluster_id,
                "warehouse_id": result.warehouse_id,
                "context_id": result.context_id,
            }
        )

        if result.success:
            passed += 1

    return CodeBlocksExecutionResult(
        total_blocks=len(blocks),
        passed_blocks=passed,
        details=details,
        context_id=current_context_id,
        execution_mode="databricks" if any(d.get("execution_mode") == "databricks" for d in details) else "local",
    )
