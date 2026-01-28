"""Thread-safe operation tracker for async tool execution.

When MCP tools take longer than a safe threshold, they return immediately
with an operation ID. The operation continues in the background and can
be polled via check_operation_status().

This keeps the Claude connection alive during long-running operations
by allowing frequent polling interactions instead of blocking calls.
"""

import threading
import time
import uuid
import logging
from dataclasses import dataclass, field
from typing import Any, Optional, Dict

logger = logging.getLogger(__name__)

# TTL for completed operations (1 hour)
OPERATION_TTL_SECONDS = 3600


@dataclass
class TrackedOperation:
    """Represents a background operation that can be polled for status."""

    operation_id: str
    tool_name: str
    args: dict
    status: str = "running"  # running, completed, failed
    result: Optional[Any] = None
    error: Optional[str] = None
    started_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None


# Thread-safe operation storage
_operations: Dict[str, TrackedOperation] = {}
_lock = threading.Lock()


def create_operation(tool_name: str, args: dict) -> str:
    """Create a new tracked operation.

    Args:
        tool_name: Name of the MCP tool being executed
        args: Arguments passed to the tool

    Returns:
        operation_id: Short unique ID for polling
    """
    op_id = str(uuid.uuid4())[:8]

    with _lock:
        # Clean up old operations before creating new one
        _cleanup_expired_operations()

        _operations[op_id] = TrackedOperation(
            operation_id=op_id,
            tool_name=tool_name,
            args=args,
        )

    logger.info(f"Created async operation {op_id} for tool {tool_name}")
    return op_id


def get_operation(op_id: str) -> Optional[TrackedOperation]:
    """Get an operation by ID.

    Args:
        op_id: The operation ID returned by create_operation

    Returns:
        TrackedOperation or None if not found
    """
    with _lock:
        return _operations.get(op_id)


def complete_operation(op_id: str, result: Any = None, error: str = None):
    """Mark an operation as completed or failed.

    Args:
        op_id: The operation ID
        result: The successful result (if no error)
        error: Error message (if failed)
    """
    with _lock:
        op = _operations.get(op_id)
        if op:
            op.status = "failed" if error else "completed"
            op.result = result
            op.error = error
            op.completed_at = time.time()
            logger.info(
                f"Operation {op_id} {op.status}: "
                f"{error if error else 'success'}"
            )


def list_operations(status: Optional[str] = None) -> list:
    """List all operations, optionally filtered by status.

    Args:
        status: Optional filter ('running', 'completed', 'failed')

    Returns:
        List of operation summaries
    """
    with _lock:
        ops = _operations.values()
        if status:
            ops = [op for op in ops if op.status == status]

        return [
            {
                "operation_id": op.operation_id,
                "tool_name": op.tool_name,
                "status": op.status,
                "started_at": op.started_at,
                "elapsed_seconds": time.time() - op.started_at,
            }
            for op in ops
        ]


def _cleanup_expired_operations():
    """Remove completed operations older than TTL.

    Called internally with lock already held.
    """
    now = time.time()
    expired = [
        op_id
        for op_id, op in _operations.items()
        if op.completed_at and (now - op.completed_at) > OPERATION_TTL_SECONDS
    ]

    for op_id in expired:
        del _operations[op_id]
        logger.debug(f"Cleaned up expired operation {op_id}")

    if expired:
        logger.info(f"Cleaned up {len(expired)} expired operations")
