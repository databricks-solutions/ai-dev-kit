"""Real integration test fixtures - no mocks.

These fixtures create actual files, directories, and check real configuration.
Use pytest.skip() when external services are not configured.
"""
import json
import os
import subprocess
from datetime import datetime
from pathlib import Path

import pytest
import yaml


@pytest.fixture(scope="session")
def databricks_configured():
    """Skip tests if Databricks not configured."""
    if not os.environ.get("DATABRICKS_HOST"):
        pytest.skip("DATABRICKS_HOST not set")
    if not os.environ.get("DATABRICKS_TOKEN"):
        pytest.skip("DATABRICKS_TOKEN not set")
    return True


@pytest.fixture(scope="session")
def mlflow_configured():
    """Skip tests if MLflow autolog not configured."""
    try:
        result = subprocess.run(
            ["mlflow", "autolog", "claude", "--status"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            pytest.skip("mlflow autolog claude command failed")
        if "enabled" not in result.stdout.lower() and "tracking_uri" not in result.stdout.lower():
            pytest.skip("MLflow autolog not enabled")
        return True
    except FileNotFoundError:
        pytest.skip("mlflow CLI not found")
    except subprocess.TimeoutExpired:
        pytest.skip("mlflow command timed out")


@pytest.fixture
def real_trace_file(tmp_path):
    """Create a real trace JSONL file with valid Claude Code format.

    This creates an actual file on disk that matches the Claude Code
    transcript format for parsing and evaluation.
    """
    trace_path = tmp_path / "session-integration-test.jsonl"

    base_time = datetime.now()
    session_id = "integration-test-session"

    entries = [
        # User message
        {
            "uuid": "int-test-user-1",
            "type": "user",
            "timestamp": base_time.isoformat(),
            "sessionId": session_id,
            "cwd": str(tmp_path),
            "message": {
                "role": "user",
                "content": "Create a streaming table for orders data"
            }
        },
        # Assistant response with tool calls
        {
            "uuid": "int-test-assistant-1",
            "type": "assistant",
            "timestamp": base_time.isoformat(),
            "sessionId": session_id,
            "parentUuid": "int-test-user-1",
            "message": {
                "model": "claude-3-5-sonnet-20241022",
                "role": "assistant",
                "usage": {
                    "input_tokens": 1500,
                    "output_tokens": 800,
                    "cache_creation_input_tokens": 200,
                    "cache_read_input_tokens": 100
                },
                "content": [
                    {"type": "text", "text": "I'll create the streaming table for orders."},
                    {
                        "type": "tool_use",
                        "id": "toolu_read_001",
                        "name": "Read",
                        "input": {"file_path": "/test/schema.sql"}
                    }
                ]
            }
        },
        # Tool result for Read
        {
            "uuid": "int-test-tool-result-1",
            "type": "user",
            "timestamp": base_time.isoformat(),
            "sessionId": session_id,
            "parentUuid": "int-test-assistant-1",
            "sourceToolAssistantUUID": "int-test-assistant-1",
            "message": {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_read_001",
                        "content": "-- Schema file contents\nCREATE TABLE orders (id INT, amount DECIMAL);"
                    }
                ]
            },
            "toolUseResult": {
                "type": "read",
                "filePath": "/test/schema.sql"
            }
        },
        # Second assistant response with Write
        {
            "uuid": "int-test-assistant-2",
            "type": "assistant",
            "timestamp": base_time.isoformat(),
            "sessionId": session_id,
            "parentUuid": "int-test-tool-result-1",
            "message": {
                "model": "claude-3-5-sonnet-20241022",
                "role": "assistant",
                "usage": {
                    "input_tokens": 1200,
                    "output_tokens": 600,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 300
                },
                "content": [
                    {"type": "text", "text": "Now I'll create the streaming table definition."},
                    {
                        "type": "tool_use",
                        "id": "toolu_write_001",
                        "name": "Write",
                        "input": {
                            "file_path": "/test/bronze_orders.sql",
                            "content": "CREATE STREAMING TABLE bronze_orders AS SELECT * FROM STREAM(orders);"
                        }
                    }
                ]
            }
        },
        # Tool result for Write
        {
            "uuid": "int-test-tool-result-2",
            "type": "user",
            "timestamp": base_time.isoformat(),
            "sessionId": session_id,
            "parentUuid": "int-test-assistant-2",
            "sourceToolAssistantUUID": "int-test-assistant-2",
            "message": {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_write_001",
                        "content": "File written successfully"
                    }
                ]
            },
            "toolUseResult": {
                "type": "create",
                "filePath": "/test/bronze_orders.sql"
            }
        },
        # Third assistant response with Bash
        {
            "uuid": "int-test-assistant-3",
            "type": "assistant",
            "timestamp": base_time.isoformat(),
            "sessionId": session_id,
            "parentUuid": "int-test-tool-result-2",
            "message": {
                "model": "claude-3-5-sonnet-20241022",
                "role": "assistant",
                "usage": {
                    "input_tokens": 1000,
                    "output_tokens": 400,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 400
                },
                "content": [
                    {"type": "text", "text": "Let me validate the SQL syntax."},
                    {
                        "type": "tool_use",
                        "id": "toolu_bash_001",
                        "name": "Bash",
                        "input": {"command": "cat /test/bronze_orders.sql"}
                    }
                ]
            }
        },
        # Tool result for Bash
        {
            "uuid": "int-test-tool-result-3",
            "type": "user",
            "timestamp": base_time.isoformat(),
            "sessionId": session_id,
            "parentUuid": "int-test-assistant-3",
            "sourceToolAssistantUUID": "int-test-assistant-3",
            "message": {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_bash_001",
                        "content": "CREATE STREAMING TABLE bronze_orders AS SELECT * FROM STREAM(orders);"
                    }
                ]
            }
        },
        # Fourth assistant with MCP Databricks tool
        {
            "uuid": "int-test-assistant-4",
            "type": "assistant",
            "timestamp": base_time.isoformat(),
            "sessionId": session_id,
            "parentUuid": "int-test-tool-result-3",
            "message": {
                "model": "claude-3-5-sonnet-20241022",
                "role": "assistant",
                "usage": {
                    "input_tokens": 800,
                    "output_tokens": 300,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 500
                },
                "content": [
                    {"type": "text", "text": "I'll execute the SQL on Databricks."},
                    {
                        "type": "tool_use",
                        "id": "toolu_mcp_001",
                        "name": "mcp__databricks__execute_sql",
                        "input": {"sql": "SELECT 1"}
                    }
                ]
            }
        },
        # Tool result for MCP
        {
            "uuid": "int-test-tool-result-4",
            "type": "user",
            "timestamp": base_time.isoformat(),
            "sessionId": session_id,
            "parentUuid": "int-test-assistant-4",
            "sourceToolAssistantUUID": "int-test-assistant-4",
            "message": {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_mcp_001",
                        "content": "[{\"1\": 1}]"
                    }
                ]
            }
        },
    ]

    with open(trace_path, 'w') as f:
        for entry in entries:
            f.write(json.dumps(entry) + '\n')

    return trace_path


@pytest.fixture
def real_skill_dir(tmp_path):
    """Create a real skill directory structure with manifest and test files.

    Creates:
    - skills/<skill_name>/manifest.yaml with trace_expectations
    - skills/<skill_name>/ground_truth.yaml
    - skills/<skill_name>/candidates.yaml with pending items
    """
    skills_dir = tmp_path / "skills"
    skill_dir = skills_dir / "integration-test-skill"
    skill_dir.mkdir(parents=True)

    # Real manifest.yaml with trace_expectations
    manifest = {
        "skill_name": "integration-test-skill",
        "description": "Test skill for integration tests",
        "triggers": ["create streaming table", "build pipeline"],
        "scorers": {
            "enabled": ["python_syntax", "sql_syntax"],
            "llm_scorers": ["Safety"],
            "default_guidelines": ["Response must be complete"],
            "trace_expectations": {
                "tool_limits": {
                    "Bash": 20,
                    "Read": 50,
                    "Write": 10
                },
                "token_budget": {
                    "max_total": 100000
                },
                "required_tools": ["Read"],
                "banned_tools": [],
                "expected_files": ["*.sql"],
                "category_limits": {
                    "bash": 25,
                    "mcp_databricks": 15
                }
            }
        },
        "quality_gates": {
            "syntax_valid": 1.0,
            "execution_success": 0.8
        }
    }
    manifest_path = skill_dir / "manifest.yaml"
    with open(manifest_path, 'w') as f:
        yaml.dump(manifest, f, default_flow_style=False, sort_keys=False)

    # Real ground_truth.yaml with existing test cases
    ground_truth = {
        "metadata": {
            "skill_name": "integration-test-skill",
            "version": "0.1.0",
            "created_at": datetime.now().isoformat(),
        },
        "test_cases": [
            {
                "id": "existing_test_001",
                "inputs": {"prompt": "Existing test prompt"},
                "outputs": {
                    "response": "```sql\nSELECT 1;\n```",
                    "execution_success": True
                },
                "expectations": {
                    "expected_facts": ["SQL query"],
                    "expected_patterns": [],
                    "guidelines": []
                },
                "metadata": {
                    "category": "happy_path",
                    "source": "manual"
                }
            }
        ]
    }
    gt_path = skill_dir / "ground_truth.yaml"
    with open(gt_path, 'w') as f:
        yaml.dump(ground_truth, f, default_flow_style=False, sort_keys=False)

    # Real candidates.yaml with pending items
    candidates = {
        "candidates": [
            {
                "id": "int_test_pending_001",
                "skill_name": "integration-test-skill",
                "status": "pending",
                "prompt": "Create a streaming table",
                "response": "```sql\nCREATE STREAMING TABLE orders AS SELECT * FROM STREAM(source);\n```",
                "execution_success": True,
                "code_blocks_found": 1,
                "code_blocks_passed": 1,
                "execution_details": [
                    {"success": True, "language": "sql", "line": 1, "error": None}
                ],
                "created_at": datetime.now().isoformat()
            },
            {
                "id": "int_test_pending_002",
                "skill_name": "integration-test-skill",
                "status": "pending",
                "prompt": "Create a materialized view",
                "response": "```sql\nCREATE MATERIALIZED VIEW mv_orders AS SELECT * FROM orders;\n```",
                "execution_success": True,
                "code_blocks_found": 1,
                "code_blocks_passed": 1,
                "execution_details": [
                    {"success": True, "language": "sql", "line": 1, "error": None}
                ],
                "created_at": datetime.now().isoformat()
            },
            {
                "id": "int_test_failed_001",
                "skill_name": "integration-test-skill",
                "status": "pending",
                "prompt": "Invalid prompt",
                "response": "```python\nthis is not valid python\n```",
                "execution_success": False,
                "code_blocks_found": 1,
                "code_blocks_passed": 0,
                "execution_details": [
                    {"success": False, "language": "python", "line": 1, "error": "SyntaxError"}
                ],
                "created_at": datetime.now().isoformat()
            }
        ]
    }
    candidates_path = skill_dir / "candidates.yaml"
    with open(candidates_path, 'w') as f:
        yaml.dump(candidates, f, default_flow_style=False, sort_keys=False)

    return skill_dir


@pytest.fixture
def real_trace_dir(tmp_path, real_trace_file):
    """Create a directory with multiple trace files.

    Uses the real_trace_file fixture and adds additional trace files.
    """
    trace_dir = tmp_path / "traces"
    trace_dir.mkdir()

    # Copy the base trace file
    import shutil
    shutil.copy(real_trace_file, trace_dir / "session-1.jsonl")

    # Create a second trace file with different content
    base_time = datetime.now()
    entries = [
        {
            "uuid": "trace2-user-1",
            "type": "user",
            "timestamp": base_time.isoformat(),
            "sessionId": "session-2",
            "cwd": str(tmp_path),
            "message": {"role": "user", "content": "Simple query"}
        },
        {
            "uuid": "trace2-assistant-1",
            "type": "assistant",
            "timestamp": base_time.isoformat(),
            "sessionId": "session-2",
            "message": {
                "model": "claude-3-5-sonnet-20241022",
                "role": "assistant",
                "usage": {
                    "input_tokens": 500,
                    "output_tokens": 200,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 0
                },
                "content": [
                    {"type": "text", "text": "Here is a simple query."},
                    {
                        "type": "tool_use",
                        "id": "toolu_read_002",
                        "name": "Read",
                        "input": {"file_path": "/test/query.sql"}
                    }
                ]
            }
        }
    ]

    trace_path = trace_dir / "session-2.jsonl"
    with open(trace_path, 'w') as f:
        for entry in entries:
            f.write(json.dumps(entry) + '\n')

    return trace_dir


@pytest.fixture
def cli_context(real_skill_dir):
    """Create a CLIContext pointing to the real skill directory."""
    import sys

    # Add the src path for imports
    repo_root = Path(__file__).resolve().parents[3]
    src_path = str(repo_root / "src")
    if src_path not in sys.path:
        sys.path.insert(0, src_path)

    from skill_test.cli.commands import CLIContext

    # base_path should point to the skills directory
    return CLIContext(base_path=real_skill_dir.parent)


@pytest.fixture
def repo_root():
    """Get the repository root path."""
    current = Path(__file__).resolve()
    while current != current.parent:
        if (current / ".test" / "src").exists():
            return current
        if current.name == ".test":
            return current.parent
        current = current.parent
    raise RuntimeError("Could not find repo root")
