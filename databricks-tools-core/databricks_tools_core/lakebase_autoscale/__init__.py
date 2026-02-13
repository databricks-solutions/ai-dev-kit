"""
Lakebase Autoscaling Operations

Functions for managing Databricks Lakebase Autoscaling projects, branches,
computes (endpoints), and database credentials.
"""

from .projects import (
    create_project,
    get_project,
    list_projects,
    update_project,
    delete_project,
)
from .branches import (
    create_branch,
    get_branch,
    list_branches,
    update_branch,
    delete_branch,
)
from .computes import (
    create_endpoint,
    get_endpoint,
    list_endpoints,
    update_endpoint,
    delete_endpoint,
)
from .credentials import (
    generate_credential,
)

__all__ = [
    # Projects
    "create_project",
    "get_project",
    "list_projects",
    "update_project",
    "delete_project",
    # Branches
    "create_branch",
    "get_branch",
    "list_branches",
    "update_branch",
    "delete_branch",
    # Computes (Endpoints)
    "create_endpoint",
    "get_endpoint",
    "list_endpoints",
    "update_endpoint",
    "delete_endpoint",
    # Credentials
    "generate_credential",
]
