"""Session management for Codex CLI.

Provides utilities for session persistence, resume, and fork
operations as supported by Codex CLI.
"""

import logging
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class CodexSession:
    """Represents a Codex CLI session."""

    session_id: str
    created_at: datetime
    last_activity: Optional[datetime] = None
    project_dir: Optional[Path] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class SessionManager:
    """Manage Codex CLI sessions.

    Provides utilities for:
    - Listing recent sessions
    - Resuming previous sessions
    - Forking sessions into new conversations

    Example:
        >>> manager = SessionManager()
        >>> sessions = manager.list_sessions()
        >>> if sessions:
        ...     manager.resume_session(sessions[0].session_id)
    """

    def __init__(self, session_dir: Optional[Path] = None):
        """Initialize session manager.

        Args:
            session_dir: Directory for session data (default: ~/.codex/sessions)
        """
        self.session_dir = session_dir or (Path.home() / ".codex" / "sessions")

    def list_sessions(self, limit: int = 10) -> List[CodexSession]:
        """List recent Codex sessions.

        Args:
            limit: Maximum sessions to return

        Returns:
            List of sessions, most recent first

        Example:
            >>> sessions = manager.list_sessions(limit=5)
            >>> for s in sessions:
            ...     print(f"{s.session_id}: {s.created_at}")
        """
        try:
            # Codex doesn't have a direct list command, try resume --list or similar
            result = subprocess.run(
                ["codex", "resume", "--last"],
                capture_output=True,
                text=True,
                timeout=30,
            )

            # Parse output to extract session info
            # Note: This is heuristic as Codex output format may vary
            sessions = self._parse_session_output(result.stdout)
            return sessions[:limit]

        except FileNotFoundError:
            logger.warning("Codex CLI not found")
            return []
        except subprocess.TimeoutExpired:
            logger.warning("Codex session list timed out")
            return []
        except Exception as e:
            logger.warning(f"Failed to list sessions: {e}")
            return []

    def get_last_session(self) -> Optional[CodexSession]:
        """Get the most recent session.

        Returns:
            Most recent CodexSession or None

        Example:
            >>> session = manager.get_last_session()
            >>> if session:
            ...     print(f"Last session: {session.session_id}")
        """
        sessions = self.list_sessions(limit=1)
        return sessions[0] if sessions else None

    def resume_session(
        self,
        session_id: Optional[str] = None,
        last: bool = False,
    ) -> Optional[str]:
        """Resume a previous session.

        Args:
            session_id: Session ID to resume (optional if last=True)
            last: Resume the most recent session

        Returns:
            Session ID if successful, None otherwise

        Example:
            >>> new_id = manager.resume_session(last=True)
            >>> # Or with specific ID
            >>> new_id = manager.resume_session("abc123")
        """
        try:
            cmd = ["codex", "resume"]

            if last:
                cmd.append("--last")
            elif session_id:
                cmd.append(session_id)
            else:
                logger.error("Must provide session_id or set last=True")
                return None

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0:
                # Extract session ID from output
                resumed_id = self._extract_session_id(result.stdout) or session_id
                logger.info(f"Resumed session: {resumed_id}")
                return resumed_id

            logger.warning(f"Failed to resume session: {result.stderr}")
            return None

        except FileNotFoundError:
            logger.error("Codex CLI not found")
            return None
        except subprocess.TimeoutExpired:
            logger.warning("Resume session timed out")
            return None
        except Exception as e:
            logger.error(f"Failed to resume session: {e}")
            return None

    def fork_session(
        self,
        session_id: str,
        new_prompt: Optional[str] = None,
    ) -> Optional[str]:
        """Fork an existing session into a new conversation.

        Args:
            session_id: Session to fork from
            new_prompt: Optional initial prompt for forked session

        Returns:
            New session ID if successful

        Example:
            >>> new_id = manager.fork_session(
            ...     "abc123",
            ...     new_prompt="Continue but focus on error handling"
            ... )
        """
        try:
            cmd = ["codex", "fork", session_id]

            if new_prompt:
                cmd.extend(["--prompt", new_prompt])

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0:
                new_id = self._extract_session_id(result.stdout)
                logger.info(f"Forked session {session_id} -> {new_id}")
                return new_id

            logger.warning(f"Failed to fork session: {result.stderr}")
            return None

        except FileNotFoundError:
            logger.error("Codex CLI not found")
            return None
        except subprocess.TimeoutExpired:
            logger.warning("Fork session timed out")
            return None
        except Exception as e:
            logger.error(f"Failed to fork session {session_id}: {e}")
            return None

    def session_exists(self, session_id: str) -> bool:
        """Check if a session exists.

        Args:
            session_id: Session ID to check

        Returns:
            True if session exists
        """
        # Try to get info about the session
        # This is a heuristic approach
        sessions = self.list_sessions(limit=100)
        return any(s.session_id == session_id for s in sessions)

    def _parse_session_output(self, output: str) -> List[CodexSession]:
        """Parse session information from Codex output.

        This is heuristic as Codex output format may vary.
        """
        sessions = []

        # Look for session ID patterns (typically UUID-like)
        # Format may be: "Session: abc123..." or "abc123-def456..."
        id_pattern = re.compile(r"([a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}|[a-f0-9]{8,})")

        for line in output.strip().split("\n"):
            line = line.strip()
            if not line:
                continue

            match = id_pattern.search(line)
            if match:
                session_id = match.group(1)
                sessions.append(
                    CodexSession(
                        session_id=session_id,
                        created_at=datetime.now(),  # Placeholder
                    )
                )

        return sessions

    def _extract_session_id(self, output: str) -> Optional[str]:
        """Extract session ID from Codex output."""
        # Look for UUID-like patterns
        id_pattern = re.compile(r"([a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}|[a-f0-9]{8,})")

        match = id_pattern.search(output)
        if match:
            return match.group(1)

        # Fallback: try to get last word/line
        lines = output.strip().split("\n")
        if lines:
            last_line = lines[-1].strip()
            words = last_line.split()
            if words:
                return words[-1]

        return None

    def clear_sessions(self, keep_last: int = 5) -> int:
        """Clear old sessions, keeping the most recent.

        Args:
            keep_last: Number of recent sessions to keep

        Returns:
            Number of sessions cleared

        Note: This may not be supported by Codex CLI directly.
        """
        # Codex may not have a clear command
        # This would need to clean up ~/.codex/sessions directory
        logger.warning("Session clearing not implemented - manual cleanup may be required")
        return 0
