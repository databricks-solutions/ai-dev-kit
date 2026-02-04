---
name: genai-security-framework
description: Secure GenAI applications on Databricks using the AI Security Framework. Use when implementing prompt injection protection, data exfiltration prevention, model vulnerability scanning, or governance controls for LLM applications.
author: Databricksters Community
source_url: https://www.databricksters.com/p/securing-genai-agents-on-databricks
source_site: databricksters.com
---

# GenAI Security Framework on Databricks

## Overview

Production GenAI applications introduce new attack surfaces that traditional security tools don't address. This skill covers Databricks' comprehensive security framework for protecting LLM applications from prompt injection, data exfiltration, and other AI-specific threats.

**OWASP Top 10 for LLMs (2025):**
1. **LLM01:2025** - Prompt Injection
2. **LLM02:2025** - Sensitive Information Disclosure
3. **LLM03:2025** - Supply Chain Vulnerabilities
4. **LLM04:2025** - Data and Model Poisoning
5. **LLM05:2025** - Improper Output Handling
6. **LLM06:2025** - Excessive Agency
7. **LLM07:2025** - System Prompt Leakage
8. **LLM08:2025** - Vector and Embedding Weaknesses
9. **LLM09:2025** - Misinformation
10. **LLM10:2025** - Unbounded Consumption

## Security Layers

```
┌─────────────────────────────────────────────────────────────┐
│ Layer 1: Prompt Protection (AI Gateway)                     │
│ - Guardrails, rate limiting, safety filters                 │
├─────────────────────────────────────────────────────────────┤
│ Layer 2: Model Security (Garak Scanning)                    │
│ - Vulnerability scanning, penetration testing               │
├─────────────────────────────────────────────────────────────┤
│ Layer 3: Network Security (Egress Control)                  │
│ - FQDN allowlisting, default-deny outbound                  │
├─────────────────────────────────────────────────────────────┤
│ Layer 4: Data Governance (Unity Catalog)                    │
│ - Column/row-level security, audit logging                  │
├─────────────────────────────────────────────────────────────┤
│ Layer 5: AI Lifecycle Security (Noma)                       │
│ - Model inventory, AIBOM, continuous monitoring             │
└─────────────────────────────────────────────────────────────┘
```

## Layer 1: AI Gateway Protection

The Mosaic AI Gateway sits in front of model endpoints, processing prompts through guardrails and safety filters.

### Built-in Guardrails

```python
from databricks.model_serving import endpoint

# Enable AI Guardrails on endpoint
config = {
    "served_entities": [...],
    "ai_gateway": {
        "guardrails": {
            "pii": {
                "enabled": True,
                "action": "BLOCK"  # or "ANONYMIZE"
            },
            "safety": {
                "enabled": True,
                "categories": [
                    "HATE_SPEECH",
                    "VIOLENCE", 
                    "SEXUAL_CONTENT",
                    "HARASSMENT"
                ]
            }
        },
        "rate_limits": {
            "requests_per_minute": 1000,
            "tokens_per_minute": 100000
        }
    }
}

client.create_endpoint(name="protected-llm", config=config)
```

### Rate Limiting

Protect against abuse and manage costs:

| Level | Configuration | Use Case |
|-------|---------------|----------|
| **User** | Per-user limits | Prevent individual abuse |
| **Service Principal** | Per-application limits | Control app consumption |
| **Endpoint** | Global limits | Overall capacity protection |

```python
# Configure multi-level rate limiting
rate_limits = {
    "user_limits": {
        "requests_per_minute": 60,
        "tokens_per_minute": 10000
    },
    "endpoint_limits": {
        "requests_per_minute": 10000,
        "tokens_per_minute": 1000000
    }
}
```

## Layer 2: Model Vulnerability Scanning

Use NVIDIA's Garak to scan models for vulnerabilities before deployment.

### Garak Integration

```python
import json
import subprocess

# Garak configuration for Databricks endpoints
garak_config = {
    "model_type": "databricks",
    "model_name": "your-endpoint-name",
    "databricks_token": "${DATABRICKS_TOKEN}",
    "databricks_workspace": "https://your-workspace.cloud.databricks.com",
    "probes": [
        "promptinject",      # Prompt injection attempts
        "realtoxicityprompts",  # Toxic content generation
        "xss",               # XSS attempts
        "leakreplay"         # Data leakage attempts
    ]
}

# Save config
with open("garak_config.json", "w") as f:
    json.dump(garak_config, f)

# Run scan
subprocess.run([
    "garak",
    "--config", "garak_config.json",
    "--report", "security_report.json"
])
```

### Automated Scanning Pipeline

```python
# Databricks job for nightly security scans
import mlflow
from databricks.sdk import WorkspaceClient

def nightly_security_scan():
    """Run Garak scan and report failures."""
    
    # Run Garak
    result = run_garak_scan("production-endpoint")
    
    # Log results to MLflow
    with mlflow.start_run(run_name="security_scan"):
        mlflow.log_metric("vulnerabilities_found", result.vulnerability_count)
        mlflow.log_artifact("security_report.json")
        
        # Alert if issues found
        if result.vulnerability_count > 0:
            send_alert(f"Found {result.vulnerability_count} vulnerabilities")
            raise Exception("Security scan failed")
```

### Interpreting Results

| Probe Category | What It Tests | Severity |
|----------------|---------------|----------|
| `promptinject` | Direct/indirect prompt injection | **Critical** |
| `realtoxicityprompts` | Toxic content generation | **High** |
| `xss` | Cross-site scripting in outputs | **High** |
| `leakreplay` | Training data leakage | **Critical** |
| `encoding` | Base64/rot13 obfuscation attacks | **Medium** |

## Layer 3: Serverless Egress Control

Control outbound connections from model serving endpoints with default-deny policies.

### FQDN Allowlisting

```python
# Create Network Policy Configuration
from databricks.sdk.service.serving import (
    NetworkPolicyConfiguration,
    FqdnDestination,
    PolicyMode
)

# Define allowed destinations
allowed_destinations = [
    FqdnDestination(
        fqdn="api.your-company.com",
        port=443,
        protocol="https"
    ),
    FqdnDestination(
        fqdn="*.databricks.com",
        port=443,
        protocol="https"
    )
]

# Create policy in dry-run mode first
policy = NetworkPolicyConfiguration(
    mode=PolicyMode.DRY_RUN,  # Log only, don't block
    allowed_fqdns=allowed_destinations
)

# Apply to endpoint
client.update_endpoint_network_policy(
    endpoint_name="protected-llm",
    policy=policy
)
```

### Monitoring Denied Connections

```sql
-- Query audit logs for denied egress attempts
SELECT 
    timestamp,
    endpoint_name,
    attempted_fqdn,
    destination_ip,
    user_agent
FROM system.serving.egress_logs
WHERE action = 'DENIED'
    AND timestamp > current_timestamp() - interval 24 hours
ORDER BY timestamp DESC;
```

### Network Connectivity Configurations (NCC)

For private connectivity without VPC complexity:

```python
# Create NCC for private endpoints
from databricks.sdk.service.serving import NetworkConnectivityConfig

ncc = NetworkConnectivityConfig(
    name="private-connectivity",
    private_endpoints=[
        {
            "resource_id": "/subscriptions/.../privateLinkServices/...",
            "fqdn": "internal-api.company.com"
        }
    ]
)

# Attach to endpoint
client.update_endpoint_network_connectivity(
    endpoint_name="protected-llm",
    ncc_id=ncc.id
)
```

**NCC Limits:**
- Azure: 100 private endpoints per region (GA)
- AWS: 30 private endpoints per region (Public Preview)
- GCP: Limited availability

## Layer 4: Data Governance with Unity Catalog

### Column and Row-Level Security

```sql
-- Column-level security
CREATE TABLE sensitive_data (
    id BIGINT,
    public_field STRING,
    sensitive_field STRING,
    pii_field STRING
);

-- Grant column-level access
GRANT SELECT(public_field, sensitive_field) ON TABLE sensitive_data TO ANALYSTS;
GRANT SELECT ON TABLE sensitive_data TO DATA_SCIENTISTS;

-- Row-level filters
CREATE FUNCTION region_filter(region STRING)
RETURN CASE 
    WHEN is_member('GLOBAL_ANALYSTS') THEN TRUE
    WHEN is_member('NA_ANALYSTS') AND region = 'NA' THEN TRUE
    WHEN is_member('EU_ANALYSTS') AND region = 'EU' THEN TRUE
    ELSE FALSE
END;

ALTER TABLE sales_data 
SET ROW FILTER region_filter ON (region);
```

### Token Scoping

```python
# Create scoped token for agent
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

# Token with limited scope
scoped_token = w.tokens.create(
    lifetime_seconds=3600,
    comment="GenAI agent token",
    permissions=[
        {
            "permission_level": "CAN_READ",
            "table": "catalog.schema.allowed_table"
        }
    ]
)
```

## Layer 5: AI Lifecycle Security (Noma)

Databricks Ventures invested in Noma Security for comprehensive AI security governance.

### Key Capabilities

| Capability | Description |
|------------|-------------|
| **AI Bill of Materials (AIBOM)** | Inventory all AI assets |
| **Model Discovery** | Find shadow AI deployments |
| **Risk Detection** | Identify vulnerabilities pre-runtime |
| **Continuous Monitoring** | Detect anomalous behavior |
| **Compliance** | ISO 42001, NIST AI RMF alignment |

### Integration Pattern

```python
# Noma integration for AI asset inventory
from noma import NomaClient

noma = NomaClient(
    api_key="${NOMA_API_KEY}",
    databricks_workspace="https://your-workspace.cloud.databricks.com"
)

# Register model in AIBOM
noma.register_model(
    model_name="customer-service-agent",
    model_version="1.2.0",
    endpoint_url="https://.../serving-endpoints/customer-agent",
    training_data=["catalog.schema.training_data"],
    dependencies=["llama-2-70b", "faiss-cpu"],
    risk_assessment={
        "data_sensitivity": "HIGH",
        "exposure": "EXTERNAL",
        "compliance_requirements": ["GDPR", "SOX"]
    }
)

# Continuous monitoring
noma.monitor_endpoint(
    endpoint_name="customer-service-agent",
    alert_on=[
        "prompt_injection_attempt",
        "data_exfiltration_pattern",
        "model_drift"
    ]
)
```

## Databricks AI Security Framework (DASF) 2.0

DASF 2.0 maps 62 technical security risks across 12 AI system components.

### Risk Categories by Stage

| Stage | Key Risks | Mitigation |
|-------|-----------|------------|
| **Data Collection** | Data poisoning, bias injection | Data validation, lineage tracking |
| **Training** | Model poisoning, credential theft | Secure training environments |
| **Model Serving** | Prompt injection, jailbreaks | AI Gateway, guardrails |
| **Inference** | Data exfiltration, inference attacks | Egress control, monitoring |
| **Response** | Hallucination, toxic output | Output filtering, safety models |

### Framework Application

```python
# Apply DASF risk assessment
risk_assessment = {
    "application": "customer-service-chatbot",
    "data_classification": "PII",
    "exposure": "INTERNET",
    "safeguards": {
        "input_validation": True,
        "output_filtering": True,
        "rate_limiting": True,
        "audit_logging": True,
        "human_in_the_loop": False  # Flag as risk
    }
}

# Identify gaps
gaps = identify_dasf_gaps(risk_assessment)
for gap in gaps:
    print(f"Risk: {gap.risk_id} - {gap.description}")
    print(f"Remediation: {gap.recommendation}")
```

## Best Practices

### 1. Defense in Depth

Implement multiple security layers:

```python
# Layer 1: Input validation
@ai_gateway_guardrail
async def validate_input(user_input):
    # Check for injection attempts
    if detect_injection(user_input):
        raise SecurityException("Potential injection detected")
    return user_input

# Layer 2: Model-level protection
model_endpoint = create_endpoint(
    guardrails=enabled,
    rate_limits=strict
)

# Layer 3: Output filtering
@output_filter
def clean_response(model_output):
    # Remove PII, check for toxicity
    return filter_output(model_output)
```

### 2. Principle of Least Privilege

```python
# Give agents minimum required access
def create_restricted_agent():
    return Agent(
        tools=[
            # Only specific tables
            ReadTable("catalog.schema.allowed_data"),
            # No write access
            # No external API access without approval
        ],
        max_tokens=1000,  # Limit output
        allowed_models=["small-safe-model"]  # Restrict model choice
    )
```

### 3. Audit Everything

```sql
-- Enable comprehensive audit logging
CREATE AUDIT LOG genai_access_log (
    timestamp TIMESTAMP,
    user STRING,
    endpoint STRING,
    input_tokens INT,
    output_tokens INT,
    guardrail_triggers ARRAY<STRING>,
    response_status STRING
);
```

### 4. Regular Security Scanning

```python
# Schedule weekly Garak scans
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

# Create security scan job
w.jobs.create(
    name="weekly-security-scan",
    tasks=[
        Task(
            task_key="scan",
            notebook_task=NotebookTask(
                notebook_path="/Security/garak-scan"
            )
        ),
        Task(
            task_key="notify",
            depends_on=[{"task_key": "scan"}],
            notification_task=NotificationTask(
                alert_on_failure=True,
                email_addresses=["security@company.com"]
            )
        )
    ],
    schedule=CronSchedule(
        quartz_cron_expression="0 0 2 * * 0",  # Weekly on Sunday
        timezone_id="America/New_York"
    )
)
```

## Incident Response

### Prompt Injection Detection

```python
def handle_potential_injection(user_input, model_output):
    """Response flow for detected injection attempts."""
    
    # Log incident
    log_security_event(
        event_type="PROMPT_INJECTION_ATTEMPT",
        input_hash=hash(user_input),
        timestamp=now(),
        user=current_user()
    )
    
    # Block and alert
    block_user(current_user(), duration=timedelta(hours=1))
    notify_security_team(
        severity="HIGH",
        details={
            "input_sample": user_input[:100],
            "detection_confidence": 0.95
        }
    )
    
    # Return safe response
    return "I'm unable to process that request. Please try rephrasing."
```

## Attribution

This skill is based on **Securing Gen‑AI Agents on Databricks: How I Keep Prompt-Injection and Data-Leak Nightmares at Bay** from the Databricksters blog.

## References

- [Databricks AI Security Framework 2.0](https://www.databricks.com/blog/announcing-databricks-ai-security-framework-20)
- [AI Gateways Documentation](https://docs.databricks.com/aws/en/machine-learning/model-serving/ai-gateways)
- [Serverless Egress Control](https://www.databricks.com/blog/announcing-egress-control-serverless-and-model-serving-workloads)
- [Garak LLM Scanner](https://github.com/leondz/garak)
- [OWASP Top 10 for LLM Applications](https://owasp.org/www-project-top-10-for-large-language-model-applications/)
