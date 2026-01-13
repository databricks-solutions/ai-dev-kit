"""
App Health Checker
Checks if Databricks app is healthy via SDK + HTTP. Auto-redeploys if unhealthy.

Authentication modes:
1. M2M (for jobs): Set DATABRICKS_CLIENT_ID and DATABRICKS_CLIENT_SECRET env vars
2. U2M (interactive): Run `databricks auth login --host <workspace-url>` first
"""

import json
import os
import time
import requests
from pathlib import Path
from databricks.sdk import WorkspaceClient

# Configuration
APP_NAME = "dbdemos-generator"
HTTP_TIMEOUT = 20


def get_oauth_token_m2m(host: str) -> str:
    """Get OAuth token using M2M (service principal) credentials.

    Requires DATABRICKS_CLIENT_ID and DATABRICKS_CLIENT_SECRET env vars.
    Token is valid for 1 hour - refresh as needed.
    """
    client_id = os.environ.get("DATABRICKS_CLIENT_ID")
    client_secret = os.environ.get("DATABRICKS_CLIENT_SECRET")

    if not client_id or not client_secret:
        return None  # Fall back to U2M

    response = requests.post(
        f"{host}/oidc/v1/token",
        auth=(client_id, client_secret),
        data={"grant_type": "client_credentials", "scope": "all-apis"},
    )

    if response.status_code != 200:
        raise Exception(f"M2M OAuth failed: {response.text}")

    return response.json()["access_token"]


def get_oauth_token_u2m(host: str) -> str:
    """Get OAuth token using U2M (user) cached credentials.

    Requires prior `databricks auth login --host <workspace-url>`.
    """
    token_cache_path = Path.home() / ".databricks" / "token-cache.json"

    if not token_cache_path.exists():
        raise Exception(
            f"No OAuth token cache found. Run: databricks auth login --host {host}"
        )

    with open(token_cache_path) as f:
        cache = json.load(f)

    if host not in cache.get("tokens", {}):
        raise Exception(
            f"No cached token for {host}. Run: databricks auth login --host {host}"
        )

    token_data = cache["tokens"][host]
    refresh_token = token_data.get("refresh_token")

    if not refresh_token:
        raise Exception(
            f"No refresh token for {host}. Run: databricks auth login --host {host}"
        )

    # Refresh the token
    response = requests.post(
        f"{host}/oidc/v1/token",
        data={
            "client_id": "databricks-cli",
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "scope": "all-apis offline_access",
        },
    )

    if response.status_code != 200:
        raise Exception(
            f"Failed to refresh OAuth token: {response.text}. Run: databricks auth login --host {host}"
        )

    return response.json()["access_token"]


def get_oauth_token(host: str) -> str:
    """Get OAuth token - tries M2M first (for jobs), falls back to U2M (interactive)."""
    # Try M2M first (service principal - for jobs)
    token = get_oauth_token_m2m(host)
    if token:
        print("🔑 Using M2M OAuth (service principal)")
        return token

    # Fall back to U2M (user - interactive)
    print("🔑 Using U2M OAuth (user credentials)")
    return get_oauth_token_u2m(host)


def check_and_fix_app(app_name: str, w: WorkspaceClient, timeout: int = 20):
    """Check app health via SDK + HTTP. Auto-redeploy if unhealthy."""

    try:
        # Get app from Databricks
        app = w.apps.get(app_name)

        # Check SDK status
        compute_ok = app.compute_status and app.compute_status.state.value == "ACTIVE"
        app_ok = app.app_status and app.app_status.state.value == "RUNNING"

        print(
            f"📊 SDK Status - Compute: {app.compute_status.state.value if app.compute_status else 'N/A'}, "
            f"App: {app.app_status.state.value if app.app_status else 'N/A'}"
        )

        if not (compute_ok and app_ok):
            compute_state = (
                app.compute_status.state.value if app.compute_status else "UNKNOWN"
            )
            app_state = app.app_status.state.value if app.app_status else "UNKNOWN"
            print(f"❌ App unhealthy - Compute: {compute_state}, App: {app_state}")
            print("🔄 Redeploying...")
            w.apps.start(app_name)
            raise Exception(f"App {app_name} was unhealthy. Redeployed.")

        # Check HTTP with OAuth token (required for Databricks Apps)
        if app.url:
            # Get OAuth token (PAT doesn't work for Apps)
            oauth_token = get_oauth_token(w.config.host)
            headers = {"Authorization": f"Bearer {oauth_token}"}

            # Test the app's user endpoint (confirms auth and app responsiveness)
            health_url = app.url.rstrip("/") + "/api/user/me"
            print(f"🔍 Testing HTTP: {health_url}")
            start = time.time()

            resp = requests.get(health_url, timeout=timeout, headers=headers)
            elapsed = round(time.time() - start, 2)

            # Show response details
            print(f"📄 Status: {resp.status_code}")
            print(f"📄 Response time: {elapsed}s")
            print(f"📄 Body: {resp.text[:200]}")

            # Check for gateway errors (app frozen/not responding)
            is_gateway_error = resp.status_code in [502, 503, 504]
            is_timeout_error = "upstream request timeout" in resp.text.lower()

            if is_gateway_error or is_timeout_error:
                print("❌ Gateway error or timeout - app is frozen")
                print("🔄 Redeploying...")
                w.apps.start(app_name)
                raise Exception(
                    f"App {app_name} is frozen (HTTP {resp.status_code}). Redeployed."
                )

            # 200 = app is responding and healthy
            # 401/403 = auth issue but app is responding
            if resp.status_code == 200:
                print(f"✅ Healthy - App responded with 200 in {elapsed}s")
                return {"healthy": True, "response_time": elapsed, "status_code": 200}
            elif resp.status_code in [401, 403]:
                print(
                    f"⚠️ Auth issue (HTTP {resp.status_code}) but app responded in {elapsed}s"
                )
                return {
                    "healthy": True,
                    "response_time": elapsed,
                    "status_code": resp.status_code,
                    "warning": "auth_issue",
                }
            else:
                print(
                    f"⚠️ Unexpected status {resp.status_code} but app responded in {elapsed}s"
                )
                return {
                    "healthy": True,
                    "response_time": elapsed,
                    "status_code": resp.status_code,
                    "warning": "unexpected_status",
                }
        else:
            print("⚠️ No URL available")
            return {"healthy": True, "warning": "No URL"}

    except requests.Timeout:
        print(f"❌ Timeout after {timeout}s - app is frozen!")
        print("🔄 Redeploying...")
        w.apps.start(app_name)
        raise Exception(f"App {app_name} timed out after {timeout}s. Redeployed.")

    except requests.exceptions.ConnectionError as e:
        print(f"❌ Connection error: {e}")
        print("🔄 Redeploying...")
        w.apps.start(app_name)
        raise Exception(f"App {app_name} connection failed. Redeployed.")

    except Exception as e:
        if "does not exist" in str(e):
            print(f"❌ App not found: {e}")
            raise Exception(f"App {app_name} not found: {e}")
        raise


if __name__ == "__main__":
    w = WorkspaceClient()
    print(f"Checking {APP_NAME}...\n")
    result = check_and_fix_app(APP_NAME, w, HTTP_TIMEOUT)
    print(f"\nResult: {result}")
