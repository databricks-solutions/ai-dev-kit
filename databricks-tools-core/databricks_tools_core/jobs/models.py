"""
Jobs - Data Models and Enums

Data classes and enums for job operations.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Dict, Any


class JobStatus(Enum):
    """Job lifecycle status enum."""

    RUNNING = "RUNNING"
    QUEUED = "QUEUED"
    TERMINATED = "TERMINATED"
    TERMINATING = "TERMINATING"
    PENDING = "PENDING"
    SKIPPED = "SKIPPED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class RunLifecycleState(Enum):
    """Run lifecycle state enum."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    TERMINATING = "TERMINATING"
    TERMINATED = "TERMINATED"
    SKIPPED = "SKIPPED"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    QUEUED = "QUEUED"
    WAITING_FOR_RETRY = "WAITING_FOR_RETRY"
    BLOCKED = "BLOCKED"


class RunResultState(Enum):
    """Run result state enum."""

    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    TIMEDOUT = "TIMEDOUT"
    CANCELED = "CANCELED"
    EXCLUDED = "EXCLUDED"
    SUCCESS_WITH_FAILURES = "SUCCESS_WITH_FAILURES"
    UPSTREAM_FAILED = "UPSTREAM_FAILED"
    UPSTREAM_CANCELED = "UPSTREAM_CANCELED"


@dataclass
class JobRunResult:
    """
    Result from a job run operation with detailed status for LLM consumption.

    This dataclass provides comprehensive information about job runs
    to help LLMs understand what happened and take appropriate action.
    """

    # Job identification
    job_id: int
    run_id: int
    job_name: Optional[str] = None

    # Run status
    lifecycle_state: Optional[str] = None
    result_state: Optional[str] = None
    success: bool = False

    # Timing
    duration_seconds: Optional[float] = None
    start_time: Optional[int] = None  # epoch millis
    end_time: Optional[int] = None  # epoch millis

    # Run details
    run_page_url: Optional[str] = None
    state_message: Optional[str] = None

    # Error details (if failed)
    error_message: Optional[str] = None
    errors: List[Dict[str, Any]] = field(default_factory=list)

    # Human-readable status
    message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "job_id": self.job_id,
            "run_id": self.run_id,
            "job_name": self.job_name,
            "lifecycle_state": self.lifecycle_state,
            "result_state": self.result_state,
            "success": self.success,
            "duration_seconds": self.duration_seconds,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "run_page_url": self.run_page_url,
            "state_message": self.state_message,
            "error_message": self.error_message,
            "errors": self.errors,
            "message": self.message,
        }


class JobError(Exception):
    """Exception raised for job-related errors."""

    def __init__(
        self, message: str, job_id: Optional[int] = None, run_id: Optional[int] = None
    ):
        self.job_id = job_id
        self.run_id = run_id
        super().__init__(message)
