"""Models for AI/BI Dashboard operations.

Defines dataclasses for dashboard deployment results.
"""

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class DashboardDeploymentResult:
    """Result from deploying a dashboard to Databricks."""

    success: bool = False
    status: str = ""  # 'created' or 'updated'
    dashboard_id: str | None = None
    path: str | None = None
    url: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "success": self.success,
            "status": self.status,
            "dashboard_id": self.dashboard_id,
            "path": self.path,
            "url": self.url,
            "error": self.error,
        }
