"""
Lakebase Autoscaling Credential Operations

Functions for generating OAuth tokens for connecting to
Lakebase Autoscaling PostgreSQL databases.
"""

import logging
from typing import Any, Dict

from ..auth import get_workspace_client

logger = logging.getLogger(__name__)


def generate_credential(endpoint: str) -> Dict[str, Any]:
    """
    Generate an OAuth token for connecting to Lakebase Autoscaling databases.

    The token is valid for ~1 hour. Use it as the password in PostgreSQL
    connection strings with sslmode=require.

    Args:
        endpoint: Endpoint resource name to scope the credential to
            (e.g., "projects/my-app/branches/production/endpoints/ep-primary").

    Returns:
        Dictionary with:
        - token: OAuth token (use as password in connection string)
        - expiration_time: Token expiration time
        - message: Usage instructions

    Raises:
        Exception: If credential generation fails
    """
    client = get_workspace_client()

    try:
        cred = client.postgres.generate_database_credential(endpoint=endpoint)

        result: Dict[str, Any] = {}

        if hasattr(cred, "token") and cred.token:
            result["token"] = cred.token

        if hasattr(cred, "expiration_time") and cred.expiration_time:
            result["expiration_time"] = str(cred.expiration_time)

        result["message"] = "Token generated. Valid for ~1 hour. Use as password with sslmode=require."

        return result
    except Exception as e:
        raise Exception(f"Failed to generate Lakebase Autoscaling credentials: {str(e)}")
