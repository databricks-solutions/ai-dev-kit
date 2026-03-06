import os
import time
from typing import Any, MutableMapping

from openai import OpenAI

CACHE_KEY = "dbx_oauth"


def get_serving_base_url() -> str:
    return os.environ.get(
        "DATABRICKS_SERVING_BASE_URL",
        "https://<your-workspace-host>/serving-endpoints",
    )


def get_model_name() -> str:
    model = os.environ.get("DATABRICKS_MODEL")
    if model:
        return model
    raise RuntimeError(
        "DATABRICKS_MODEL is required. Choose an endpoint from the "
        "databricks-model-serving skill and set it in the environment."
    )


def _workspace_host_from_serving_base_url(serving_base_url: str) -> str:
    return serving_base_url.split("/serving-endpoints")[0].rstrip("/")


def _normalize_host(host: str) -> str:
    host = host.strip().rstrip("/")
    if not host.startswith("http://") and not host.startswith("https://"):
        return "https://" + host
    return host


def _mint_oauth_token(serving_base_url: str) -> tuple[str, int]:
    import requests

    client_id = os.environ.get("DATABRICKS_CLIENT_ID")
    client_secret = os.environ.get("DATABRICKS_CLIENT_SECRET")
    if not (client_id and client_secret):
        raise RuntimeError(
            "No Databricks auth configured. Provide Apps service-principal creds "
            "(DATABRICKS_CLIENT_ID/SECRET) or set DATABRICKS_TOKEN (PAT)."
        )

    host = os.environ.get("DATABRICKS_HOST") or _workspace_host_from_serving_base_url(
        serving_base_url
    )
    token_url = f"{_normalize_host(host)}/oidc/v1/token"
    response = requests.post(
        token_url,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={"grant_type": "client_credentials", "scope": "all-apis"},
        auth=(client_id, client_secret),
        timeout=30,
    )

    if response.status_code >= 400:
        raise RuntimeError(
            f"Failed to mint OAuth token (HTTP {response.status_code}). "
            f"Response: {response.text[:500]}"
        )

    payload = response.json()
    access_token = payload.get("access_token")
    expires_in = int(payload.get("expires_in", 300))
    if not access_token:
        raise RuntimeError(f"Token endpoint response missing access_token: {payload}")
    return access_token, int(time.time()) + expires_in


def resolve_bearer_token(cache: MutableMapping[str, Any] | None = None) -> str:
    token = os.environ.get("DATABRICKS_TOKEN")
    if token:
        return token

    if cache:
        cached = cache.get(CACHE_KEY)
        if (
            cached
            and cached.get("access_token")
            and cached.get("expires_at", 0) > int(time.time()) + 30
        ):
            return cached["access_token"]

    access_token, expires_at = _mint_oauth_token(get_serving_base_url())
    if cache is not None:
        cache[CACHE_KEY] = {"access_token": access_token, "expires_at": expires_at}
    return access_token


def create_foundation_model_client(
    cache: MutableMapping[str, Any] | None = None,
) -> OpenAI:
    return OpenAI(
        api_key=resolve_bearer_token(cache=cache),
        base_url=get_serving_base_url(),
    )
