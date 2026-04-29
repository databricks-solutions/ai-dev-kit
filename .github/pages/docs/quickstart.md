---
hide:
  - navigation
---

<div class="qs" markdown>

# Quickstart

## <span class="num">1</span> Install the AI Dev Kit <span class="dur">2 min</span>

You need **uv**, the **Databricks CLI** (authenticated), and an AI coding assistant.

=== "Mac / Linux"

    ```bash
    bash <(curl -sL https://raw.githubusercontent.com/databricks-solutions/ai-dev-kit/main/install.sh)
    ```

=== "Windows"

    ```powershell
    irm https://raw.githubusercontent.com/databricks-solutions/ai-dev-kit/main/install.ps1 | iex
    ```

Follow the interactive prompts, then open your AI assistant from the same directory.

!!! success "What you'll see"
    Your project now has `.claude/skills/` (27 Databricks skills) and `.claude/mcp.json` (MCP server config). Your AI assistant can talk to Databricks.

<div class="step-screenshot">
<img src="../assets/step1-install.png" alt="Install output">
</div>

---

## <span class="num">2</span> Explore your data <span class="dur">5 min</span>

Discover what's in your workspace. Open your AI assistant and paste:

!!! example "Prompt"
    ```
    What catalogs and schemas are available in my Databricks workspace?
    Show me the tables in each schema with their column names and row counts.
    ```

Now pick a table and profile it:

!!! example "Prompt"
    ```
    Profile the table `main.default.my_table`. Show total rows, null counts
    per column, value distributions for categoricals (top 10), and
    min/max/mean for numerics. Include 5 sample rows.
    ```

!!! tip
    Replace `main.default.my_table` with a real table. If your workspace is empty, the next step generates sample data.

<div class="step-screenshot">
<img src="../assets/step2-explore.png" alt="Table exploration results">
</div>

---

## <span class="num">3</span> Generate sample data <span class="dur">5 min</span>

If you need data for the rest of this quickstart:

!!! example "Prompt"
    ```
    Generate a realistic e-commerce dataset in my workspace:
    - main.quickstart.customers — 10,000 rows (name, email, signup_date, segment)
    - main.quickstart.orders — 50,000 rows (order_id, customer_id, order_date, total_amount, status)
    - main.quickstart.products — 500 rows (product_id, name, category, price)

    Use realistic distributions, not uniform random. Make sure foreign keys are valid.
    ```

!!! success "What you'll see"
    Three tables created in Unity Catalog with realistic distributions, immediately queryable.

Try asking a question:

!!! example "Prompt"
    ```
    What are the top 10 product categories by total revenue?
    Break it down by month for the last 6 months.
    ```

---

## <span class="num">4</span> Build a data pipeline <span class="dur">15 min</span>

Create a production-ready Spark Declarative Pipeline with the medallion architecture.

!!! example "Prompt"
    ```
    Create a new Spark Declarative Pipeline using Databricks Asset Bundles:

    - Python (not SQL)
    - Medallion architecture: bronze → silver → gold
    - Serverless compute
    - Target: main.quickstart schema

    Bronze: ingest from orders and customers tables
    Silver: clean nulls, join orders with customers, add order_year/month columns
    Gold: materialized views for monthly_revenue (by month + segment)
         and customer_lifetime_value

    Initialize with `databricks pipelines init`, then deploy and run it.
    ```

!!! success "What you'll see"
    The assistant scaffolds a DAB project with bronze/silver/gold Python files, deploys it, triggers a run, and shows pipeline status as each table processes.

!!! info "How skills help"
    The assistant loaded `databricks-spark-declarative-pipelines` and `databricks-bundles` skills, which taught it correct SDP patterns, serverless defaults, and Asset Bundle structure. Without these skills, it would guess — and often get it wrong.

<div class="step-screenshot">
<img src="../assets/step4-pipeline.png" alt="Pipeline status">
</div>

---

## <span class="num">5</span> Create a dashboard <span class="dur">10 min</span>

Build an AI/BI dashboard from the gold tables your pipeline just created.

!!! example "Prompt"
    ```
    Create an AI/BI dashboard called "Quickstart: Sales Overview" using main.quickstart:

    1. Counter: total revenue
    2. Counter: total orders
    3. Line chart: monthly revenue trend (last 12 months)
    4. Bar chart: revenue by customer segment
    5. Table: top 20 customers by lifetime value
    6. Date range filter on all charts

    Test all SQL queries before deploying.
    ```

!!! success "What you'll see"
    The assistant follows the mandatory validation workflow: get schemas → write SQL → **test every query** → build dashboard JSON → deploy. Returns a URL to the live dashboard.

Iterate by asking:

!!! example "Prompt"
    ```
    Update the dashboard: change the monthly chart to a stacked area by segment,
    and add a second page "Customers" with a scatter plot of order frequency
    vs average order value.
    ```

!!! info "Why validation matters"
    The `databricks-aibi-dashboards` skill enforces SQL testing before deployment. Without it, widgets show "Invalid widget definition" errors. Skills encode hard-won best practices.

<div class="step-screenshot">
<img src="../assets/step5-dashboard.png" alt="Dashboard preview">
</div>

---

## <span class="num">6</span> Deploy an AI agent <span class="dur">15 min</span>

Create a Knowledge Assistant — a RAG-based agent that answers questions from documents.

!!! example "Prompt"
    ```
    Create a Knowledge Assistant called "Quickstart FAQ Bot":

    1. Generate 20 sample FAQ documents (pricing, features, returns, shipping, support)
    2. Upload to UC volume main.quickstart.volumes.faq_docs
    3. Create a Vector Search endpoint and index for the documents
    4. Create the Knowledge Assistant using Foundation Model APIs
    5. Deploy to a serving endpoint
    6. System prompt: "Answer questions based only on the FAQ documents. If unsure, say so."

    Test it with: "What is your return policy?" and "How much does enterprise cost?"
    ```

!!! success "What you'll see"
    The assistant creates the knowledge base, vector index, and agent, deploys it, then runs test queries showing responses with source attribution.

<div class="step-screenshot">
<img src="../assets/step6-agent.png" alt="Agent test results">
</div>

**Alternative** — for SQL-based data Q&A, try a Genie Space instead:

!!! example "Prompt"
    ```
    Create a Genie Space called "Sales Genie" that lets users ask natural
    language questions about the quickstart tables (orders, customers, products).
    Add sample questions and curation instructions.
    ```

---

## <span class="num">7</span> Build a full-stack app <span class="dur">10 min</span>

Bring everything together in a Databricks App.

!!! example "Prompt"
    ```
    Create a Databricks App called "quickstart-explorer" with FastAPI + React (APX pattern):

    - Page 1 "Explorer": catalog/schema browser + SQL query editor with results table
    - Page 2 "Dashboard": line chart of monthly_revenue from the gold table,
      filterable by segment, auto-refreshes every 30s
    - Page 3 "Chat": chat interface connected to the FAQ Bot serving endpoint,
      with streaming responses and source document cards

    Set up app.yaml with SQL warehouse and serving endpoint resources,
    then deploy to Databricks Apps.
    ```

!!! success "What you'll see"
    The assistant scaffolds a complete project (FastAPI backend + React frontend), configures app.yaml with resource permissions, deploys it, and returns the live app URL.

<div class="step-screenshot">
<img src="../assets/step7-app.png" alt="App preview">
</div>

---

<div class="completion-banner" markdown>

## You're done.

**Data exploration** → **Pipeline** → **Dashboard** → **AI Agent** → **Full-stack App** — all through conversation.

The AI Dev Kit has [27 skills](reference/skills.md) and [50+ MCP tools](reference/mcp-tools.md). Just ask your assistant to build something — skills activate automatically.

!!! example "Ideas to try next"
    ```
    Create a scheduled Databricks job that runs my pipeline every hour
    and sends a Slack notification on failure.
    ```

    ```
    Set up MLflow evaluation for my FAQ Bot. Create 10 test questions and
    measure correctness, retrieval relevance, and faithfulness.
    ```

    ```
    Add a Lakebase PostgreSQL database to my app for storing user preferences
    and query history.
    ```

</div>

</div>
