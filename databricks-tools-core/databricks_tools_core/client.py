"""
Databricks REST API Client

Shared HTTP client for all Databricks API operations.
Uses Databricks SDK for authentication to support both PAT and OAuth.
"""
import os
from typing import Dict, Any, Optional, Callable
import requests

from databricks.sdk import WorkspaceClient


def _has_oauth_credentials() -> bool:
    """Check if OAuth credentials (SP) are configured in environment."""
    return bool(os.environ.get('DATABRICKS_CLIENT_ID') and os.environ.get('DATABRICKS_CLIENT_SECRET'))


class FilesAPI:
    """Databricks Files API for Unity Catalog Volumes."""

    def __init__(self, client: 'DatabricksClient'):
        self.client = client

    def create_directory(self, path: str) -> None:
        """
        Create directory in Volume (idempotent).

        Args:
            path: Volume path (e.g., "/Volumes/catalog/schema/volume/dir")

        Raises:
            requests.HTTPError: If request fails
        """
        self.client.put("/api/2.0/fs/directories", json={"path": path})

    def delete_directory(self, path: str, ignore_missing: bool = False) -> None:
        """
        Delete directory recursively.

        Args:
            path: Volume path to delete
            ignore_missing: If True, ignore 404 errors

        Raises:
            requests.HTTPError: If request fails (unless ignore_missing=True for 404)
        """
        try:
            self.client.delete(
                "/api/2.0/fs/directories",
                params={"path": path, "recursive": "true"}
            )
        except requests.HTTPError as e:
            if not ignore_missing or e.response.status_code != 404:
                raise

    def upload(self, path: str, data: bytes, overwrite: bool = False) -> None:
        """
        Upload file to Volume.

        Args:
            path: Volume file path (e.g., "/Volumes/catalog/schema/volume/file.parquet")
            data: File content as bytes
            overwrite: If True, overwrite existing file

        Raises:
            requests.HTTPError: If request fails
        """
        self.client.put(
            f"/api/2.0/fs/files{path}",
            data=data,
            params={"overwrite": str(overwrite).lower()}
        )


class DatabricksClient:
    """Client for making requests to Databricks REST APIs.

    Uses Databricks SDK for authentication to support both PAT and OAuth (SP credentials).
    """

    def __init__(
        self,
        host: Optional[str] = None,
        token: Optional[str] = None,
        profile: Optional[str] = None
    ):
        """
        Initialize Databricks client.

        Authentication priority (via Databricks SDK):
        1. If OAuth credentials exist in env, use explicit OAuth M2M auth (Databricks Apps)
        2. Explicit host/token parameters (PAT auth for development)
        3. DATABRICKS_HOST and DATABRICKS_TOKEN env vars
        4. Profile from ~/.databrickscfg

        Args:
            host: Databricks workspace URL
            token: Databricks personal access token (optional - uses SDK auth if not provided)
            profile: Profile name from ~/.databrickscfg (e.g., "ai-strat")
        """
        # In Databricks Apps (OAuth credentials in env), explicitly use OAuth M2M
        # This prevents the SDK from detecting other auth methods like PAT or config file
        if _has_oauth_credentials():
            oauth_host = host or os.environ.get('DATABRICKS_HOST', '')
            client_id = os.environ.get('DATABRICKS_CLIENT_ID', '')
            client_secret = os.environ.get('DATABRICKS_CLIENT_SECRET', '')

            # Explicitly configure OAuth M2M to prevent auth conflicts
            self._sdk_client = WorkspaceClient(
                host=oauth_host,
                client_id=client_id,
                client_secret=client_secret,
            )
        elif host and token:
            # Development mode: explicit PAT auth
            self._sdk_client = WorkspaceClient(host=host, token=token)
        elif host:
            # Host provided, use SDK default auth
            self._sdk_client = WorkspaceClient(host=host)
        elif profile:
            # Use config profile
            self._sdk_client = WorkspaceClient(profile=profile)
        else:
            # Use default SDK auth (env vars, config file)
            self._sdk_client = WorkspaceClient()

        # Get host from SDK config
        self.host = self._sdk_client.config.host.rstrip("/") if self._sdk_client.config.host else ""

        if not self.host:
            raise ValueError(
                "Databricks host must be provided via:\n"
                "  1. Constructor parameters (host)\n"
                "  2. Environment variables (DATABRICKS_HOST)\n"
                "  3. Config profile (profile parameter or DATABRICKS_CONFIG_PROFILE env var)"
            )

        # Store the authenticate function for getting fresh headers
        self._authenticate: Callable[[], dict] = self._sdk_client.config.authenticate

        # Initialize Files API
        self.files = FilesAPI(self)

    @property
    def headers(self) -> Dict[str, str]:
        """Get authentication headers using SDK's authenticate method.

        This generates fresh OAuth tokens when needed, avoiding token expiration issues.
        """
        return self._authenticate()

    def get(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Make GET request to Databricks API.

        Args:
            endpoint: API endpoint path (e.g., "/api/2.1/unity-catalog/catalogs")
            params: Query parameters

        Returns:
            JSON response as dictionary

        Raises:
            requests.HTTPError: If request fails
        """
        url = f"{self.host}{endpoint}"
        response = requests.get(url, headers=self.headers, params=params)
        response.raise_for_status()
        return response.json()

    def post(self, endpoint: str, json: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Make POST request to Databricks API.

        Args:
            endpoint: API endpoint path
            json: JSON request body

        Returns:
            JSON response as dictionary

        Raises:
            requests.HTTPError: If request fails
        """
        url = f"{self.host}{endpoint}"
        response = requests.post(url, headers=self.headers, json=json)
        response.raise_for_status()
        return response.json()

    def patch(self, endpoint: str, json: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Make PATCH request to Databricks API.

        Args:
            endpoint: API endpoint path
            json: JSON request body

        Returns:
            JSON response as dictionary

        Raises:
            requests.HTTPError: If request fails
        """
        url = f"{self.host}{endpoint}"
        response = requests.patch(url, headers=self.headers, json=json)
        response.raise_for_status()
        return response.json()

    def put(
        self,
        endpoint: str,
        json: Optional[Dict[str, Any]] = None,
        data: Optional[bytes] = None,
        params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Make PUT request to Databricks API.

        Args:
            endpoint: API endpoint path
            json: JSON request body (mutually exclusive with data)
            data: Binary data for file uploads (mutually exclusive with json)
            params: Query parameters

        Returns:
            JSON response as dictionary (or empty dict for 204 responses)

        Raises:
            requests.HTTPError: If request fails
        """
        url = f"{self.host}{endpoint}"

        if data is not None:
            headers = {**self.headers, "Content-Type": "application/octet-stream"}
            response = requests.put(url, data=data, params=params, headers=headers)
        elif json is not None:
            headers = {**self.headers, "Content-Type": "application/json"}
            response = requests.put(url, json=json, params=params, headers=headers)
        else:
            response = requests.put(url, params=params, headers=self.headers)

        response.raise_for_status()

        # Handle 204 No Content responses
        if response.status_code == 204:
            return {}

        return response.json()

    def delete(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Make DELETE request to Databricks API.

        Args:
            endpoint: API endpoint path
            params: Query parameters

        Returns:
            JSON response as dictionary (or empty dict for 204 responses)

        Raises:
            requests.HTTPError: If request fails
        """
        url = f"{self.host}{endpoint}"
        response = requests.delete(url, headers=self.headers, params=params)
        response.raise_for_status()

        # Handle 204 No Content responses
        if response.status_code == 204 or not response.content:
            return {}

        return response.json()
