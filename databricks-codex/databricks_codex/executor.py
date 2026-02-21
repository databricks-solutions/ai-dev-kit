"""Codex exec wrapper with Databricks context.

Provides Python SDK for running codex exec commands with proper
Databricks authentication and environment setup.
"""

import asyncio
import logging
import os
import subprocess
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from typing import Callable, Dict, List, Optional

from databricks_codex.auth import get_databricks_env
from databricks_codex.models import CodexExecOptions, ExecutionResult, ExecutionStatus, SandboxMode

logger = logging.getLogger(__name__)

# Threshold for switching to async mode (prevents connection timeouts)
SAFE_EXECUTION_THRESHOLD = 30


class CodexExecutor:
    """Execute Codex commands with Databricks context.

    Provides both synchronous and asynchronous execution patterns with
    timeout handling for long-running operations.

    Example:
        >>> executor = CodexExecutor()
        >>> options = CodexExecOptions(
        ...     prompt="List all files in current directory",
        ...     sandbox_mode=SandboxMode.READ_ONLY,
        ... )
        >>> result = executor.exec_sync(options)
        >>> print(result.stdout)
    """

    def __init__(
        self,
        default_timeout: int = 300,
        max_workers: int = 4,
    ):
        """Initialize executor.

        Args:
            default_timeout: Default timeout in seconds
            max_workers: Maximum worker threads for async operations
        """
        self.default_timeout = default_timeout
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._operations: Dict[str, ExecutionResult] = {}
        self._lock = threading.Lock()

    def exec_sync(self, options: CodexExecOptions) -> ExecutionResult:
        """Execute codex exec synchronously.

        Args:
            options: Execution options

        Returns:
            ExecutionResult with output and status

        Example:
            >>> result = executor.exec_sync(CodexExecOptions(prompt="echo hello"))
            >>> assert result.status == ExecutionStatus.COMPLETED
        """
        start_time = time.time()

        cmd = self._build_command(options)
        env = self._build_env(options)

        logger.info(f"Running codex exec: {' '.join(cmd[:5])}...")
        logger.debug(f"Full command: {cmd}")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=options.timeout or self.default_timeout,
                cwd=options.working_dir,
                env=env,
            )

            elapsed = time.time() - start_time

            status = ExecutionStatus.COMPLETED if result.returncode == 0 else ExecutionStatus.FAILED

            logger.info(f"Codex exec completed in {elapsed:.1f}s with status {status.value}")

            return ExecutionResult(
                status=status,
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.returncode,
                elapsed_seconds=elapsed,
            )

        except subprocess.TimeoutExpired as e:
            elapsed = time.time() - start_time
            logger.warning(f"Codex exec timed out after {elapsed:.1f}s")
            return ExecutionResult(
                status=ExecutionStatus.TIMEOUT,
                stdout=e.stdout or "" if hasattr(e, "stdout") else "",
                stderr=e.stderr or "" if hasattr(e, "stderr") else "",
                elapsed_seconds=elapsed,
            )
        except FileNotFoundError:
            elapsed = time.time() - start_time
            return ExecutionResult(
                status=ExecutionStatus.FAILED,
                stderr="Codex CLI not found. Install from: npm i -g @openai/codex",
                elapsed_seconds=elapsed,
            )
        except Exception as e:
            elapsed = time.time() - start_time
            logger.exception("Codex exec error")
            return ExecutionResult(
                status=ExecutionStatus.FAILED,
                stderr=str(e),
                elapsed_seconds=elapsed,
            )

    async def exec_async(
        self,
        options: CodexExecOptions,
        callback: Optional[Callable[[ExecutionResult], None]] = None,
    ) -> ExecutionResult:
        """Execute codex exec asynchronously with timeout handling.

        Uses async handoff pattern for long-running operations to prevent
        connection timeouts.

        Args:
            options: Execution options
            callback: Optional callback when execution completes

        Returns:
            ExecutionResult (may contain operation_id for async tracking)

        Example:
            >>> async def main():
            ...     result = await executor.exec_async(options)
            ...     if result.status == ExecutionStatus.RUNNING:
            ...         # Poll for completion
            ...         final = executor.get_operation(result.operation_id)
        """
        start_time = time.time()

        # Copy context for thread execution
        ctx = copy_context()

        def run_in_context():
            return ctx.run(self.exec_sync, options)

        # Run in executor with heartbeat pattern
        loop = asyncio.get_event_loop()
        future = loop.run_in_executor(self._executor, run_in_context)

        HEARTBEAT_INTERVAL = 10

        while True:
            try:
                result = await asyncio.wait_for(
                    asyncio.shield(future),
                    timeout=HEARTBEAT_INTERVAL,
                )
                if callback:
                    callback(result)
                return result

            except asyncio.TimeoutError:
                elapsed = time.time() - start_time
                logger.debug(f"Codex exec still running... ({elapsed:.0f}s elapsed)")

                # Switch to async mode if exceeding threshold
                if elapsed > SAFE_EXECUTION_THRESHOLD:
                    op_id = str(uuid.uuid4())[:8]

                    # Track operation
                    with self._lock:
                        self._operations[op_id] = ExecutionResult(
                            status=ExecutionStatus.RUNNING,
                            operation_id=op_id,
                            elapsed_seconds=elapsed,
                        )

                    # Background completion handler
                    def complete_background():
                        try:
                            result = future.result()
                            result.operation_id = op_id
                            with self._lock:
                                self._operations[op_id] = result
                            if callback:
                                callback(result)
                            logger.info(f"Operation {op_id} completed: {result.status.value}")
                        except Exception as e:
                            with self._lock:
                                self._operations[op_id] = ExecutionResult(
                                    status=ExecutionStatus.FAILED,
                                    stderr=str(e),
                                    operation_id=op_id,
                                )
                            logger.error(f"Operation {op_id} failed: {e}")

                    threading.Thread(
                        target=complete_background,
                        daemon=True,
                    ).start()

                    logger.info(f"Operation handed off to background: {op_id}")

                    return ExecutionResult(
                        status=ExecutionStatus.RUNNING,
                        operation_id=op_id,
                        elapsed_seconds=elapsed,
                    )

    def get_operation(self, operation_id: str) -> Optional[ExecutionResult]:
        """Get status of an async operation.

        Args:
            operation_id: Operation ID from exec_async

        Returns:
            ExecutionResult if found, None otherwise

        Example:
            >>> result = executor.get_operation("abc123")
            >>> if result and result.status == ExecutionStatus.COMPLETED:
            ...     print(result.stdout)
        """
        with self._lock:
            return self._operations.get(operation_id)

    def list_operations(self) -> Dict[str, ExecutionResult]:
        """List all tracked operations.

        Returns:
            Dictionary of operation_id -> ExecutionResult
        """
        with self._lock:
            return dict(self._operations)

    def clear_operation(self, operation_id: str) -> bool:
        """Clear a completed operation from tracking.

        Args:
            operation_id: Operation ID to clear

        Returns:
            True if cleared, False if not found
        """
        with self._lock:
            if operation_id in self._operations:
                del self._operations[operation_id]
                return True
            return False

    def _build_command(self, options: CodexExecOptions) -> List[str]:
        """Build the codex exec command."""
        cmd = ["codex", "exec"]

        # Sandbox mode
        if options.sandbox_mode != SandboxMode.READ_ONLY:
            cmd.extend(["--sandbox", options.sandbox_mode.value])

        # Model selection
        if options.model:
            cmd.extend(["--model", options.model])

        # Working directory
        if options.working_dir:
            cmd.extend(["--cd", str(options.working_dir)])

        # The prompt is the final positional argument
        cmd.append(options.prompt)

        return cmd

    def _build_env(self, options: CodexExecOptions) -> Dict[str, str]:
        """Build environment for execution."""
        env = os.environ.copy()

        # Inject Databricks credentials
        if options.inject_databricks_env:
            databricks_env = get_databricks_env(options.databricks_profile)
            env.update(databricks_env)

        # Add custom environment variables
        env.update(options.env_vars)

        return env

    def shutdown(self, wait: bool = True) -> None:
        """Shutdown the executor.

        Args:
            wait: Whether to wait for pending operations
        """
        self._executor.shutdown(wait=wait)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.shutdown()
