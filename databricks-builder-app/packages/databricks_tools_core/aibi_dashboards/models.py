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
    dashboard_id: Optional[str] = None
    path: Optional[str] = None
    url: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "success": self.success,
            "status": self.status,
            "dashboard_id": self.dashboard_id,
            "path": self.path,
            "url": self.url,
            "error": self.error,
        }
