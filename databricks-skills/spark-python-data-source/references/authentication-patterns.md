# Authentication Patterns

Multi-method authentication strategies with clear priority ordering.

## Priority-Based Authentication

Support multiple authentication methods with fallback:

```python
class AuthenticatedDataSource(DataSource):
    def __init__(self, options):
        # Priority 1: Databricks Unity Catalog credential
        self.databricks_credential = options.get("databricks_credential")

        # Priority 2: Cloud default credential (managed identity)
        self.default_credential = options.get("default_credential", "false").lower() == "true"

        # Priority 3: Service principal
        self.tenant_id = options.get("tenant_id")
        self.client_id = options.get("client_id")
        self.client_secret = options.get("client_secret")

        # Priority 4: API key
        self.api_key = options.get("api_key")

        # Priority 5: Username/password
        self.username = options.get("username")
        self.password = options.get("password")

        # Validate at least one method is configured
        self._validate_auth()

    def _validate_auth(self):
        """Validate at least one auth method is configured."""
        has_databricks_cred = bool(self.databricks_credential)
        has_default_cred = self.default_credential
        has_service_principal = all([self.tenant_id, self.client_id, self.client_secret])
        has_api_key = bool(self.api_key)
        has_basic_auth = bool(self.username and self.password)

        if not any([has_databricks_cred, has_default_cred, has_service_principal,
                    has_api_key, has_basic_auth]):
            raise AssertionError(
                "Authentication required. Provide one of: "
                "'databricks_credential', 'default_credential=true', "
                "'tenant_id/client_id/client_secret', 'api_key', or 'username/password'"
            )
```

## Azure Authentication

### Unity Catalog Service Credential

```python
def _get_azure_credential_uc(credential_name):
    """Get credential from Unity Catalog."""
    import databricks.service_credentials

    return databricks.service_credentials.getServiceCredentialsProvider(credential_name)
```

### Default Credential (Managed Identity)

```python
def _get_azure_credential_default(authority=None):
    """Get DefaultAzureCredential for managed identity."""
    from azure.identity import DefaultAzureCredential

    if authority:
        return DefaultAzureCredential(authority=authority)
    return DefaultAzureCredential()
```

### Service Principal

```python
def _get_azure_credential_sp(tenant_id, client_id, client_secret, authority=None):
    """Get service principal credential."""
    from azure.identity import ClientSecretCredential

    if authority:
        return ClientSecretCredential(
            tenant_id=tenant_id,
            client_id=client_id,
            client_secret=client_secret,
            authority=authority
        )
    return ClientSecretCredential(
        tenant_id=tenant_id,
        client_id=client_id,
        client_secret=client_secret
    )
```

### Multi-Cloud Support

```python
def _get_azure_cloud_config(cloud_name):
    """Get cloud-specific endpoints and authorities."""
    from azure.identity import AzureAuthorityHosts

    cloud_configs = {
        "public": (None, None),
        "government": (
            AzureAuthorityHosts.AZURE_GOVERNMENT,
            "https://api.loganalytics.us"
        ),
        "china": (
            AzureAuthorityHosts.AZURE_CHINA,
            "https://api.loganalytics.azure.cn"
        ),
    }

    cloud = (cloud_name or "public").lower().strip()

    if cloud not in cloud_configs:
        valid = ", ".join(cloud_configs.keys())
        raise ValueError(f"Invalid cloud '{cloud_name}'. Valid: {valid}")

    return cloud_configs[cloud]

def _create_azure_client_with_cloud(options):
    """Create Azure client with cloud-specific configuration."""
    cloud_name = options.get("azure_cloud", "public")
    authority, endpoint = _get_azure_cloud_config(cloud_name)

    # Get credential based on priority
    credential = _get_credential(options, authority)

    # Create client with cloud-specific endpoint
    from azure.monitor.query import LogsQueryClient

    if endpoint:
        return LogsQueryClient(credential, endpoint=endpoint)
    return LogsQueryClient(credential)
```

## API Key Authentication

### Header-Based

```python
def _get_api_key_auth(api_key):
    """Get API key authentication headers."""
    return {"Authorization": f"Bearer {api_key}"}

def _create_session_with_api_key(api_key):
    """Create requests session with API key."""
    import requests

    session = requests.Session()
    session.headers.update({"Authorization": f"Bearer {api_key}"})
    return session
```

### Query Parameter-Based

```python
def _build_url_with_api_key(base_url, api_key):
    """Add API key as query parameter."""
    from urllib.parse import urlencode

    params = {"api_key": api_key}
    return f"{base_url}?{urlencode(params)}"
```

## Basic Authentication

```python
def _get_basic_auth(username, password):
    """Get HTTP Basic Auth."""
    from requests.auth import HTTPBasicAuth
    return HTTPBasicAuth(username, password)

def _create_session_with_basic_auth(username, password):
    """Create session with basic auth."""
    import requests

    session = requests.Session()
    session.auth = (username, password)
    return session
```

## OAuth2 Authentication

### Client Credentials Flow

```python
def _get_oauth2_token(token_url, client_id, client_secret, scope):
    """Get OAuth2 token using client credentials."""
    import requests

    response = requests.post(
        token_url,
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": scope
        }
    )
    response.raise_for_status()

    return response.json()["access_token"]

class OAuth2Writer:
    def __init__(self, options):
        self.token_url = options["token_url"]
        self.client_id = options["client_id"]
        self.client_secret = options["client_secret"]
        self.scope = options.get("scope", "")
        self._token = None
        self._token_expiry = None

    def _get_valid_token(self):
        """Get valid token, refresh if expired."""
        from datetime import datetime, timedelta

        if not self._token or datetime.now() >= self._token_expiry:
            self._token = _get_oauth2_token(
                self.token_url,
                self.client_id,
                self.client_secret,
                self.scope
            )
            # Assume 1 hour expiry if not provided
            self._token_expiry = datetime.now() + timedelta(hours=1)

        return self._token

    def write(self, iterator):
        """Write with OAuth2 authentication."""
        import requests

        token = self._get_valid_token()
        headers = {"Authorization": f"Bearer {token}"}

        for row in iterator:
            requests.post(self.url, json=row.asDict(), headers=headers)
```

## Complete Authentication Factory

```python
def get_credential(options):
    """
    Get credential based on configuration priority.

    Priority:
    1. databricks_credential
    2. default_credential
    3. Service principal (tenant_id/client_id/client_secret)
    4. API key
    5. Username/password
    """

    # Priority 1: Databricks credential
    if options.get("databricks_credential"):
        import databricks.service_credentials
        return databricks.service_credentials.getServiceCredentialsProvider(
            options["databricks_credential"]
        )

    # Priority 2: Cloud default credential
    if options.get("default_credential", "false").lower() == "true":
        authority = options.get("authority")
        if authority:
            from azure.identity import DefaultAzureCredential
            return DefaultAzureCredential(authority=authority)
        from azure.identity import DefaultAzureCredential
        return DefaultAzureCredential()

    # Priority 3: Service principal
    if all(k in options for k in ["tenant_id", "client_id", "client_secret"]):
        from azure.identity import ClientSecretCredential
        authority = options.get("authority")
        if authority:
            return ClientSecretCredential(
                tenant_id=options["tenant_id"],
                client_id=options["client_id"],
                client_secret=options["client_secret"],
                authority=authority
            )
        return ClientSecretCredential(
            tenant_id=options["tenant_id"],
            client_id=options["client_id"],
            client_secret=options["client_secret"]
        )

    # Priority 4: API key
    if "api_key" in options:
        return {"Authorization": f"Bearer {options['api_key']}"}

    # Priority 5: Basic auth
    if "username" in options and "password" in options:
        from requests.auth import HTTPBasicAuth
        return HTTPBasicAuth(options["username"], options["password"])

    raise ValueError("No valid authentication method configured")
```

## Security Best Practices

### Never Log Sensitive Values

```python
class SecureDataSource(DataSource):
    def __init__(self, options):
        self._sensitive_keys = {
            "password", "api_key", "client_secret", "token", "access_token"
        }

        # Store actual values
        self.options = options

        # Create sanitized version for logging
        self._safe_options = self._sanitize_options(options)

    def _sanitize_options(self, options):
        """Mask sensitive values for logging."""
        safe = {}
        for key, value in options.items():
            if key.lower() in self._sensitive_keys:
                safe[key] = "***REDACTED***"
            else:
                safe[key] = value
        return safe

    def __repr__(self):
        return f"SecureDataSource({self._safe_options})"
```

### Use Secrets Management

```python
def _load_secrets_from_dbutils(scope, keys):
    """Load secrets from Databricks secrets."""
    try:
        from pyspark.dbutils import DBUtils
        from pyspark.sql import SparkSession

        spark = SparkSession.getActiveSession()
        dbutils = DBUtils(spark)

        secrets = {}
        for key in keys:
            secrets[key] = dbutils.secrets.get(scope=scope, key=key)

        return secrets

    except Exception as e:
        raise ValueError(f"Failed to load secrets from scope '{scope}': {e}")

# Usage
if "secret_scope" in options:
    secrets = _load_secrets_from_dbutils(
        options["secret_scope"],
        ["password", "api_key"]
    )
    options.update(secrets)
```
