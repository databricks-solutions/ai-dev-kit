# Supervisor Agents (MAS)

Supervisor Agents orchestrate multiple specialized agents, routing user queries to the most appropriate agent based on the query content.

## What is a Supervisor Agent?

A Supervisor Agent (formerly Multi-Agent Supervisor, MAS) acts as a traffic controller for multiple AI agents, routing user queries to the most appropriate agent. It supports five types of agents:

1. **Knowledge Assistants (KA)**: Document-based Q&A from PDFs/files in Volumes
2. **Genie Spaces**: Natural language to SQL for data exploration
3. **Model Serving Endpoints**: Custom LLM agents, fine-tuned models, RAG applications
4. **Unity Catalog Functions**: Callable UC functions for data operations
5. **External MCP Servers**: JSON-RPC endpoints via UC HTTP Connections for external system integration

When a user asks a question:
1. **Analyzes** the query to understand the intent
2. **Routes** to the most appropriate specialized agent
3. **Returns** the agent's response to the user

This allows you to combine multiple specialized agents into a single unified interface.

## When to Use

Use a Supervisor Agent when:
- You have multiple specialized agents (billing, technical support, HR, etc.)
- Users shouldn't need to know which agent to ask
- You want to provide a unified conversational experience

## Prerequisites

Before creating a Supervisor Agent, you need agents of one or both types:

**Model Serving Endpoints** (`endpoint_name`):
- Knowledge Assistant (KA) endpoints (e.g., `ka-abc123-endpoint`)
- Custom agents built with LangChain, LlamaIndex, etc.
- Fine-tuned models
- RAG applications

**Genie Spaces** (`genie_space_id`):
- Existing Genie spaces for SQL-based data exploration
- Great for analytics, metrics, and data-driven questions
- No separate endpoint deployment required - reference the space directly
- To find a Genie space by name, use `find_genie_by_name(display_name="My Genie")`
- **Note**: There is NO system table for Genie spaces - do not try to query `system.ai.genie_spaces`

## Unity Catalog Functions

Unity Catalog Functions allow Supervisor Agents to call registered UC functions for data operations.

### Prerequisites

- UC Function already exists (use SQL `CREATE FUNCTION` or Python UDF)
- Agent service principal has `EXECUTE` privilege:
  ```sql
  GRANT EXECUTE ON FUNCTION catalog.schema.function_name TO `<agent_sp>`;
  ```

### Configuration

```json
{
  "name": "data_enrichment",
  "uc_function_name": "sales_analytics.utils.enrich_customer_data",
  "description": "Enriches customer records with demographic and purchase history data"
}
```

**Field**: `uc_function_name` - Fully-qualified function name in format `catalog.schema.function_name`

## External MCP Servers

External MCP Servers enable Supervisor Agents to interact with external systems (ERP, CRM, etc.) via UC HTTP Connections. The MCP server implements a JSON-RPC 2.0 endpoint that exposes tools for the Supervisor Agent to call.

### Prerequisites

**1. MCP Server Endpoint**: Your external system must provide a JSON-RPC 2.0 endpoint (e.g., `/api/mcp`) that implements the MCP protocol:

```python
# Example MCP server tool definition
TOOLS = [
    {
        "name": "approve_invoice",
        "description": "Approve a specific invoice",
        "inputSchema": {
            "type": "object",
            "properties": {
                "invoice_number": {"type": "string", "description": "Invoice number to approve"},
                "approver": {"type": "string", "description": "Name/email of approver"},
            },
            "required": ["invoice_number"],
        },
    },
]

# JSON-RPC methods: initialize, tools/list, tools/call
```

**2. UC HTTP Connection**: Create a Unity Catalog HTTP Connection that points to your MCP endpoint:

```sql
CREATE CONNECTION my_mcp_connection TYPE HTTP
OPTIONS (
  host 'https://my-app.databricksapps.com',  -- Your MCP server URL
  port '443',
  base_path '/api/mcp',                       -- Path to JSON-RPC endpoint
  client_id '<service_principal_id>',         -- OAuth M2M credentials
  client_secret '<service_principal_secret>',
  oauth_scope 'all-apis',
  token_endpoint 'https://<workspace>.azuredatabricks.net/oidc/v1/token',
  is_mcp_connection 'true'                    -- REQUIRED: Identifies as MCP connection
);
```

**3. Grant Permissions**: Agent service principal needs access to the connection:

```sql
GRANT USE CONNECTION ON my_mcp_connection TO `<agent_sp>`;
```

### Configuration

Reference the UC Connection using the `connection_name` field:

```python
{
    "name": "external_operations",
    "connection_name": "my_mcp_connection",
    "description": "Execute external system operations: approve invoices, create records, trigger workflows"
}
```

**Field**: `connection_name` - the name of the Unity Catalog HTTP Connection configured as an MCP server

**Important**: Make the description comprehensive - it guides the Supervisor Agent's routing decisions for when to call this agent.

### Complete Example: Multi-System Supervisor

Example showing integration of Genie, KA, and external MCP:

```python
manage_mas(
    action="create_or_update",
    name="AP_Invoice_Supervisor",
    agents=[
        {
            "name": "billing_analyst",
            "genie_space_id": "01abc123...",
            "description": "SQL analytics on AP invoice data: spending trends, vendor analysis, aging reports"
        },
        {
            "name": "policy_expert",
            "ka_tile_id": "f32c5f73...",
            "description": "Answers questions about AP policies, approval workflows, and compliance requirements from policy documents"
        },
        {
            "name": "ap_operations",
            "connection_name": "ap_invoice_mcp",
            "description": (
                "Execute AP operations: approve/reject/flag invoices, search invoice details, "
                "get vendor summaries, trigger batch workflows. Use for ANY action or write operation."
            )
        }
    ],
    description="AP automation assistant with analytics, policy guidance, and operational actions",
    instructions="""
    Route queries as follows:
    - Data questions (invoice counts, spend analysis, vendor metrics) → billing_analyst
    - Policy questions (thresholds, SLAs, compliance rules) → policy_expert
    - Actions (approve, reject, flag, search, workflows) → ap_operations

    When a user asks to approve, reject, or flag an invoice, ALWAYS use ap_operations.
    """
)
```

### MCP Connection Testing

Verify your connection before adding to MAS:

```sql
-- Test tools/list method
SELECT http_request(
  conn => 'my_mcp_connection',
  method => 'POST',
  path => '',
  json => '{"jsonrpc":"2.0","method":"tools/list","id":1}'
);
```

### Resources

- **MCP Protocol Spec**: [Model Context Protocol](https://modelcontextprotocol.io)

## Creating a Supervisor Agent

Use the `manage_mas` tool with `action="create_or_update"`:

- `name`: "Customer Support MAS"
- `agents`:
  ```json
  [
    {
      "name": "policy_agent",
      "ka_tile_id": "f32c5f73-466b-4798-b3a0-5396b5ece2a5",
      "description": "Answers questions about company policies and procedures from indexed documents"
    },
    {
      "name": "usage_analytics",
      "genie_space_id": "01abc123-def4-5678-90ab-cdef12345678",
      "description": "Answers data questions about usage metrics, trends, and statistics"
    },
    {
      "name": "custom_agent",
      "endpoint_name": "my-custom-endpoint",
      "description": "Handles specialized queries via custom model endpoint"
    }
  ]
  ```
- `description`: "Routes customer queries to specialized support agents"
- `instructions`: "Analyze the user's question and route to the most appropriate agent. If unclear, ask for clarification."

This example shows mixing Knowledge Assistants (policy_agent), Genie spaces (usage_analytics), and custom endpoints (custom_agent).

## Agent Configuration

Each agent in the `agents` list needs:

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Internal identifier for the agent |
| `description` | Yes | What this agent handles (critical for routing) |
| `ka_tile_id` | One of these | Knowledge Assistant tile ID (for document Q&A agents) |
| `genie_space_id` | One of these | Genie space ID (for SQL-based data agents) |
| `endpoint_name` | One of these | Model serving endpoint name (for custom agents) |
| `uc_function_name` | One of these | Unity Catalog function name in format `catalog.schema.function_name` |
| `connection_name` | One of these | Unity Catalog connection name (for external MCP servers) |

**Note**: Provide exactly one of: `ka_tile_id`, `genie_space_id`, `endpoint_name`, `uc_function_name`, or `connection_name`.

To find a KA tile_id, use `manage_ka(action="find_by_name", name="Your KA Name")`.
To find a Genie space_id, use `find_genie_by_name(display_name="Your Genie Name")`.

### Writing Good Descriptions

The `description` field is critical for routing. Make it specific:

**Good descriptions:**
- "Handles billing questions including invoices, payments, refunds, and subscription changes"
- "Answers technical questions about API errors, integration issues, and product bugs"
- "Provides information about HR policies, PTO, benefits, and employee handbook"

**Bad descriptions:**
- "Billing agent" (too vague)
- "Handles stuff" (not helpful)
- "Technical" (not specific)

## Provisioning Timeline

After creation, the Supervisor Agent endpoint needs to provision:

| Status | Meaning | Duration |
|--------|---------|----------|
| `PROVISIONING` | Creating the supervisor | 2-5 minutes |
| `ONLINE` | Ready to route queries | - |
| `OFFLINE` | Not currently running | - |

Use `manage_mas` with `action="get"` to check the status.

## Adding Example Questions

Example questions help with evaluation and can guide routing optimization:

```json
{
  "examples": [
    {
      "question": "I haven't received my invoice for this month",
      "guideline": "Should be routed to billing_agent"
    },
    {
      "question": "The API is returning a 500 error",
      "guideline": "Should be routed to technical_agent"
    },
    {
      "question": "How many vacation days do I have?",
      "guideline": "Should be routed to hr_agent"
    }
  ]
}
```

If the Supervisor Agent is not yet `ONLINE`, examples are queued and added automatically when ready.

## Best Practices

### Agent Design

1. **Specialized agents**: Each agent should have a clear, distinct purpose
2. **Non-overlapping domains**: Avoid agents with similar descriptions
3. **Clear boundaries**: Define what each agent does and doesn't handle

### Instructions

Provide routing instructions:

```
You are a customer support supervisor. Your job is to route user queries to the right specialist:

1. For billing, payments, or subscription questions → billing_agent
2. For technical issues, bugs, or API problems → technical_agent
3. For HR, benefits, or policy questions → hr_agent

If the query is unclear or spans multiple domains, ask the user to clarify.
```

### Fallback Handling

Consider adding a general-purpose agent for queries that don't fit elsewhere:

```json
{
  "name": "general_agent",
  "endpoint_name": "general-support-endpoint",
  "description": "Handles general inquiries that don't fit other categories, provides navigation help"
}
```

## Example Workflow

1. **Deploy specialized agents** as model serving endpoints:
   - `billing-assistant-endpoint`
   - `tech-support-endpoint`
   - `hr-assistant-endpoint`

2. **Create the MAS**:
   - Configure agents with clear descriptions
   - Add routing instructions

3. **Wait for ONLINE status** (2-5 minutes)

4. **Add example questions** for evaluation

5. **Test routing** with various query types

## Updating a Supervisor Agent

To update an existing Supervisor Agent:

1. **Add/remove agents**: Call `manage_mas` with `action="create_or_update"` and updated `agents` list
2. **Update descriptions**: Change agent descriptions to improve routing
3. **Modify instructions**: Update routing rules

The tool finds the existing Supervisor Agent by name and updates it.

## Troubleshooting

### Queries routed to wrong agent

- Review and improve agent descriptions
- Make descriptions more specific and distinct
- Add examples that demonstrate correct routing

### Endpoint not responding

- Verify each underlying model serving endpoint is running
- Check endpoint logs for errors
- Ensure endpoints accept the expected input format

### Slow responses

- Check latency of underlying endpoints
- Consider endpoint scaling settings
- Monitor for cold start issues

## Advanced: Hierarchical Routing

For complex scenarios, you can create multiple levels of Supervisor Agents:

```
Top-level Supervisor
├── Customer Support Supervisor
│   ├── billing_agent
│   ├── technical_agent
│   └── general_agent
├── Sales Supervisor
│   ├── pricing_agent
│   ├── demo_agent
│   └── contract_agent
└── Internal Supervisor
    ├── hr_agent
    └── it_helpdesk_agent
```

Each sub-supervisor is deployed as an endpoint and configured as an agent in the top-level supervisor.
