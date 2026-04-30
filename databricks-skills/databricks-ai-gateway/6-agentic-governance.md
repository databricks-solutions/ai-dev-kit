# Agentic Governance

AI Gateway V2 (Beta) is the enterprise control plane for governing LLM endpoints, coding agents, and MCP servers across agentic AI workflows.

## The Problem

Agents orchestrate multi-step workflows that span LLM calls, MCP server invocations, and external API requests, touching sensitive data at every step. A single user query might trigger a chain: LLM reasoning, a Salesforce lookup via MCP, a database write, then another LLM call to synthesize results. Traditional governance tools operate in silos -- they can monitor individual endpoints or log individual API calls, but they cannot trace across these boundaries or provide a unified view of what an agent did, why, and on whose authority.

## What V2 Adds

Beyond V1's per-endpoint guardrails, rate limits, and inference tables, V2 introduces:

- **MCP server governance** -- On-behalf-of user execution and tool access control for MCP connections
- **On-behalf-of execution** -- Agent calls inherit the requesting user's permissions, not a shared service account
- **Tool access control** -- Admins control which agents and teams can access which MCP servers and external systems
- **Multi-step traceability** -- End-to-end audit trails across every hop in an agentic workflow
- **Unified dashboard** -- Single pane of glass for spend, usage, and metrics across LLM endpoints, coding agents, and MCP servers
- **Real dollar cost attribution** -- Actual costs (not just token counts) across all tool types, including external provider pricing

## MCP Server Governance

### On-Behalf-Of Execution

When an agent calls an MCP server through AI Gateway, the call executes with the requesting user's exact permissions -- not a shared service account or the agent's own credentials. If user Alice asks an agent to query Salesforce via MCP, the MCP call runs as Alice with Alice's Salesforce permissions.

This prevents privilege escalation. An agent cannot access data or perform actions beyond what the requesting user is authorized to do, even if the agent itself has broader connectivity. The agent inherits the user's identity for the duration of the call.

### Tool Access Control

Admins define which MCP tools each team or agent can access. For example:

- The sales team's agents can access Salesforce and HubSpot MCP servers but not production databases
- The engineering team's agents can access GitHub and JIRA MCP servers but not financial systems
- A customer-facing chatbot agent can read from a product catalog MCP server but cannot write

### MCP Audit Logging

All MCP calls routed through AI Gateway are logged with:

- **Requesting identity** -- Who initiated the action (end user, not the agent)
- **Timestamp** -- When the call was made
- **Connection name** -- Which MCP server was called
- **HTTP method** -- What operation was performed
- **On-behalf-of flag** -- Whether the call used delegated user credentials

## Multi-Step Traceability

An agentic workflow touches multiple systems in sequence. AI Gateway traces every step:

```
User request
  → Agent receives query
    → Agent calls LLM (gateway logs: model, tokens, latency, requester)
      → LLM decides to use a tool
    → Agent calls MCP server, e.g. Salesforce (gateway logs: connection, identity, method)
      → MCP server returns data
    → Agent calls LLM again with tool results (gateway logs: model, tokens, latency)
  → Agent returns response to user
```

Every hop through the gateway produces an audit record. Together, these records answer:

- **Who authorized each action?** The requesting user's identity is logged at every step, not just the initial request.
- **What data was shared with which model?** Inference table payloads show exactly what was sent to each LLM call.
- **Were policies enforced consistently?** Guardrails, rate limits, and access controls are applied and logged at each gateway hop.
- **Can you trace the full chain?** A single request ID or correlation ID links every step from initial user query to final response.

## Integration with MLflow Tracing

AI Gateway audit logs and MLflow traces capture complementary views of the same agentic execution. Gateway logs record the infrastructure perspective: which endpoint was called, latency, status codes, token counts, and policy enforcement. MLflow traces record the application perspective: what the agent was reasoning about, which tool it chose and why, and how it assembled the final response.

When an agent fails mid-chain, cross-referencing the two gives the full picture. The gateway log shows which step returned an error (e.g., a 403 from the Salesforce MCP connection), while the MLflow trace shows what the agent was attempting and how it handled the failure. Use the `databricks_request_id` to correlate records across both systems.

For MLflow tracing setup and evaluation patterns, see the [databricks-mlflow-evaluation](../databricks-mlflow-evaluation/SKILL.md) skill.

## Unified Dashboard

The V2 dashboard provides a single view across all AI-powered tools in the organization:

- **Total spend** -- Aggregated dollar costs across LLM endpoints, coding agents (Cursor, Codex CLI, Claude Code), and MCP servers
- **Usage by team and department** -- Break down consumption by organizational unit using usage context tags
- **Cross-tool metrics** -- Compare request volumes, error rates, and latency across endpoint types in one view
- **Genie Code integration** -- Ask natural language questions against audit data ("Which team spent the most on external API calls last month?" or "Show me all MCP calls that used on-behalf-of execution in the last week") and get SQL-backed answers without writing queries

For usage tracking configuration and system table queries, see [4-observability.md](4-observability.md).

## V2 Beta Status

AI Gateway V2 is currently in **Beta**. Key considerations:

- V2 features do not incur additional charges during the Beta period
- APIs and configuration interfaces may change before general availability
- Not all features are available in all regions or cloud providers
- Check the [AI Gateway Beta docs](https://docs.databricks.com/aws/en/ai-gateway/overview-beta) for the latest availability and feature status
- Account admin or workspace admin permissions are required for V2 configuration
