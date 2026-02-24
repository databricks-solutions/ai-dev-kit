---
name: databricks-app-python
description: "Build Python-based Databricks applications using Dash, Streamlit, or Flask."
---

# Databricks Python Application

Build Python-based Databricks applications using frameworks like Dash, Streamlit, Flask, or other Python web frameworks.

## Trigger Conditions

**Invoke when user requests**:
- "Dash app" or "Dash application"
- "Streamlit app" or "Streamlit application"
- "Python web app" for Databricks
- Building data visualization or dashboard apps
- Order management, analytics dashboard, etc.

**Do NOT invoke if user specifies**: APX, React, Node.js, or other non-Python frameworks.

## Framework Selection

Ask user which framework to use if not specified:
- **Dash** - Rich interactive dashboards, Bootstrap components, Plotly charts
- **Streamlit** - Rapid prototyping, simple syntax, data science focus, automatic reactivity
- **Flask** - Lightweight, flexible, custom web apps (coming soon)

### Dash vs Streamlit Comparison

| Aspect | Dash | Streamlit |
|--------|------|-----------|
| **Development Speed** | Moderate (more boilerplate) | Fast (script-based) |
| **Learning Curve** | Steeper (callbacks, components) | Gentle (Pythonic, intuitive) |
| **Layout Control** | High (Bootstrap grid, custom CSS) | Medium (columns, containers) |
| **Styling** | Extensive (Bootstrap themes, CSS) | Limited (custom CSS via markdown) |
| **Callbacks** | Explicit (Input/Output decorators) | Automatic (reruns on interaction) |
| **State Management** | Manual (via callbacks) | Built-in (st.session_state) |
| **Performance** | Better for complex interactions | Slower (full page reruns) |
| **Best For** | Production dashboards, BI tools | Prototypes, data science demos |
| **Multi-page Apps** | Better routing support | Simpler but less flexible |
| **Data Science Fit** | Good (requires more setup) | Excellent (notebook-like) |
| **Code Complexity** | ~600 lines for full app | ~400 lines for full app |

**Choose Dash when:**
- Building production-grade business intelligence dashboards
- Need precise control over layout and styling
- Require complex callback chains and interactions
- Want Bootstrap components and themes
- Building for non-technical business users

**Choose Streamlit when:**
- Rapid prototyping and POCs
- Data science team building internal tools
- Simple data exploration and visualization
- ML model demos and experiments
- Prefer notebook-like development workflow

For framework-specific details, see:
- **[dash.md](dash.md)** - Complete Dash implementation guide
- **[streamlit.md](streamlit.md)** - Complete Streamlit implementation guide
- **flask.md** - Flask patterns (coming soon)

## Prerequisites Check

1. Verify Python environment: `python --version` (3.9+)
2. Check for `uv` package manager: `uv --version`
3. Verify Databricks connectivity (if using real backend):
   - `DATABRICKS_WAREHOUSE_ID` (required for SQL backend)
   - Databricks CLI configured profile (SDK Config handles auth automatically)
   - **Note:** No explicit tokens needed when using SDK Config approach

## Core Architecture

All Python Databricks apps follow this pattern:

```
app-directory/
├── models.py              # Pydantic data models
├── backend_mock.py        # Mock backend with sample data
├── backend_real.py        # Real Databricks backend
├── {framework}_app.py     # Main application (dash_app.py, streamlit_app.py, etc.)
├── setup_database.py      # Database initialization
├── requirements.txt       # Python dependencies
├── app.yaml              # Databricks Apps configuration
├── .env                  # Environment configuration
└── README.md             # Documentation
```

### Framework-Specific Requirements

**Dash (dash_app.py):**
```txt
dash>=2.14.0
dash-bootstrap-components>=1.5.0
pandas>=2.0.0
plotly>=5.17.0
pydantic>=2.0.0
python-dotenv>=1.0.0
databricks-sdk>=0.12.0
databricks-sql-connector>=3.0.0
```

**Streamlit (streamlit_app.py):**
```txt
streamlit>=1.28.0
pandas>=2.0.0
plotly>=5.17.0
pydantic>=2.0.0
python-dotenv>=1.0.0
databricks-sdk>=0.12.0
databricks-sql-connector>=3.0.0
```

**Key Difference:** Dash requires `dash-bootstrap-components`, Streamlit doesn't need any additional UI libraries.

## Workflow Overview

### Phase 1: Planning & Models (10-15 min)
1. Understand requirements
2. Design data models
3. Create Pydantic models with validation
4. Create TodoWrite to track progress

### Phase 2: Mock Backend (10-15 min)
1. Generate realistic sample data
2. Implement filtering and search
3. Create statistics methods
4. Test data generation

### Phase 3: Application UI (20-30 min)
1. Set up framework structure
2. Create consistent styling
3. Build main pages/views
4. Add interactivity (filters, charts)
5. Implement data tables

### Phase 4: Real Backend (15-20 min)
1. Design Unity Catalog schema
2. Implement SQL queries
3. Create database initialization
4. Add data seeding from mock

### Phase 5: Testing & Documentation (10-15 min)
1. Test with mock backend
2. Test with real backend
3. Create comprehensive README
4. Add deployment instructions

## Databricks Connectivity Patterns

### Environment Configuration

```python
# Standard environment variables
USE_MOCK_BACKEND=true|false         # Toggle backend mode
DATABRICKS_WAREHOUSE_ID=...         # SQL Warehouse ID (required)
DATABRICKS_CATALOG=main             # Unity Catalog
DATABRICKS_SCHEMA=app_schema        # Schema name
DATABRICKS_APP_PORT=8080            # Application port
DEBUG=false                         # Debug mode

# Note: No DATABRICKS_TOKEN needed when using SDK Config
# Authentication handled automatically via:
# - Databricks CLI profile (local development)
# - Service principal (Databricks Apps)
```

### Backend Toggle Pattern

```python
import os

USE_MOCK = os.getenv("USE_MOCK_BACKEND", "true").lower() == "true"

if USE_MOCK:
    from backend_mock import MockBackend
    backend = MockBackend()
else:
    from backend_real import RealBackend
    backend = RealBackend()
```

### Pydantic Models Pattern

```python
from pydantic import BaseModel, Field, field_validator
from decimal import Decimal
from datetime import datetime
from enum import Enum
from typing import List, Optional

class StatusEnum(str, Enum):
    """Status enumeration"""
    ACTIVE = "active"
    INACTIVE = "inactive"

class Entity(BaseModel):
    """Main entity model"""
    id: str = Field(..., description="Unique identifier")
    name: str = Field(..., description="Entity name")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    status: StatusEnum = Field(default=StatusEnum.ACTIVE)
    amount: Decimal = Field(..., description="Monetary amount", gt=0)

    @field_validator('amount', mode='before')
    @classmethod
    def validate_amount(cls, v):
        """Ensure amount is a valid Decimal"""
        if isinstance(v, (int, float, str)):
            return Decimal(str(v))
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "id": "ENT-001",
                "name": "Example Entity",
                "status": "active",
                "amount": "99.99"
            }
        }
```

### Mock Backend Pattern

```python
from typing import List, Optional
from models import Entity

class MockBackend:
    """Mock backend with sample data"""

    def __init__(self):
        self.entities = self._generate_entities()

    def _generate_entities(self) -> List[Entity]:
        """Generate sample data"""
        return [
            Entity(id="ENT-001", name="Entity 1", amount=Decimal("100.00")),
            Entity(id="ENT-002", name="Entity 2", amount=Decimal("200.00")),
        ]

    def get_entities(self, filter_criteria: Optional[dict] = None) -> List[Entity]:
        """Get entities with optional filtering"""
        results = self.entities

        if filter_criteria:
            # Apply filters
            if filter_criteria.get("status"):
                results = [e for e in results if e.status == filter_criteria["status"]]

        return results

    def get_entity(self, entity_id: str) -> Optional[Entity]:
        """Get specific entity"""
        for entity in self.entities:
            if entity.id == entity_id:
                return entity
        return None

    def get_statistics(self) -> dict:
        """Get aggregated statistics"""
        return {
            "total_count": len(self.entities),
            "total_amount": float(sum(e.amount for e in self.entities))
        }
```

### Real Backend Pattern (Databricks SQL)

**Important:** For SQL Warehouse connection examples, see the Databricks Apps Cookbook:
- **Tables Read Example**: https://apps-cookbook.dev/docs/dash/tables/tables_read
- Shows proper service principal authentication using SDK Config

```python
import os
from databricks import sql
from databricks.sdk import WorkspaceClient
from databricks.sdk.core import Config
from typing import List, Optional
from models import Entity

class RealBackend:
    """Real backend using Databricks SQL with SDK Config authentication"""

    def __init__(self, catalog: Optional[str] = None, schema: Optional[str] = None):
        self.catalog = catalog or os.getenv("DATABRICKS_CATALOG", "main")
        self.schema = schema or os.getenv("DATABRICKS_SCHEMA", "app_schema")
        self.warehouse_id = os.getenv("DATABRICKS_WAREHOUSE_ID")

        if not self.warehouse_id:
            raise ValueError("DATABRICKS_WAREHOUSE_ID required")

        self.config = Config()  # Automatically handles authentication
        self._connection = None

    def _get_connection(self):
        """Get or create database connection using SDK Config"""
        if self._connection is None:
            self._connection = sql.connect(
                server_hostname=self.config.host,
                http_path=f"/sql/1.0/warehouses/{self.warehouse_id}",
                credentials_provider=lambda: self.config.authenticate
            )
        return self._connection

    def _execute_query(self, query: str, params: Optional[dict] = None) -> List[dict]:
        """Execute SQL query and return results"""
        connection = self._get_connection()
        cursor = connection.cursor()

        try:
            cursor.execute(query, params or {})
            columns = [desc[0] for desc in cursor.description]
            results = []
            for row in cursor.fetchall():
                results.append(dict(zip(columns, row)))
            return results
        finally:
            cursor.close()

    def get_entities(self, filter_criteria: Optional[dict] = None) -> List[Entity]:
        """Get entities with optional filtering"""
        query = f"""
        SELECT * FROM {self.catalog}.{self.schema}.entities
        WHERE 1=1
        """

        params = {}
        if filter_criteria and filter_criteria.get("status"):
            query += " AND status = :status"
            params["status"] = filter_criteria["status"]

        query += " ORDER BY created_at DESC"

        results = self._execute_query(query, params)
        return [Entity(**row) for row in results]

    def initialize_schema(self):
        """Initialize database schema"""
        self._execute_query(f"""
        CREATE TABLE IF NOT EXISTS {self.catalog}.{self.schema}.entities (
            id STRING NOT NULL,
            name STRING NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP(),
            status STRING NOT NULL,
            amount DECIMAL(10, 2) NOT NULL,
            PRIMARY KEY (id)
        )
        """)

    def close(self):
        """Close database connection"""
        if self._connection:
            self._connection.close()
            self._connection = None
```

### Database Setup Script Pattern

```python
"""Database setup script"""
import os
import argparse
from dotenv import load_dotenv
from backend_mock import MockBackend
from backend_real import RealBackend

def setup_database(seed_data: bool = False):
    """Initialize database and optionally seed data"""
    load_dotenv()

    # Verify environment
    required_vars = ["DATABRICKS_SERVER_HOSTNAME", "DATABRICKS_TOKEN", "DATABRICKS_WAREHOUSE_ID"]
    missing = [v for v in required_vars if not os.getenv(v)]
    if missing:
        print(f"Missing: {', '.join(missing)}")
        return 1

    # Initialize backend
    backend = RealBackend()
    backend.initialize_schema()

    # Seed if requested
    if seed_data:
        mock = MockBackend()
        # Copy data from mock to real backend
        for entity in mock.entities:
            backend.insert_entity(entity)

    backend.close()
    return 0

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", action="store_true")
    args = parser.parse_args()
    exit(setup_database(seed_data=args.seed))
```

## Best Practices

### Data Models
- Use Pydantic for validation
- Include proper type hints
- Add `json_schema_extra` examples
- Handle Decimal for currency
- Use Enums for status fields

### Backend Design
- Create both mock and real backends
- Use consistent interface between them
- Implement filtering and pagination
- Provide statistics/aggregations
- Use parameterized queries (security)

### Error Handling
- Validate environment variables
- Handle connection failures gracefully
- Provide clear error messages
- Log errors appropriately

### Configuration
- Use `.env` files for configuration
- Never commit secrets
- Provide `.env.example` template
- Support environment variable overrides

### Testing Strategy
1. Start with mock backend (rapid development)
2. Test all features with sample data
3. Initialize real database with `--seed`
4. Test with real backend
5. Verify performance at scale

## Common Patterns

### Decimal Handling
```python
# Always convert to Decimal for monetary values
@field_validator('price', 'total', mode='before')
@classmethod
def validate_decimal(cls, v):
    if isinstance(v, (int, float, str)):
        return Decimal(str(v))
    return v
```

### Date Formatting
```python
# Consistent date formatting
order.order_date.strftime("%Y-%m-%d %H:%M")
order.created_at.isoformat()
```

### Status Colors
```python
# Map status to visual indicators
STATUS_COLORS = {
    Status.ACTIVE: "#2CA02C",    # Green
    Status.PENDING: "#FF7F0E",   # Orange
    Status.FAILED: "#D62728",    # Red
}
```

### Filtering Pattern
```python
# Reusable filter criteria model
class FilterCriteria(BaseModel):
    status: Optional[Status] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    search: Optional[str] = None
```

## Success Criteria

- [ ] Pydantic models with proper validation
- [ ] Mock backend with realistic data
- [ ] Framework UI with consistent styling
- [ ] Real backend with Unity Catalog
- [ ] Database initialization script
- [ ] Environment configuration
- [ ] Comprehensive documentation
- [ ] Both backends tested and working

## Troubleshooting

**First Step: Check Application Logs**
```bash
# Always check logs first when troubleshooting
databricks apps logs <app-name> --profile <profile-name>

# Examples:
databricks apps logs order-management-dash-dev -p DEFAULT
databricks apps logs order-management-streamlit-dev -p DEFAULT
```

Logs reveal:
- Deployment errors and stack traces
- Backend connection status (look for "✅ Initialized real backend")
- Missing dependencies or import errors
- SQL connection failures
- App startup issues

**Connection Issues**
- Verify Databricks CLI profile is configured: `databricks auth profiles`
- Check `DATABRICKS_WAREHOUSE_ID` exists and is accessible
- Ensure warehouse is running: `databricks warehouses get <warehouse-id>`
- Verify network connectivity to workspace
- For service principal: Check permissions on warehouse and catalog
- **Check logs for connection errors:** `databricks apps logs <app-name>`

**Data Type Errors**
- Use Decimal for monetary values
- Handle None/Optional properly
- Validate datetime parsing

**Performance Issues**
- Add database indexes
- Implement pagination
- Use query result caching
- Optimize SQL queries

## Deployment to Databricks

### Ask User for Deployment Preference

**IMPORTANT:** Before deploying, ask the user which deployment method they prefer:

1. **Databricks CLI** - Simple, direct deployment using `databricks apps` commands
2. **Databricks Asset Bundles (DABs)** - Infrastructure-as-code approach with version control

Example: "Would you like to deploy using Databricks CLI or Databricks Asset Bundles (DABs)?"

### Option 1: Deploy with Databricks CLI

**Prerequisites:**
- Databricks CLI installed
- Authenticated profile configured
- SQL Warehouse ID available

**Steps:**

1. **Create app.yaml**

**For Dash apps:**
```yaml
command:
  - "python"
  - "dash_app.py"

env:
  - name: USE_MOCK_BACKEND
    value: "false"
  - name: DATABRICKS_WAREHOUSE_ID
    value: "your-warehouse-id"
  - name: DATABRICKS_CATALOG
    value: "main"
  - name: DATABRICKS_SCHEMA
    value: "app_schema"
  - name: DATABRICKS_APP_PORT
    value: "8080"
  - name: DEBUG
    value: "false"
```

**For Streamlit apps:**
```yaml
command:
  - "streamlit"
  - "run"
  - "streamlit_app.py"
  - "--server.port"
  - "8080"
  - "--server.address"
  - "0.0.0.0"

env:
  - name: USE_MOCK_BACKEND
    value: "false"
  - name: DATABRICKS_WAREHOUSE_ID
    value: "your-warehouse-id"
  - name: DATABRICKS_CATALOG
    value: "main"
  - name: DATABRICKS_SCHEMA
    value: "app_schema"
```

**Note:** Streamlit uses `streamlit run` command, while Dash uses `python`. Streamlit doesn't need `DATABRICKS_APP_PORT` env var as it's specified in the command.

2. **Initialize database schema**
```bash
# Run setup script locally (requires profile configured)
python setup_database.py --seed
```

3. **Create Databricks app**
```bash
databricks apps create <app-name> --profile <profile-name>
```

4. **Upload source code to workspace**
```bash
databricks workspace mkdirs /Workspace/Users/<user>/apps/<app-name> --profile <profile-name>
databricks workspace import-dir . /Workspace/Users/<user>/apps/<app-name> --profile <profile-name>
```

5. **Deploy the app**
```bash
databricks apps deploy <app-name> \
  --source-code-path /Workspace/Users/<user>/apps/<app-name> \
  --profile <profile-name>
```

6. **Get app URL**
```bash
databricks apps get <app-name> --profile <profile-name>
```

**Redeployment:**
```bash
# Update workspace files
databricks workspace delete /Workspace/Users/<user>/apps/<app-name> --recursive --profile <profile-name>
databricks workspace mkdirs /Workspace/Users/<user>/apps/<app-name> --profile <profile-name>
databricks workspace import-dir . /Workspace/Users/<user>/apps/<app-name> --profile <profile-name>

# Redeploy
databricks apps deploy <app-name> \
  --source-code-path /Workspace/Users/<user>/apps/<app-name> \
  --profile <profile-name>
```

### Option 2: Deploy with Databricks Asset Bundles (DABs)

**Prerequisites:**
- Databricks CLI installed (v0.239.0+)
- App already deployed via CLI (recommended workflow)

**Advantages:**
- Version controlled deployment
- Multi-environment support (dev/staging/prod)
- Declarative infrastructure
- Easier CI/CD integration

**Recommended Workflow: CLI First, Then DABs**

1. **Deploy app using CLI first** (see Option 1 above)
   - This creates the app and validates everything works
   - Easier to debug issues initially

2. **Generate bundle configuration from existing app**
```bash
# This creates resources/*.app.yml and downloads source to src/app/
databricks bundle generate app \
  --existing-app-name <app-name> \
  --key <resource_key> \
  --profile <profile-name>

# Example:
databricks bundle generate app \
  --existing-app-name order-management-dash \
  --key order_management_dash \
  --profile DEFAULT
```

**What gets generated:**
- `resources/<resource_key>.app.yml` - Minimal app resource definition
- `src/app/` - All app source files including `app.yaml` with env vars
- `databricks.yml` updated with bundle structure

3. **Update generated configuration for multi-environment**

**Edit `databricks.yml`:**
```yaml
bundle:
  name: <app-name>

include:
  - resources/*.yml

variables:
  warehouse_id:
    default: "your-warehouse-id"
  catalog:
    default: "main"
  schema:
    default: "app_schema"

targets:
  dev:
    default: true
    mode: development
    workspace:
      profile: <profile-name>
    variables:
      warehouse_id: "dev-warehouse-id"
      schema: "app_schema_dev"

  prod:
    mode: production
    workspace:
      profile: <profile-name>
    variables:
      warehouse_id: "prod-warehouse-id"
      schema: "app_schema_prod"
```

**Edit `resources/<resource_key>.app.yml`:**
```yaml
resources:
  apps:
    <resource_key>:
      name: <app-name>-${bundle.target}    # Environment-specific naming
      description: "Python ${framework} application"
      source_code_path: ../src/app         # Or .. if source in project root
```

**Important:** Environment variables are in `src/app/app.yaml`, NOT in databricks.yml:
```yaml
command:
  - "python"
  - "dash_app.py"

env:
  - name: USE_MOCK_BACKEND
    value: "false"
  - name: DATABRICKS_WAREHOUSE_ID
    value: "your-warehouse-id"
  - name: DATABRICKS_CATALOG
    value: "main"
  - name: DATABRICKS_SCHEMA
    value: "app_schema"
```

4. **Deploy and run**
```bash
# Validate configuration
databricks bundle validate -t dev

# Deploy to dev (creates/updates resource)
databricks bundle deploy -t dev

# Start the app (required after deployment)
databricks bundle run <resource_key> -t dev

# For production
databricks bundle deploy -t prod
databricks bundle run <resource_key> -t prod
```

**Key Differences from Other Resources:**
- Environment variables go in `app.yaml` (source dir), NOT databricks.yml
- Apps have minimal bundle configuration (name, description, path)
- Must run `databricks bundle run` to start the app after deployment

**For complete DABs guidance, use the `asset-bundles` skill.**

### Post-Deployment Steps

1. **Verify deployment**
   - Access app URL
   - Check all pages load
   - Verify data from Unity Catalog

2. **Configure permissions**
   - Set up user access
   - Configure service principal permissions
   - Grant warehouse access

3. **Set up monitoring and view logs**

   **View application logs:**
   ```bash
   # View logs for your deployed app
   databricks apps logs <app-name> --profile <profile-name>

   # Examples:
   databricks apps logs order-management-dash-dev --profile DEFAULT
   databricks apps logs order-management-streamlit-dev --profile DEFAULT
   ```

   **What logs show:**
   - `[SYSTEM]` - Deployment status, file updates, dependency installation
   - `[APP]` - Application output (print statements, framework messages)
   - Backend initialization messages
   - Connection status to Unity Catalog
   - Error messages and stack traces

   **Useful for debugging:**
   - ✅ Verify real backend connection: Look for "✅ Initialized real backend: main.schema"
   - ✅ Check dependency installation: "Requirements installed successfully"
   - ✅ Confirm app start: "App started successfully"
   - ✅ Diagnose connection errors: SQL connection failures
   - ✅ Track deployments: Each deployment has unique ID

   **Additional monitoring:**
   - Monitor warehouse usage in Databricks SQL
   - Track app performance and response times
   - Set up alerts for app failures

4. **Documentation**
   - Update README with deployment URL
   - Document environment variables
   - Add troubleshooting guide

## Reference Materials

For framework-specific implementation details:
- **[dash.md](dash.md)** - Complete Dash implementation guide with Bootstrap components
- **[streamlit.md](streamlit.md)** - Complete Streamlit implementation guide with caching patterns
- **flask.md** - Flask patterns (coming soon)
