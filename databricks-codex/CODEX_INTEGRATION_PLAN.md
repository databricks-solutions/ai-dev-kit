# Databricks Codex Integration Plugin

## Complete Implementation Plan for ai-dev-kit

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Product Requirements Document (PRD)](#2-product-requirements-document-prd)
3. [Technical Design](#3-technical-design)
4. [Implementation Plan](#4-implementation-plan)
5. [Non-Functional Requirements](#5-non-functional-requirements)
6. [Gap Analysis](#6-gap-analysis)
7. [Testing Strategy](#7-testing-strategy)
8. [Appendix: Reference Code Patterns](#8-appendix-reference-code-patterns)

---

## 1. Executive Summary

### Purpose

Build a comprehensive `databricks-codex` module that integrates OpenAI Codex CLI with the Databricks ecosystem, providing:

- **Python SDK** for programmatic Codex interaction
- **MCP Client** for bidirectional communication with Codex-as-MCP-server
- **Configuration Management** for unified Codex + Databricks setup
- **Session Management** for conversation persistence and forking
- **Complete Test Suite** with unit and integration tests

### What is Codex CLI?

OpenAI Codex CLI is a terminal-based coding agent that can read, modify, and execute code on your machine. Key characteristics:

- Built in **Rust** (95.8%) for performance
- Supports **MCP (Model Context Protocol)** for third-party tools
- Multiple **sandbox modes** for security (read-only, workspace-write, full-access)
- **Session persistence** with resume and fork capabilities
- Available on macOS, Linux, and Windows (experimental)

### Current State in ai-dev-kit

The `install.sh` and `install.ps1` scripts already configure Codex with the Databricks MCP server:

```toml
# ~/.codex/config.toml
[mcp_servers.databricks]
command = "/path/to/.venv/bin/python"
args = ["/path/to/databricks-mcp-server/run_server.py"]
```

This plan extends that integration with a full Python SDK.

---

## 2. Product Requirements Document (PRD)

### 2.1 Problem Statement

Developers using Codex CLI with Databricks need:

1. **Programmatic access** to Codex capabilities from Python workflows
2. **Unified authentication** bridging Databricks and Codex credentials
3. **Robust error handling** for long-running operations
4. **Session management** for complex multi-step tasks
5. **Testing infrastructure** to validate integrations

### 2.2 User Personas

| Persona | Description | Primary Use Case |
|---------|-------------|------------------|
| **Data Engineer** | Builds ETL pipelines on Databricks | Use Codex to generate Spark SQL, validate with Databricks tools |
| **ML Engineer** | Develops models with MLflow | Use Codex for code review, generate documentation |
| **Platform Engineer** | Maintains Databricks infrastructure | Automate Codex workflows in CI/CD pipelines |
| **Developer Advocate** | Creates demos and tutorials | Build interactive Databricks + AI experiences |

### 2.3 Functional Requirements

#### FR-1: Configuration Management

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-1.1 | Read/write `~/.codex/config.toml` programmatically | P0 |
| FR-1.2 | Support project-local `.codex/config.toml` | P1 |
| FR-1.3 | Configure Databricks MCP server with profile selection | P0 |
| FR-1.4 | Validate TOML syntax before writing | P1 |
| FR-1.5 | Atomic writes to prevent corruption | P0 |

#### FR-2: Authentication

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-2.1 | Check Codex authentication status | P0 |
| FR-2.2 | Support ChatGPT OAuth login | P1 |
| FR-2.3 | Support device code flow for headless environments | P1 |
| FR-2.4 | Support API key authentication | P1 |
| FR-2.5 | Inject Databricks credentials into Codex environment | P0 |

#### FR-3: Execution

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-3.1 | Execute `codex exec` synchronously with output capture | P0 |
| FR-3.2 | Execute `codex exec` asynchronously with timeout handling | P0 |
| FR-3.3 | Support all sandbox modes (read-only, workspace-write, full-access) | P0 |
| FR-3.4 | Pass environment variables to Codex subprocess | P0 |
| FR-3.5 | Track async operations with unique IDs | P1 |

#### FR-4: MCP Client

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-4.1 | Connect to Codex running as MCP server (stdio transport) | P0 |
| FR-4.2 | Connect via HTTP transport | P1 |
| FR-4.3 | List available tools from Codex MCP server | P0 |
| FR-4.4 | Call tools with argument passing | P0 |
| FR-4.5 | Handle JSON-RPC errors gracefully | P0 |

#### FR-5: Session Management

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-5.1 | List recent Codex sessions | P1 |
| FR-5.2 | Resume a previous session by ID | P1 |
| FR-5.3 | Fork a session into a new conversation | P2 |

### 2.4 Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Unit test coverage | > 80% | pytest-cov |
| Integration test pass rate | 100% | CI/CD pipeline |
| Codex exec latency overhead | < 500ms | Benchmark tests |
| Documentation completeness | 100% of public APIs | Manual review |

---

## 3. Technical Design

### 3.1 Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           databricks-codex Module                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐│
│  │   config    │  │    auth     │  │  executor   │  │     mcp_client      ││
│  │             │  │             │  │             │  │                     ││
│  │ - read()    │  │ - check()   │  │ - exec_sync │  │ - connect()         ││
│  │ - write()   │  │ - login()   │  │ - exec_async│  │ - list_tools()      ││
│  │ - configure │  │ - logout()  │  │ - get_op()  │  │ - call_tool()       ││
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────────┬──────────┘│
│         │                │                │                     │          │
│         └────────────────┴────────────────┴─────────────────────┘          │
│                                    │                                        │
│                           ┌────────▼────────┐                              │
│                           │     models      │                              │
│                           │                 │                              │
│                           │ - Enums         │                              │
│                           │ - TypedDicts    │                              │
│                           │ - Pydantic      │                              │
│                           └─────────────────┘                              │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     │ subprocess / MCP
                                     ▼
                           ┌─────────────────┐
                           │   Codex CLI     │
                           │                 │
                           │ codex exec      │
                           │ codex mcp-server│
                           └─────────────────┘
                                     │
                                     │ MCP Protocol
                                     ▼
                    ┌─────────────────────────────────┐
                    │     databricks-mcp-server       │
                    │                                 │
                    │ 50+ Databricks tools            │
                    │ - SQL execution                 │
                    │ - Unity Catalog                 │
                    │ - Jobs/Pipelines               │
                    │ - Genie Spaces                  │
                    └─────────────────────────────────┘
```

### 3.2 Directory Structure

```
databricks-codex/
├── databricks_codex/
│   ├── __init__.py                 # Package exports
│   ├── auth.py                     # Codex authentication utilities
│   ├── config.py                   # TOML configuration management
│   ├── executor.py                 # codex exec wrapper (sync/async)
│   ├── mcp_client.py               # Client for Codex-as-MCP-server
│   ├── session.py                  # Session management
│   ├── middleware.py               # Timeout/retry handling
│   └── models.py                   # Data models
├── tests/
│   ├── __init__.py
│   ├── conftest.py                 # Shared fixtures
│   ├── test_auth.py
│   ├── test_config.py
│   ├── test_executor.py
│   ├── test_mcp_client.py
│   ├── test_session.py
│   └── integration/
│       ├── __init__.py
│       ├── conftest.py
│       ├── test_codex_exec.py
│       └── test_mcp_server.py
├── docs/
│   └── API.md                      # API documentation
├── pyproject.toml
├── README.md
└── LICENSE
```

### 3.3 Component Specifications

#### 3.3.1 Configuration Manager (`config.py`)

```python
class MCPServerConfig(BaseModel):
    """MCP server entry in config.toml."""
    command: str
    args: List[str] = []
    env: Dict[str, str] = {}

class CodexConfig(BaseModel):
    """Full Codex configuration."""
    mcp_servers: Dict[str, MCPServerConfig] = {}

class CodexConfigManager:
    """Manage ~/.codex/config.toml and .codex/config.toml."""

    def __init__(self, config_path: Optional[Path] = None, scope: str = "global"):
        """Initialize with global or project scope."""

    def read(self) -> CodexConfig:
        """Read and parse TOML configuration."""

    def write(self, config: CodexConfig) -> None:
        """Write configuration atomically (temp file + rename)."""

    def configure_databricks_mcp(
        self,
        profile: str = "DEFAULT",
        python_path: Optional[str] = None,
        mcp_entry: Optional[str] = None,
    ) -> None:
        """Add/update Databricks MCP server configuration."""
```

**Key Pattern:** Atomic writes using temp file + `os.replace()` (from `manifest.py`).

#### 3.3.2 Authentication (`auth.py`)

```python
class CodexAuthMethod(Enum):
    CHATGPT_OAUTH = "chatgpt"
    DEVICE_CODE = "device"
    API_KEY = "api_key"
    NONE = "none"

@dataclass
class CodexAuthStatus:
    method: CodexAuthMethod
    is_authenticated: bool
    username: Optional[str] = None
    error: Optional[str] = None

def check_codex_auth() -> CodexAuthStatus:
    """Check if Codex CLI is authenticated."""

def login_codex(
    method: CodexAuthMethod = CodexAuthMethod.CHATGPT_OAUTH,
    api_key: Optional[str] = None,
) -> CodexAuthStatus:
    """Authenticate with Codex CLI."""

def logout_codex() -> bool:
    """Log out from Codex CLI."""

def get_combined_auth_context() -> Tuple[Optional[str], Optional[str]]:
    """Get Databricks host/token for injection into Codex environment."""
```

**Key Pattern:** Uses `databricks_tools_core.auth.get_workspace_client()` for Databricks credentials.

#### 3.3.3 Executor (`executor.py`)

```python
class SandboxMode(Enum):
    READ_ONLY = "read-only"
    WORKSPACE_WRITE = "workspace-write"
    FULL_ACCESS = "danger-full-access"

class ExecutionStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"

@dataclass
class ExecutionResult:
    status: ExecutionStatus
    stdout: str = ""
    stderr: str = ""
    exit_code: Optional[int] = None
    elapsed_seconds: float = 0.0
    operation_id: Optional[str] = None

class CodexExecOptions(BaseModel):
    prompt: str
    working_dir: Optional[Path] = None
    sandbox_mode: SandboxMode = SandboxMode.READ_ONLY
    model: Optional[str] = None
    timeout: int = 300
    env_vars: Dict[str, str] = {}
    databricks_profile: str = "DEFAULT"
    inject_databricks_env: bool = True

class CodexExecutor:
    """Execute Codex commands with Databricks context."""

    def exec_sync(self, options: CodexExecOptions) -> ExecutionResult:
        """Execute synchronously."""

    async def exec_async(
        self,
        options: CodexExecOptions,
        callback: Optional[Callable] = None,
    ) -> ExecutionResult:
        """Execute asynchronously with timeout handoff at 30s."""

    def get_operation(self, operation_id: str) -> Optional[ExecutionResult]:
        """Check status of async operation."""
```

**Key Pattern:** Async handoff at 30s threshold (from `databricks_tools.py`), prevents connection timeouts.

#### 3.3.4 MCP Client (`mcp_client.py`)

```python
class MCPClientConfig(BaseModel):
    # Stdio transport
    command: Optional[str] = None
    args: List[str] = []
    env: Dict[str, str] = {}
    # HTTP transport
    url: Optional[str] = None
    bearer_token_env_var: Optional[str] = None
    timeout: int = 120

@dataclass
class MCPToolInfo:
    name: str
    description: str
    input_schema: Dict[str, Any] = field(default_factory=dict)

class CodexMCPClient:
    """Client for Codex running as MCP server."""

    async def connect(self) -> None:
        """Establish connection (stdio or HTTP)."""

    async def disconnect(self) -> None:
        """Close connection."""

    async def list_tools(self) -> List[MCPToolInfo]:
        """List available tools."""

    async def call_tool(
        self,
        name: str,
        arguments: Dict[str, Any],
        timeout: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Call an MCP tool."""

    # Context manager support
    async def __aenter__(self): ...
    async def __aexit__(self, *args): ...
```

**Usage Example:**

```python
async with CodexMCPClient() as client:
    tools = await client.list_tools()
    result = await client.call_tool("generate_code", {"prompt": "Create a Python function"})
```

#### 3.3.5 Session Manager (`session.py`)

```python
@dataclass
class CodexSession:
    session_id: str
    created_at: datetime
    last_activity: Optional[datetime] = None
    project_dir: Optional[Path] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

class SessionManager:
    """Manage Codex CLI sessions."""

    def list_sessions(self, limit: int = 10) -> List[CodexSession]:
        """List recent sessions."""

    def resume_session(self, session_id: str) -> Optional[str]:
        """Resume a previous session."""

    def fork_session(
        self,
        session_id: str,
        new_prompt: Optional[str] = None,
    ) -> Optional[str]:
        """Fork an existing session."""
```

### 3.4 Authentication Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          Authentication Flow                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────┐                                                           │
│  │   User      │                                                           │
│  └──────┬──────┘                                                           │
│         │                                                                   │
│         ▼                                                                   │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                        Codex Authentication                          │   │
│  │                                                                      │   │
│  │  Option 1: ChatGPT OAuth (Browser)                                   │   │
│  │  $ codex login                                                       │   │
│  │  → Opens browser for ChatGPT sign-in                                 │   │
│  │                                                                      │   │
│  │  Option 2: Device Code (Headless)                                    │   │
│  │  $ codex login --device-auth                                         │   │
│  │  → Displays code to enter at https://...                             │   │
│  │                                                                      │   │
│  │  Option 3: API Key                                                   │   │
│  │  $ printenv OPENAI_API_KEY | codex login --with-api-key              │   │
│  │                                                                      │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│         │                                                                   │
│         ▼                                                                   │
│  ┌─────────────────┐                                                       │
│  │ ~/.codex/       │  (Codex credentials stored here)                      │
│  │ credentials     │                                                       │
│  └─────────────────┘                                                       │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      Databricks Integration                          │   │
│  │                                                                      │   │
│  │  Priority Order:                                                     │   │
│  │  1. DATABRICKS_HOST + DATABRICKS_TOKEN (environment)                 │   │
│  │  2. ~/.databrickscfg [PROFILE] (config file)                         │   │
│  │  3. OAuth M2M (Databricks Apps)                                      │   │
│  │                                                                      │   │
│  │  ┌─────────────────────┐        ┌─────────────────────────────────┐ │   │
│  │  │ get_workspace_      │  ───▶  │ CodexExecutor._build_env()      │ │   │
│  │  │ client()            │        │                                 │ │   │
│  │  │                     │        │ Injects:                        │ │   │
│  │  │ Returns: host,token │        │ - DATABRICKS_HOST               │ │   │
│  │  └─────────────────────┘        │ - DATABRICKS_TOKEN              │ │   │
│  │                                 │ - DATABRICKS_CONFIG_PROFILE     │ │   │
│  │                                 └─────────────────────────────────┘ │   │
│  │                                                                      │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3.5 Data Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            Data Flow: codex exec                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Python Application                                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                                                                      │   │
│  │  options = CodexExecOptions(                                         │   │
│  │      prompt="Create a Delta table from JSON files",                  │   │
│  │      sandbox_mode=SandboxMode.WORKSPACE_WRITE,                       │   │
│  │      inject_databricks_env=True,                                     │   │
│  │  )                                                                   │   │
│  │                                                                      │   │
│  │  result = executor.exec_sync(options)                                │   │
│  │                                                                      │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│         │                                                                   │
│         │ 1. Build command                                                  │
│         │ 2. Build environment (inject Databricks creds)                    │
│         │ 3. subprocess.run()                                               │
│         ▼                                                                   │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  codex exec                                                          │   │
│  │      --sandbox workspace-write                                       │   │
│  │      "Create a Delta table from JSON files"                          │   │
│  │                                                                      │   │
│  │  Environment:                                                        │   │
│  │      DATABRICKS_HOST=https://xxx.cloud.databricks.com                │   │
│  │      DATABRICKS_TOKEN=dapi...                                        │   │
│  │      DATABRICKS_CONFIG_PROFILE=DEFAULT                               │   │
│  │                                                                      │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│         │                                                                   │
│         │ 4. Codex processes prompt                                         │
│         │ 5. Uses MCP tools if configured                                   │
│         ▼                                                                   │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  databricks-mcp-server (via MCP protocol)                            │   │
│  │                                                                      │   │
│  │  Tools called:                                                       │   │
│  │  - execute_sql("CREATE TABLE...")                                    │   │
│  │  - list_volumes("/Volumes/...")                                      │   │
│  │                                                                      │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│         │                                                                   │
│         │ 6. Return stdout/stderr                                           │
│         ▼                                                                   │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  ExecutionResult(                                                    │   │
│  │      status=ExecutionStatus.COMPLETED,                               │   │
│  │      stdout="Created table `catalog.schema.my_table`...",            │   │
│  │      stderr="",                                                      │   │
│  │      exit_code=0,                                                    │   │
│  │      elapsed_seconds=12.5,                                           │   │
│  │  )                                                                   │   │
│  │                                                                      │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Implementation Plan

### Phase 1: Foundation (Week 1)

| Task | Description | Output |
|------|-------------|--------|
| 1.1 | Create package structure | `databricks-codex/` directory |
| 1.2 | Implement `models.py` | Enums, TypedDicts, Pydantic models |
| 1.3 | Implement `config.py` | TOML read/write with atomic writes |
| 1.4 | Write unit tests for config | `test_config.py` |

### Phase 2: Authentication (Week 2)

| Task | Description | Output |
|------|-------------|--------|
| 2.1 | Implement `auth.py` | Auth status, login, logout |
| 2.2 | Integrate with databricks-tools-core | `get_combined_auth_context()` |
| 2.3 | Write unit tests for auth | `test_auth.py` |

### Phase 3: Executor (Week 2-3)

| Task | Description | Output |
|------|-------------|--------|
| 3.1 | Implement `executor.py` sync | `exec_sync()` |
| 3.2 | Implement `executor.py` async | `exec_async()` with timeout handoff |
| 3.3 | Add operation tracking | `get_operation()` |
| 3.4 | Write unit tests | `test_executor.py` |

### Phase 4: MCP Client (Week 3-4)

| Task | Description | Output |
|------|-------------|--------|
| 4.1 | Implement stdio transport | `_send_stdio()` |
| 4.2 | Implement HTTP transport | `_send_http()` |
| 4.3 | Implement tool listing/calling | `list_tools()`, `call_tool()` |
| 4.4 | Write unit tests | `test_mcp_client.py` |

### Phase 5: Session Management (Week 4)

| Task | Description | Output |
|------|-------------|--------|
| 5.1 | Implement `session.py` | List, resume, fork |
| 5.2 | Write unit tests | `test_session.py` |

### Phase 6: Integration Testing (Week 5)

| Task | Description | Output |
|------|-------------|--------|
| 6.1 | Set up integration test fixtures | `integration/conftest.py` |
| 6.2 | Write Codex exec integration tests | `test_codex_exec.py` |
| 6.3 | Write MCP server integration tests | `test_mcp_server.py` |

### Phase 7: Documentation & Polish (Week 6)

| Task | Description | Output |
|------|-------------|--------|
| 7.1 | Write README.md | Installation, usage examples |
| 7.2 | Write API documentation | `docs/API.md` |
| 7.3 | Update `install.sh` | Add databricks-codex to installation |
| 7.4 | Create pyproject.toml | Package metadata and dependencies |

---

## 5. Non-Functional Requirements

### 5.1 Performance

| Metric | Target | Rationale |
|--------|--------|-----------|
| Codex exec startup overhead | < 500ms | Minimal wrapper overhead |
| MCP tool call latency | < 100ms | Excluding Codex processing time |
| Config read/write | < 50ms | Atomic writes via temp file |
| Memory footprint | < 100MB | Per executor instance |
| Async handoff threshold | 30s | Prevent API connection timeouts (50s limit) |

### 5.2 Security

| Requirement | Implementation |
|-------------|----------------|
| **No credential storage in config** | Databricks tokens via environment or databrickscfg profile only |
| **Default sandbox mode** | `read-only` by default, require explicit opt-in for write access |
| **Token injection safety** | Inject to subprocess only, never log credentials |
| **TOML validation** | Validate before writing to prevent injection attacks |
| **Subprocess isolation** | Use `subprocess.run()` with explicit environment, no shell=True |

### 5.3 Reliability

| Requirement | Implementation |
|-------------|----------------|
| **Atomic config writes** | Use temp file + `os.replace()` pattern from `manifest.py` |
| **Timeout handling** | Match `TimeoutHandlingMiddleware` pattern for graceful degradation |
| **Retry logic** | Exponential backoff for transient failures (network, rate limits) |
| **Cleanup on shutdown** | Close subprocess handles and MCP connections |
| **Graceful degradation** | Return structured errors, don't crash on Codex CLI issues |

### 5.4 Observability

| Requirement | Implementation |
|-------------|----------------|
| **Structured logging** | Use `logging.getLogger(__name__)` throughout |
| **Operation IDs** | UUID-based IDs for async operation tracking |
| **Metrics** | Execution times, success/failure rates |
| **Error context** | Include command, arguments, and environment in error messages |

### 5.5 Compatibility

| Requirement | Implementation |
|-------------|----------------|
| **Python versions** | 3.9+ (match databricks-tools-core) |
| **Codex CLI versions** | Version detection, warn on incompatible |
| **Platform support** | macOS, Linux; Windows experimental (WSL) |
| **MCP protocol** | Version negotiation in handshake |

---

## 6. Gap Analysis

### 6.1 Technical Gaps

| Gap | Impact | Severity | Mitigation |
|-----|--------|----------|------------|
| **No Python SDK for Codex** | Must shell out via subprocess | High | Design clean subprocess wrapper with proper error handling |
| **No MCP client library** | Must implement JSON-RPC from scratch | Medium | Use httpx for HTTP, asyncio.subprocess for stdio |
| **Undocumented output format** | Parsing may break on updates | Medium | Version detection, graceful degradation, structured output flags |
| **Session persistence unclear** | May lose session state | Low | Implement local session tracking as backup |
| **Codex not bundled** | External dependency | Medium | Clear installation docs, version checking, helpful error messages |

### 6.2 API Gaps

| Gap | Description | Workaround |
|-----|-------------|------------|
| **No `codex status` command** | Can't programmatically check auth | Use `codex --version` + try simple exec |
| **No streaming output** | Output only available after completion | Poll for long operations, use `--json` flag |
| **No cancel operation** | Can't stop running exec | Kill subprocess, implement timeout |

### 6.3 Documentation Gaps

| Gap | Description | Action Required |
|-----|-------------|-----------------|
| **Session format** | Session storage format not documented | Reverse engineer from ~/.codex directory |
| **MCP server output** | Response format for `codex mcp-server` | Test and document |
| **Error codes** | Exit code meanings not documented | Catalog through testing |

### 6.4 Dependencies and Risks

| Dependency | Risk Level | Mitigation |
|------------|------------|------------|
| **Codex CLI binary** | Medium | Must be installed separately; provide clear docs |
| **OpenAI API availability** | Low | Timeout handling, retry logic |
| **Databricks SDK** | Low | Pin version, integration tests |
| **MCP protocol stability** | Medium | Version negotiation, graceful degradation |

### 6.5 Future Enhancements

| Enhancement | Description | Priority |
|-------------|-------------|----------|
| **Databricks Apps integration** | Run Codex as a Databricks App with OAuth M2M | P2 |
| **Vector Search context** | Use Databricks Vector Search for prompt context | P2 |
| **Unity Catalog discovery** | Auto-discover schemas/tables for context | P2 |
| **MLflow tracing** | Trace Codex operations through MLflow | P3 |
| **Genie enhancement** | Use Codex to enhance Genie queries | P3 |

---

## 7. Testing Strategy

### 7.1 Unit Testing

**Framework:** pytest with pytest-asyncio

**Mocking Strategy:**

```python
# Mock subprocess.run for CLI calls
@pytest.fixture
def mock_subprocess_run():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="Success",
            stderr="",
        )
        yield mock_run

# Mock async calls
@pytest.fixture
def mock_async_exec():
    return AsyncMock(return_value=ExecutionResult(
        status=ExecutionStatus.COMPLETED,
        stdout="Done",
    ))
```

**Test Categories:**

| Category | Tests | Example |
|----------|-------|---------|
| Config | Read/write TOML, atomic writes | `test_write_and_read_roundtrip` |
| Auth | Status check, login flows | `test_check_auth_not_installed` |
| Executor | Sync/async exec, timeout | `test_exec_sync_success` |
| MCP | Connect, list, call tools | `test_list_tools` |
| Session | List, resume, fork | `test_list_sessions` |

### 7.2 Integration Testing

**Prerequisites:**
- Codex CLI installed and authenticated
- Databricks connection configured (profile or environment)

**Fixtures:**

```python
@pytest.fixture(scope="session")
def codex_authenticated():
    """Skip if Codex not authenticated."""
    status = check_codex_auth()
    if not status.is_authenticated:
        pytest.skip(f"Codex not authenticated: {status.error}")
    return status

@pytest.fixture(scope="session")
def databricks_connected():
    """Skip if Databricks not configured."""
    try:
        client = get_workspace_client()
        client.current_user.me()
        return client
    except Exception as e:
        pytest.skip(f"Databricks not configured: {e}")
```

**Test Categories:**

| Category | Tests | Example |
|----------|-------|---------|
| Codex Exec | Simple prompt, Databricks context | `test_exec_with_databricks_context` |
| Async Exec | Short operations, long with handoff | `test_exec_async_long_running` |
| MCP Server | Connect, list tools, call | `test_connect_to_codex_mcp` |

### 7.3 Test Coverage Targets

| Module | Target Coverage |
|--------|-----------------|
| `config.py` | 90% |
| `auth.py` | 85% |
| `executor.py` | 85% |
| `mcp_client.py` | 80% |
| `session.py` | 80% |
| **Overall** | **> 80%** |

---

## 8. Appendix: Reference Code Patterns

### 8.1 Atomic Write Pattern (from manifest.py)

```python
import tempfile
import os

def atomic_write(path: Path, data: dict) -> None:
    """Write file atomically to prevent corruption."""
    path.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(
        dir=path.parent,
        prefix=".tmp-",
        suffix=path.suffix,
    )
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
```

### 8.2 Timeout Middleware Pattern (from middleware.py)

```python
class TimeoutHandlingMiddleware:
    """Convert TimeoutError to structured result instead of exception."""

    async def on_call_tool(self, context, call_next):
        try:
            return await call_next(context)
        except TimeoutError as e:
            return ToolResult(
                content=[TextContent(
                    type="text",
                    text=json.dumps({
                        "timed_out": True,
                        "tool": context.tool_name,
                        "message": str(e),
                        "action_required": "Operation may still be in progress. Do NOT retry."
                    })
                )]
            )
```

### 8.3 Async Handoff Pattern (from databricks_tools.py)

```python
SAFE_EXECUTION_THRESHOLD = 30  # seconds

async def execute_with_handoff(func, *args, **kwargs):
    """Execute with async handoff for long operations."""
    start_time = time.time()
    ctx = copy_context()

    def run_in_context():
        return ctx.run(func, *args, **kwargs)

    loop = asyncio.get_event_loop()
    future = loop.run_in_executor(executor, run_in_context)

    HEARTBEAT_INTERVAL = 10

    while True:
        try:
            return await asyncio.wait_for(
                asyncio.shield(future),
                timeout=HEARTBEAT_INTERVAL,
            )
        except asyncio.TimeoutError:
            elapsed = time.time() - start_time
            if elapsed > SAFE_EXECUTION_THRESHOLD:
                # Hand off to background
                op_id = str(uuid.uuid4())[:8]
                threading.Thread(
                    target=lambda: track_completion(op_id, future),
                    daemon=True,
                ).start()
                return {"status": "running", "operation_id": op_id}
```

### 8.4 Manager Pattern (from agent_bricks/manager.py)

```python
class AgentBricksManager:
    """Unified manager for resource lifecycle."""

    def __init__(
        self,
        client: Optional[WorkspaceClient] = None,
        default_timeout_s: int = 600,
        default_poll_s: float = 2.0,
    ):
        self.w = client or get_workspace_client()
        self.default_timeout_s = default_timeout_s
        self.default_poll_s = default_poll_s

    def _get(self, path: str, params: Optional[Dict] = None) -> Dict:
        """GET with auth headers."""
        headers = self.w.config.authenticate()
        response = requests.get(
            f"{self.w.config.host}{path}",
            headers=headers,
            params=params or {},
            timeout=20,
        )
        if response.status_code >= 400:
            self._handle_response_error(response, "GET", path)
        return response.json()

    def wait_until_ready(self, resource_id: str, timeout_s: int) -> Dict:
        """Poll until resource is ready."""
        deadline = time.time() + timeout_s
        last_status = None

        while True:
            resource = self._get(f"/api/resource/{resource_id}")
            status = resource.get("status")

            if status != last_status:
                logger.info(f"Status: {last_status} -> {status}")
                last_status = status

            if status == "READY":
                return resource

            if time.time() >= deadline:
                raise TimeoutError(f"Not ready within {timeout_s}s")

            time.sleep(self.default_poll_s)
```

### 8.5 Unit Test with Mocks (from test_middleware.py)

```python
from unittest.mock import AsyncMock, MagicMock
import pytest

@pytest.fixture
def middleware():
    return TimeoutHandlingMiddleware()

def _make_context(tool_name="test_tool", arguments=None):
    ctx = MagicMock()
    ctx.message.name = tool_name
    ctx.message.arguments = arguments or {}
    return ctx

@pytest.mark.asyncio
async def test_timeout_returns_structured_result(middleware):
    """TimeoutError is caught and converted to structured JSON."""
    call_next = AsyncMock(side_effect=TimeoutError("Timed out"))
    ctx = _make_context(tool_name="slow_operation")

    result = await middleware.on_call_tool(ctx, call_next)

    assert result is not None
    payload = json.loads(result.content[0].text)
    assert payload["timed_out"] is True
    assert payload["tool"] == "slow_operation"
```

---

## Summary

This document provides a complete blueprint for implementing the `databricks-codex` integration plugin:

1. **PRD** defines what we're building and why
2. **Technical Design** specifies how each component works
3. **Implementation Plan** breaks work into weekly phases
4. **NFRs** establish quality standards
5. **Gap Analysis** identifies risks and mitigations
6. **Testing Strategy** ensures quality

**Next Steps:**
1. Review and approve this plan
2. Create the `databricks-codex/` directory structure
3. Begin Phase 1: Foundation implementation
