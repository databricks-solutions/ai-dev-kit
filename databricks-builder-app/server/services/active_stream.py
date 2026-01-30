"""Active stream manager for async agent execution.

Handles background execution of Claude agent with event accumulation
and cursor-based pagination for polling.

Events are persisted to the database for session independence,
allowing users to reconnect after navigating away.
"""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Optional

logger = logging.getLogger(__name__)

# Batch size for persisting events to database
EVENT_PERSIST_BATCH_SIZE = 10
# Maximum time between database syncs (seconds)
EVENT_PERSIST_INTERVAL = 5.0


@dataclass
class StreamEvent:
    """A single event from the agent stream."""

    timestamp: float
    data: dict[str, Any]


@dataclass
class ActiveStream:
    """Manages a background agent execution with event accumulation.

    Events are stored in an append-only list for cursor-based retrieval.
    The stream can be cancelled, and cleanup happens automatically.
    Events are also persisted to the database for session independence.
    """

    execution_id: str
    conversation_id: str
    project_id: str
    user_email: str = ''  # For database persistence
    events: list[StreamEvent] = field(default_factory=list)
    is_complete: bool = False
    is_cancelled: bool = False
    error: str | None = None
    task: asyncio.Task | None = None
    persist_task: asyncio.Task | None = None
    created_at: float = field(default_factory=time.time)
    _pending_events: list[dict] = field(default_factory=list)
    _last_persist_time: float = field(default_factory=time.time)
    _persist_index: int = 0  # Track which events have been persisted

    def add_event(self, event_data: dict[str, Any]) -> None:
        """Add an event to the stream and queue for persistence."""
        event = StreamEvent(
            timestamp=time.time(),
            data=event_data,
        )
        self.events.append(event)
        # Queue event for database persistence
        self._pending_events.append({
            'timestamp': event.timestamp,
            **event_data,
        })

    def get_events_since(self, cursor: float = 0.0) -> tuple[list[dict[str, Any]], float]:
        """Get all events since the given cursor timestamp.

        Args:
            cursor: Timestamp to get events after (exclusive)

        Returns:
            Tuple of (events list, new cursor timestamp)
        """
        new_events = [
            e.data for e in self.events
            if e.timestamp > cursor
        ]

        # Return the timestamp of the last event as new cursor
        new_cursor = self.events[-1].timestamp if self.events else cursor
        return new_events, new_cursor

    def mark_complete(self) -> None:
        """Mark the stream as complete."""
        self.is_complete = True
        self.add_event({'type': 'stream.completed', 'is_error': False})

    def mark_error(self, error: str) -> None:
        """Mark the stream as failed with an error."""
        self.error = error
        self.is_complete = True
        self.add_event({'type': 'error', 'error': error})
        self.add_event({'type': 'stream.completed', 'is_error': True})

    def cancel(self) -> bool:
        """Cancel the stream if it's still running.

        Returns:
            True if cancellation was initiated, False if already complete/cancelled
        """
        if self.is_complete or self.is_cancelled:
            return False

        self.is_cancelled = True
        if self.task and not self.task.done():
            self.task.cancel()

        self.add_event({'type': 'stream.cancelled'})
        self.add_event({'type': 'stream.completed', 'is_error': False})
        self.is_complete = True
        return True

    def get_pending_events(self) -> list[dict]:
        """Get and clear pending events for database persistence."""
        events = self._pending_events.copy()
        self._pending_events.clear()
        self._last_persist_time = time.time()
        return events

    def should_persist(self) -> bool:
        """Check if events should be persisted now."""
        if not self._pending_events:
            return False
        if len(self._pending_events) >= EVENT_PERSIST_BATCH_SIZE:
            return True
        elapsed = time.time() - self._last_persist_time
        if elapsed >= EVENT_PERSIST_INTERVAL:
            return True
        return False


class ActiveStreamManager:
    """Manages multiple active streams with automatic cleanup."""

    # Streams older than this will be cleaned up (5 minutes)
    CLEANUP_THRESHOLD_SECONDS = 300

    def __init__(self):
        self._streams: dict[str, ActiveStream] = {}
        self._lock = asyncio.Lock()

    async def create_stream(
        self,
        project_id: str,
        conversation_id: str,
        user_email: str = '',
    ) -> ActiveStream:
        """Create a new active stream.

        Args:
            project_id: Project ID
            conversation_id: Conversation ID
            user_email: User email for database persistence

        Returns:
            New ActiveStream instance
        """
        execution_id = str(uuid.uuid4())

        stream = ActiveStream(
            execution_id=execution_id,
            conversation_id=conversation_id,
            project_id=project_id,
            user_email=user_email,
        )

        async with self._lock:
            self._streams[execution_id] = stream
            await self._cleanup_old_streams()

        # Persist to database for session independence
        if user_email:
            await self._persist_stream_to_db(stream)

        logger.info(
            f"Created active stream {execution_id} "
            f"for conversation {conversation_id}"
        )
        return stream

    async def _persist_stream_to_db(self, stream: ActiveStream) -> None:
        """Persist stream to database."""
        try:
            from .storage import ExecutionStorage
            storage = ExecutionStorage(
                stream.user_email,
                stream.project_id,
                stream.conversation_id
            )
            await storage.create(stream.execution_id)
            logger.debug(f"Persisted stream {stream.execution_id} to database")
        except Exception as e:
            logger.warning(f"Failed to persist stream to database: {e}")

    async def persist_events(self, stream: ActiveStream) -> None:
        """Persist pending events to database."""
        if not stream.user_email:
            return

        events = stream.get_pending_events()
        if not events:
            return

        try:
            from .storage import ExecutionStorage
            storage = ExecutionStorage(
                stream.user_email,
                stream.project_id,
                stream.conversation_id
            )
            await storage.add_events(stream.execution_id, events)
            logger.debug(
                f"Persisted {len(events)} events for "
                f"stream {stream.execution_id}"
            )
        except Exception as e:
            logger.warning(f"Failed to persist events to database: {e}")

    async def update_stream_status(
        self,
        stream: ActiveStream,
        status: str,
        error: Optional[str] = None,
    ) -> None:
        """Update stream status in database."""
        if not stream.user_email:
            return

        try:
            from .storage import ExecutionStorage
            storage = ExecutionStorage(
                stream.user_email,
                stream.project_id,
                stream.conversation_id
            )
            await storage.update_status(stream.execution_id, status, error)
            logger.debug(
                f"Updated stream {stream.execution_id} status to {status}"
            )
        except Exception as e:
            logger.warning(f"Failed to update stream status: {e}")

    async def get_stream(self, execution_id: str) -> ActiveStream | None:
        """Get a stream by execution ID."""
        async with self._lock:
            return self._streams.get(execution_id)

    async def remove_stream(self, execution_id: str) -> None:
        """Remove a stream from the manager."""
        async with self._lock:
            if execution_id in self._streams:
                del self._streams[execution_id]
                logger.info(f"Removed active stream {execution_id}")

    async def _cleanup_old_streams(self) -> None:
        """Remove streams older than the cleanup threshold."""
        now = time.time()
        to_remove = [
            eid for eid, stream in self._streams.items()
            if stream.is_complete and (now - stream.created_at) > self.CLEANUP_THRESHOLD_SECONDS
        ]

        for eid in to_remove:
            del self._streams[eid]
            logger.debug(f"Cleaned up old stream {eid}")

        if to_remove:
            logger.info(f"Cleaned up {len(to_remove)} old streams")

    async def start_stream(
        self,
        stream: ActiveStream,
        agent_coroutine: Callable[[], Coroutine[Any, Any, None]],
    ) -> None:
        """Start the agent execution in the background.

        Args:
            stream: The ActiveStream to populate with events
            agent_coroutine: Async function that yields events
        """
        manager = self  # Reference for nested function

        async def run_agent():
            try:
                await agent_coroutine()
            except asyncio.CancelledError:
                logger.info(f"Stream {stream.execution_id} was cancelled")
                if not stream.is_complete:
                    stream.is_cancelled = True
                    stream.is_complete = True
            except Exception as e:
                import traceback
                error_details = traceback.format_exc()
                logger.error(
                    f"Stream {stream.execution_id} error: "
                    f"{type(e).__name__}: {e}"
                )
                logger.error(
                    f"Stream {stream.execution_id} traceback:\n{error_details}"
                )
                if not stream.is_complete:
                    error_msg = f"{type(e).__name__}: {str(e)}"
                    if 'Stream closed' in str(e):
                        error_msg = (
                            f"Agent communication interrupted "
                            f"({type(e).__name__}): {str(e)}. "
                            f"Operations may have exceeded timeout."
                        )
                    stream.mark_error(error_msg)
            finally:
                # Final persist of any remaining events
                await manager.persist_events(stream)
                # Update final status
                if stream.is_cancelled:
                    await manager.update_stream_status(
                        stream, 'cancelled'
                    )
                elif stream.error:
                    await manager.update_stream_status(
                        stream, 'error', stream.error
                    )
                else:
                    await manager.update_stream_status(
                        stream, 'completed'
                    )

        async def persist_loop():
            """Periodically persist events to database."""
            while not stream.is_complete and not stream.is_cancelled:
                await asyncio.sleep(EVENT_PERSIST_INTERVAL)
                if stream.should_persist():
                    await manager.persist_events(stream)

        stream.task = asyncio.create_task(run_agent())
        # Start persistence loop if user_email is set
        if stream.user_email:
            stream.persist_task = asyncio.create_task(persist_loop())
        logger.info(f"Started agent task for stream {stream.execution_id}")


# Global singleton instance
_manager: ActiveStreamManager | None = None


def get_stream_manager() -> ActiveStreamManager:
    """Get the global ActiveStreamManager instance."""
    global _manager
    if _manager is None:
        _manager = ActiveStreamManager()
    return _manager
