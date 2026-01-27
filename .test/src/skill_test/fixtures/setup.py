"""Test fixture setup and teardown for Databricks test infrastructure."""
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Protocol
from pathlib import Path


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


class MCPUploadFile(Protocol):
    """Protocol for MCP upload_file tool."""
    def __call__(
        self,
        local_path: str,
        workspace_path: str,
        overwrite: bool = True,
    ) -> Dict[str, Any]: ...


class MCPUploadFolder(Protocol):
    """Protocol for MCP upload_folder tool."""
    def __call__(
        self,
        local_folder: str,
        workspace_folder: str,
        max_workers: int = 10,
        overwrite: bool = True,
    ) -> Dict[str, Any]: ...


class MCPGetBestWarehouse(Protocol):
    """Protocol for MCP get_best_warehouse tool."""
    def __call__(self) -> Optional[str]: ...


@dataclass
class FileMapping:
    """Mapping of local file to volume path."""
    local_path: str
    volume_path: str


@dataclass
class TableDefinition:
    """Definition for creating a test table."""
    name: str
    ddl: str  # CREATE TABLE statement or CTAS


@dataclass
class TestFixtureConfig:
    """Configuration for test fixtures.

    Defines the catalog, schema, volume, files, and tables needed
    for a test case.
    """
    catalog: str = "skill_test"
    schema: str = "test_schema"
    volume: str = "test_data"
    files: List[FileMapping] = field(default_factory=list)
    tables: List[TableDefinition] = field(default_factory=list)
    cleanup_after: bool = True  # Auto-cleanup after test
    warehouse_id: Optional[str] = None  # Auto-detected if None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TestFixtureConfig":
        """Create config from dictionary (e.g., from YAML)."""
        files = []
        for f in data.get("files", []):
            files.append(FileMapping(
                local_path=f.get("local_path", ""),
                volume_path=f.get("volume_path", ""),
            ))

        tables = []
        for t in data.get("tables", []):
            tables.append(TableDefinition(
                name=t.get("name", ""),
                ddl=t.get("ddl", ""),
            ))

        return cls(
            catalog=data.get("catalog", "skill_test"),
            schema=data.get("schema", "test_schema"),
            volume=data.get("volume", "test_data"),
            files=files,
            tables=tables,
            cleanup_after=data.get("cleanup_after", True),
            warehouse_id=data.get("warehouse_id"),
        )


@dataclass
class FixtureResult:
    """Result of fixture setup/teardown operation."""
    success: bool
    message: str
    error: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)


def setup_test_catalog(
    catalog: str,
    mcp_execute_sql: MCPExecuteSQL,
    mcp_get_best_warehouse: Optional[MCPGetBestWarehouse] = None,
    warehouse_id: Optional[str] = None,
) -> FixtureResult:
    """Create catalog if it doesn't exist.

    Args:
        catalog: Catalog name to create
        mcp_execute_sql: MCP tool for SQL execution
        mcp_get_best_warehouse: Optional MCP tool for warehouse detection
        warehouse_id: Optional warehouse ID (auto-detected if None)

    Returns:
        FixtureResult with operation status
    """
    if warehouse_id is None and mcp_get_best_warehouse:
        warehouse_id = mcp_get_best_warehouse()

    try:
        mcp_execute_sql(
            sql_query=f"CREATE CATALOG IF NOT EXISTS {catalog}",
            warehouse_id=warehouse_id,
            timeout=60,
        )
        return FixtureResult(
            success=True,
            message=f"Catalog '{catalog}' ready",
            details={"catalog": catalog}
        )
    except Exception as e:
        return FixtureResult(
            success=False,
            message=f"Failed to create catalog '{catalog}'",
            error=str(e),
            details={"catalog": catalog}
        )


def setup_test_schema(
    catalog: str,
    schema: str,
    mcp_execute_sql: MCPExecuteSQL,
    mcp_get_best_warehouse: Optional[MCPGetBestWarehouse] = None,
    warehouse_id: Optional[str] = None,
) -> FixtureResult:
    """Create schema if it doesn't exist.

    Args:
        catalog: Catalog name
        schema: Schema name to create
        mcp_execute_sql: MCP tool for SQL execution
        mcp_get_best_warehouse: Optional MCP tool for warehouse detection
        warehouse_id: Optional warehouse ID (auto-detected if None)

    Returns:
        FixtureResult with operation status
    """
    if warehouse_id is None and mcp_get_best_warehouse:
        warehouse_id = mcp_get_best_warehouse()

    try:
        mcp_execute_sql(
            sql_query=f"CREATE SCHEMA IF NOT EXISTS {catalog}.{schema}",
            warehouse_id=warehouse_id,
            timeout=60,
        )
        return FixtureResult(
            success=True,
            message=f"Schema '{catalog}.{schema}' ready",
            details={"catalog": catalog, "schema": schema}
        )
    except Exception as e:
        return FixtureResult(
            success=False,
            message=f"Failed to create schema '{catalog}.{schema}'",
            error=str(e),
            details={"catalog": catalog, "schema": schema}
        )


def setup_test_volume(
    catalog: str,
    schema: str,
    volume: str,
    mcp_execute_sql: MCPExecuteSQL,
    mcp_get_best_warehouse: Optional[MCPGetBestWarehouse] = None,
    warehouse_id: Optional[str] = None,
) -> FixtureResult:
    """Create volume for file storage.

    Args:
        catalog: Catalog name
        schema: Schema name
        volume: Volume name to create
        mcp_execute_sql: MCP tool for SQL execution
        mcp_get_best_warehouse: Optional MCP tool for warehouse detection
        warehouse_id: Optional warehouse ID (auto-detected if None)

    Returns:
        FixtureResult with operation status and volume path
    """
    if warehouse_id is None and mcp_get_best_warehouse:
        warehouse_id = mcp_get_best_warehouse()

    volume_path = f"/Volumes/{catalog}/{schema}/{volume}"

    try:
        mcp_execute_sql(
            sql_query=f"CREATE VOLUME IF NOT EXISTS {catalog}.{schema}.{volume}",
            warehouse_id=warehouse_id,
            timeout=60,
        )
        return FixtureResult(
            success=True,
            message=f"Volume '{volume_path}' ready",
            details={
                "catalog": catalog,
                "schema": schema,
                "volume": volume,
                "volume_path": volume_path
            }
        )
    except Exception as e:
        return FixtureResult(
            success=False,
            message=f"Failed to create volume '{volume_path}'",
            error=str(e),
            details={
                "catalog": catalog,
                "schema": schema,
                "volume": volume,
                "volume_path": volume_path
            }
        )


def upload_test_files(
    files: List[FileMapping],
    catalog: str,
    schema: str,
    volume: str,
    mcp_upload_file: MCPUploadFile,
    base_path: Optional[str] = None,
) -> FixtureResult:
    """Upload test files to UC volume.

    Args:
        files: List of FileMapping with local and volume paths
        catalog: Catalog name
        schema: Schema name
        volume: Volume name
        mcp_upload_file: MCP tool for file upload
        base_path: Optional base path for resolving relative local paths

    Returns:
        FixtureResult with upload status for all files
    """
    volume_base = f"/Volumes/{catalog}/{schema}/{volume}"
    uploaded = []
    failed = []

    for file_map in files:
        local_path = file_map.local_path
        if base_path and not Path(local_path).is_absolute():
            local_path = str(Path(base_path) / local_path)

        workspace_path = f"{volume_base}/{file_map.volume_path}"

        try:
            result = mcp_upload_file(
                local_path=local_path,
                workspace_path=workspace_path,
                overwrite=True,
            )
            if result.get("success", False):
                uploaded.append(workspace_path)
            else:
                failed.append({
                    "path": workspace_path,
                    "error": result.get("error", "Unknown error")
                })
        except Exception as e:
            failed.append({
                "path": workspace_path,
                "error": str(e)
            })

    success = len(failed) == 0
    return FixtureResult(
        success=success,
        message=f"Uploaded {len(uploaded)}/{len(files)} files",
        error=str(failed) if failed else None,
        details={
            "uploaded": uploaded,
            "failed": failed,
            "volume_path": volume_base
        }
    )


def create_test_table(
    table: TableDefinition,
    catalog: str,
    schema: str,
    mcp_execute_sql: MCPExecuteSQL,
    mcp_get_best_warehouse: Optional[MCPGetBestWarehouse] = None,
    warehouse_id: Optional[str] = None,
) -> FixtureResult:
    """Create a test table from DDL.

    Args:
        table: TableDefinition with name and DDL
        catalog: Catalog name
        schema: Schema name
        mcp_execute_sql: MCP tool for SQL execution
        mcp_get_best_warehouse: Optional MCP tool for warehouse detection
        warehouse_id: Optional warehouse ID (auto-detected if None)

    Returns:
        FixtureResult with table creation status
    """
    if warehouse_id is None and mcp_get_best_warehouse:
        warehouse_id = mcp_get_best_warehouse()

    full_name = f"{catalog}.{schema}.{table.name}"

    try:
        mcp_execute_sql(
            sql_query=table.ddl,
            warehouse_id=warehouse_id,
            catalog=catalog,
            schema=schema,
            timeout=120,
        )
        return FixtureResult(
            success=True,
            message=f"Table '{full_name}' created",
            details={"table": full_name, "ddl": table.ddl}
        )
    except Exception as e:
        return FixtureResult(
            success=False,
            message=f"Failed to create table '{full_name}'",
            error=str(e),
            details={"table": full_name, "ddl": table.ddl}
        )


def setup_fixtures(
    config: TestFixtureConfig,
    mcp_execute_sql: MCPExecuteSQL,
    mcp_upload_file: MCPUploadFile,
    mcp_get_best_warehouse: Optional[MCPGetBestWarehouse] = None,
    base_path: Optional[str] = None,
) -> FixtureResult:
    """Set up all test fixtures from configuration.

    Orchestrates the creation of catalog, schema, volume, file uploads,
    and table creation in the correct order.

    Args:
        config: TestFixtureConfig with all fixture definitions
        mcp_execute_sql: MCP tool for SQL execution
        mcp_upload_file: MCP tool for file upload
        mcp_get_best_warehouse: Optional MCP tool for warehouse detection
        base_path: Optional base path for resolving relative file paths

    Returns:
        FixtureResult with overall setup status
    """
    results = []
    warehouse_id = config.warehouse_id

    # Auto-detect warehouse if needed
    if warehouse_id is None and mcp_get_best_warehouse:
        warehouse_id = mcp_get_best_warehouse()

    # 1. Create catalog
    catalog_result = setup_test_catalog(
        config.catalog, mcp_execute_sql, warehouse_id=warehouse_id
    )
    results.append(("catalog", catalog_result))
    if not catalog_result.success:
        return FixtureResult(
            success=False,
            message="Fixture setup failed at catalog creation",
            error=catalog_result.error,
            details={"step": "catalog", "results": results}
        )

    # 2. Create schema
    schema_result = setup_test_schema(
        config.catalog, config.schema, mcp_execute_sql, warehouse_id=warehouse_id
    )
    results.append(("schema", schema_result))
    if not schema_result.success:
        return FixtureResult(
            success=False,
            message="Fixture setup failed at schema creation",
            error=schema_result.error,
            details={"step": "schema", "results": results}
        )

    # 3. Create volume (if files specified)
    if config.files:
        volume_result = setup_test_volume(
            config.catalog, config.schema, config.volume,
            mcp_execute_sql, warehouse_id=warehouse_id
        )
        results.append(("volume", volume_result))
        if not volume_result.success:
            return FixtureResult(
                success=False,
                message="Fixture setup failed at volume creation",
                error=volume_result.error,
                details={"step": "volume", "results": results}
            )

        # 4. Upload files
        upload_result = upload_test_files(
            config.files,
            config.catalog, config.schema, config.volume,
            mcp_upload_file, base_path
        )
        results.append(("files", upload_result))
        if not upload_result.success:
            return FixtureResult(
                success=False,
                message="Fixture setup failed at file upload",
                error=upload_result.error,
                details={"step": "files", "results": results}
            )

    # 5. Create tables
    for table in config.tables:
        table_result = create_test_table(
            table, config.catalog, config.schema,
            mcp_execute_sql, warehouse_id=warehouse_id
        )
        results.append((f"table:{table.name}", table_result))
        if not table_result.success:
            return FixtureResult(
                success=False,
                message=f"Fixture setup failed at table '{table.name}'",
                error=table_result.error,
                details={"step": f"table:{table.name}", "results": results}
            )

    volume_path = f"/Volumes/{config.catalog}/{config.schema}/{config.volume}"
    return FixtureResult(
        success=True,
        message="All fixtures created successfully",
        details={
            "catalog": config.catalog,
            "schema": config.schema,
            "volume": config.volume,
            "volume_path": volume_path,
            "files_uploaded": len(config.files),
            "tables_created": len(config.tables),
            "results": results
        }
    )


def teardown_fixtures(
    config: TestFixtureConfig,
    mcp_execute_sql: MCPExecuteSQL,
    mcp_get_best_warehouse: Optional[MCPGetBestWarehouse] = None,
    drop_schema: bool = True,
    drop_catalog: bool = False,
) -> FixtureResult:
    """Tear down test fixtures.

    Cleans up tables, volume, and optionally schema/catalog.

    Args:
        config: TestFixtureConfig with fixture definitions
        mcp_execute_sql: MCP tool for SQL execution
        mcp_get_best_warehouse: Optional MCP tool for warehouse detection
        drop_schema: If True, drop the schema (default: True)
        drop_catalog: If True, drop the catalog (default: False, dangerous)

    Returns:
        FixtureResult with teardown status
    """
    results = []
    warehouse_id = config.warehouse_id

    if warehouse_id is None and mcp_get_best_warehouse:
        warehouse_id = mcp_get_best_warehouse()

    # Drop tables first
    for table in config.tables:
        full_name = f"{config.catalog}.{config.schema}.{table.name}"
        try:
            mcp_execute_sql(
                sql_query=f"DROP TABLE IF EXISTS {full_name}",
                warehouse_id=warehouse_id,
                timeout=60,
            )
            results.append((f"drop_table:{table.name}", {"success": True}))
        except Exception as e:
            results.append((f"drop_table:{table.name}", {"success": False, "error": str(e)}))

    # Drop volume
    if config.files:
        try:
            mcp_execute_sql(
                sql_query=f"DROP VOLUME IF EXISTS {config.catalog}.{config.schema}.{config.volume}",
                warehouse_id=warehouse_id,
                timeout=60,
            )
            results.append(("drop_volume", {"success": True}))
        except Exception as e:
            results.append(("drop_volume", {"success": False, "error": str(e)}))

    # Drop schema
    if drop_schema:
        try:
            mcp_execute_sql(
                sql_query=f"DROP SCHEMA IF EXISTS {config.catalog}.{config.schema} CASCADE",
                warehouse_id=warehouse_id,
                timeout=60,
            )
            results.append(("drop_schema", {"success": True}))
        except Exception as e:
            results.append(("drop_schema", {"success": False, "error": str(e)}))

    # Drop catalog (dangerous, default off)
    if drop_catalog:
        try:
            mcp_execute_sql(
                sql_query=f"DROP CATALOG IF EXISTS {config.catalog} CASCADE",
                warehouse_id=warehouse_id,
                timeout=60,
            )
            results.append(("drop_catalog", {"success": True}))
        except Exception as e:
            results.append(("drop_catalog", {"success": False, "error": str(e)}))

    # Check if any failures
    failures = [r for r in results if not r[1].get("success", True)]
    success = len(failures) == 0

    return FixtureResult(
        success=success,
        message="Teardown completed" if success else f"Teardown completed with {len(failures)} failures",
        error=str(failures) if failures else None,
        details={"results": results}
    )
