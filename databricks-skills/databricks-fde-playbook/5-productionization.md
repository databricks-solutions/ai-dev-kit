# Part VI: Productionization

Productionization is where FDE engagements deliver lasting value. It's not enough to build something that works in a notebook — we need to deliver systems that are tested, observable, deployable, and maintainable by the customer team after we leave.

## 11. Observability & Monitoring

Production systems need to be observable — you should be able to understand what's happening, detect problems, and debug issues without adding more code.

For application-level logging setup, see [**2-code-quality.md §4.6 (Logging)**](2-code-quality.md).

### 11.1 Logging Best Practices

**Log at boundaries:**
- Entry and exit of jobs/pipelines
- External API calls (request/response summary, not full payload)
- Errors and exceptions with context
- Business events (records processed, decisions made)

**Include context:**

```python
logger.info(
    "Pipeline completed",
    extra={
        "pipeline": "customer_etl",
        "records_processed": 15000,
        "duration_seconds": 45,
        "run_id": run_id,
    }
)
```

**Don't log:** Sensitive data (PII, credentials), high-volume debug logs in production, full request/response payloads.

### 11.2 Key Metrics

Track metrics that reflect system health, performance, and business outcomes. Start with the metrics you will actually use.

**Common SLAs:**
- Latency (P50/P95/P99) — consider latency for each subsystem, not just round-trip
- Requests per second/minute/hour
- Error rate (status code counts)
- Token usage and cost (for AI systems)

**Metric tips:**
- Break metrics down by request type, region, date/time for useful insights
- Add tags consistently so metrics can be filtered and grouped
- Define SLOs for critical systems so teams know what "healthy" means
- Leverage [DBSQL alerts](https://docs.databricks.com/aws/en/sql/user/alerts/) when thresholds are exceeded

For alert YAML configuration, see **[databricks-asset-bundles alerts_guidance.md](../databricks-asset-bundles/alerts_guidance.md)**.

### 11.3 Dashboards

**Essential views:**
- **Health overview:** Error rate, latency, throughput
- **Business metrics:** Records processed, API calls, user activity

**Dashboard tips:**
- Keep dashboards focused — one purpose per dashboard
- Use consistent time ranges across panels
- Include links to runbooks for when things go wrong
- Review and prune unused dashboards periodically

### 11.4 Alerting

Alerts should be actionable. If an alert fires and there's nothing to do, it shouldn't be an alert.

**Good alert criteria:**
- Error rate > 5% for 5+ minutes
- P95 latency > SLA threshold for 10+ minutes
- Job failure (any production job)
- Resource exhaustion warnings

**Alert hygiene:**
- Every alert should have a runbook or clear next steps
- Review alert fatigue — too many alerts = ignored alerts
- Tune thresholds based on actual incidents

---

## 12. Deployment & CI/CD

CI/CD automation ensures consistent, repeatable deployments and catches issues before they reach production.

For the release flow overview, see [**1-foundations-and-setup.md §3.7 (Git Hygiene)**](1-foundations-and-setup.md).
For rollback procedures, see [**3-architecture.md §6.8 (Versioning & Rollback)**](3-architecture.md).

### 12.1 Environment Strategy

| Environment | Purpose | Deployed By | DAB Mode |
|-------------|---------|------------|---------|
| **Dev** | Individual developer iteration | Manual (`databricks bundle deploy -t dev`) | `development` (auto-prefixes resources) |
| **Staging** | Integration testing, mirrors prod | Automatic on merge to main | `production` |
| **Prod** | Customer-facing | Manual release tag | `production` |

**Key insight:** Dev is for manual developer iteration, NOT for CI/CD. The CI/CD pipeline deploys to staging and prod only.

### 12.2 CI Pipeline (Pull Requests)

Run **fast, cheap checks** on every PR. Don't run integration tests or evals here — they're expensive and slow.

```yaml
# .github/workflows/ci.yml
name: CI
on:
  pull_request:
    branches: [main]

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: install uv
        uses: astral-sh/setup-uv@v4

      - name: install dependencies
        run: uv sync --all-groups

      - name: lint
        run: uv run ruff check .

      - name: unit tests
        run: uv run pytest tests/unit/ -v

      - name: validate bundle
        env:
          DATABRICKS_HOST: ${{ secrets.DATABRICKS_HOST }}
          DATABRICKS_TOKEN: ${{ secrets.DATABRICKS_TOKEN }}
        run: databricks bundle validate -t staging
```

### 12.3 Staging Deployment (Merge to Main)

On merge to main, deploy to staging and run integration tests:

```yaml
# .github/workflows/deploy-staging.yml
name: Deploy to Staging
on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: install Databricks CLI
        uses: databricks/setup-cli@main

      - name: deploy to staging
        env:
          DATABRICKS_HOST: ${{ secrets.STAGING_DATABRICKS_HOST }}
          DATABRICKS_TOKEN: ${{ secrets.STAGING_DATABRICKS_TOKEN }}
        run: databricks bundle deploy -t staging

      - name: run integration tests
        env:
          DATABRICKS_HOST: ${{ secrets.STAGING_DATABRICKS_HOST }}
          DATABRICKS_TOKEN: ${{ secrets.STAGING_DATABRICKS_TOKEN }}
        run: databricks bundle run integration_tests -t staging
```

If integration tests fail, fix the issue before creating a release tag.

### 12.4 Production Deployment (Release Tags)

Deploy to production when a release tag is created. Only after staging integration tests pass.

```yaml
# .github/workflows/deploy-prod.yml
name: Deploy to Production
on:
  release:
    types: [published]

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: production  # Requires approval if configured
    steps:
      - uses: actions/checkout@v4

      - name: install Databricks CLI
        uses: databricks/setup-cli@main

      - name: deploy to production
        env:
          DATABRICKS_HOST: ${{ secrets.PROD_DATABRICKS_HOST }}
          DATABRICKS_TOKEN: ${{ secrets.PROD_DATABRICKS_TOKEN }}
        run: databricks bundle deploy -t prod
```

### 12.5 Environment Promotion Flow

**Key principles:**
- **PR checks are fast and cheap** — unit tests, lint, DAB validate only
- **Integration tests run post-merge in staging** — don't block PRs with expensive tests
- **Staging must pass before prod** — don't tag a release until integration tests are green
- **Prod requires explicit release tag** — intentional promotion, not automatic

---

## 13. Documentation & Handoff

Documentation is how knowledge survives the engagement. The customer team will maintain this system after FDE leaves.

### 13.1 Documentation Artifacts

| Document | Purpose |
|----------|--------|
| **Reference Doc** | Canonical system documentation — architecture, components, operations |
| **Design Doc** | Captures design decisions and rationale for major features |
| **Decision Docs** | Records specific technical decisions |
| **README** | Quick start for developers |

The **Reference Doc** is the most important handoff artifact — it's where someone new to the project starts.

### 13.2 README vs Reference Doc

| Document | Purpose | Audience | Length |
|----------|---------|----------|--------|
| **README** | Get developers productive quickly | Developers who need to run/modify code | 1–2 pages max |
| **Reference Doc** | Comprehensive system documentation | Anyone who needs to understand, operate, or extend the system | 10+ pages |

**README should include:** Brief overview (2–3 sentences), quick start steps, common commands, links to detailed documentation.

**README should NOT include:** Architecture details, component deep-dives, API specifications, operational procedures, design decisions — those belong in the Reference Doc / Design Docs.

**README template:**

```markdown
# Project Name

Brief description (2–3 sentences) of what this system does.

## Quick Start

1. Clone: `git clone <repo-url>`
2. Install: `uv sync`
3. Deploy to dev: `databricks bundle deploy -t dev`
4. Run tests: `make test`

## Common Commands

| Command | Description |
|---------|-------------|
| `make test` | Run unit tests |
| `make lint` | Run linting |
| `make deploy-dev` | Deploy to dev workspace |

## Documentation

- **[Reference Doc](link)** - Architecture, components, operations
- **[Design Doc](link)** - Design decisions and rationale
- **[Dashboards](link)** - Monitoring and observability
```

### 13.3 Knowledge Transfer

Conduct knowledge transfer sessions before the engagement ends:

| Session | Duration | Audience | Content |
|---------|---------|----------|--------|
| Architecture overview | 1–2 hours | Technical team | System design, data flow, key decisions |
| Codebase walkthrough | 2–3 hours | Developers | Code structure, patterns, how to make changes |
| DevOps walkthrough | 1–2 hours | Ops/DevOps | Deployment, monitoring, alerting, runbooks |

**Success criteria:** Customer team can independently deploy, monitor, and debug the system.

### 13.4 Production Readiness Checklist

Before considering a system production-ready:

**Code & Infrastructure:**
- [ ] All code in version control
- [ ] CI/CD pipeline operational and tested
- [ ] DAB resources defined and deploying correctly
- [ ] Secrets managed via Databricks Secrets

**Quality:**
- [ ] Unit tests passing with reasonable coverage
- [ ] Integration tests for critical paths
- [ ] Error handling comprehensive
- [ ] Logging implemented at key boundaries

**Operations:**
- [ ] Monitoring dashboards created
- [ ] Alerts configured for critical failures
- [ ] Runbooks written for common issues
- [ ] Backup/recovery plan documented (if applicable)

**Handoff:**
- [ ] Reference Doc complete and reviewed
- [ ] Knowledge transfer sessions completed
- [ ] Customer team trained
- [ ] Customer can deploy independently
- [ ] Access controls configured (principle of least privilege)

See also [**4-databricks-platform.md §9.2 (Engagement Exit Checklist)**](4-databricks-platform.md) for resource cleanup tasks.
