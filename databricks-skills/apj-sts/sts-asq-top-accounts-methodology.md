# STS ASQ Top Accounts — Identification & Presentation Methodology

This document describes how to identify and visualise the top 3 customer accounts for a given sub-region that have received Shared Technical Services (STS) ASQ support and shown consistent month-on-month Databricks consumption growth.

---

## 1. Identify the STS Team Members for the Region


### APJ STS Team Members (as of Mar 2026)

| Name | Coverage |
|---|---|
| Louis Chen | All APJ regions |
| Pui-Ching Lee | All APJ regions |
| Adarsh Nandan | All APJ regions |
| Hemapriya N | All APJ regions |
| Kavya Parasher | All APJ regions |
| Simran Vanjani | All APJ regions |
| Haley Won | Japan, Korea |
| Yotaro Enomoto | Japan only |
| Anwesha Ghosh | All APJ regions |
| Hemanth Rishi | All APJ regions |

---

## 2. Find ASQs Delivered by the Sub-Region Team

ASQs are stored as `approvalrequest__c` records in Salesforce. The relevant RecordType IDs for STS are:

| RecordType | ID |
|---|---|
| Shared Technical Services | `0128Y000001h44DQAQ` |

Query ASQs owned by the sub-region team members within the last 6 months:

```sql
SELECT ar.Name, ar.Account__c, ar.OwnerId, ar.Status__c,
       ar.Request_Description__c, ar.Request_Closure_Note__c,
       u.Name as OwnerName, u.User_Sub_Region__c
FROM main.sfdc_bronze.approvalrequest__c ar
JOIN main.sfdc_bronze.user u ON ar.OwnerId = u.Id
  AND u.processDate = (SELECT MAX(processDate) FROM main.sfdc_bronze.user)
WHERE ar.RecordTypeId IN ('0128Y000001h44DQAQ')
  AND ar.Status__c = 'Completed'
  AND u.User_Sub_Region__c = '<sub_region>'   -- e.g. 'ANZ'
  AND ar.processDate = (SELECT MAX(processDate) FROM main.sfdc_bronze.approvalrequest__c)
  AND ar.CreatedDate >= DATEADD(MONTH, -6, CURRENT_DATE())
```

Collect the distinct `Account__c` IDs for accounts that received an ASQ.

---

## 3. Pull Monthly Consumption for Those Accounts

Use `main.fin_live_gold.paid_usage_metering` — the source of truth for Databricks billing data.

```sql
SELECT
  sfdc_account_id,
  DATE_TRUNC('month', date) AS month,
  SUM(usage_dollars) AS monthly_dollars
FROM main.fin_live_gold.paid_usage_metering
WHERE sfdc_account_id IN (<comma_separated_account_ids>)
  AND date >= DATEADD(MONTH, -6, DATE_TRUNC('month', CURRENT_DATE()))
  AND date < DATE_TRUNC('month', CURRENT_DATE())   -- exclude current incomplete month
GROUP BY 1, 2
ORDER BY 1, 2
```

> **Note:** Always exclude the current month using `date < DATE_TRUNC('month', CURRENT_DATE())`. Mid-month data will understate consumption and produce false MoM declines, distorting growth scoring and the chart.

---

## 4. Score Accounts for Consistent MoM Growth

For each account, count the number of month-over-month transitions where consumption increased. Rank by:

1. **growth_months** — number of MoM transitions with positive growth (out of 5 for a 6-month window)
2. **recent_consecutive_months** — longest streak of growth ending in the most recent month
3. **latest_month_dollars** — Feb consumption as a tiebreaker

Accounts with 4 or 5 out of 5 growth months qualify. Select the top 3.

---

## 5. Retrieve Supporting Account Metadata

For each of the top 3 accounts, pull:

**Account Owner** (from `sfdc_bronze.account`):
```sql
SELECT a.Id, a.Name, u.Name as AccountOwner
FROM main.sfdc_bronze.account a
JOIN main.sfdc_bronze.user u ON a.OwnerId = u.Id
  AND u.processDate = (SELECT MAX(processDate) FROM main.sfdc_bronze.user)
WHERE a.Id IN (<account_ids>)
  AND a.processDate = (SELECT MAX(processDate) FROM main.sfdc_bronze.account)
```

**Primary SA** (from `sfdc_bronze.accountteammember`):
```sql
SELECT atm.AccountId, u.Name as PrimarySA
FROM main.sfdc_bronze.accountteammember atm
JOIN main.sfdc_bronze.user u ON atm.UserId = u.Id
  AND u.processDate = (SELECT MAX(processDate) FROM main.sfdc_bronze.user)
WHERE atm.AccountId IN (<account_ids>)
  AND atm.TeamMemberRole LIKE '%Scale Solution%'
  AND atm.processDate = (SELECT MAX(processDate) FROM main.sfdc_bronze.accountteammember)
  AND atm.IsDeleted = false
```

**ASQ Activity Summary** — use `Request_Closure_Note__c` for activities delivered (prefer over `Request_Description__c` which captures the request intent, not the outcome). Where the closure note is absent or terse, fall back to `Request_Description__c`.

```sql
SELECT ar.Name as asq_name, ar.Account__c, ar.Request_Closure_Note__c,
       ar.Request_Description__c, CAST(ar.CreatedDate AS DATE) as created_date,
       u.Name as owner_name
FROM main.sfdc_bronze.approvalrequest__c ar
JOIN main.sfdc_bronze.user u ON ar.OwnerId = u.Id
  AND u.processDate = (SELECT MAX(processDate) FROM main.sfdc_bronze.user)
WHERE ar.Account__c IN (<top_3_account_ids>)
  AND ar.RecordTypeId IN ('0128Y000001h44DQAQ')
  AND ar.Status__c IN ('Complete', 'Completed')
  AND ar.processDate = (SELECT MAX(processDate) FROM main.sfdc_bronze.approvalrequest__c)
  AND ar.CreatedDate >= DATEADD(MONTH, -6, CURRENT_DATE())
ORDER BY ar.Account__c, ar.CreatedDate DESC
```

Summarise the `Request_Closure_Note__c` into 2–3 concise sentences focused on what was done and the customer outcome. These are displayed in the account card on the visualisation.

---

## 6. Visualise with Chart.js

Build an HTML page with an inline Chart.js line chart (v4.4.0). Key design choices:

- **X-axis:** months (e.g. Sep-25 to Feb-26), labelled `"Month"`, excluding current incomplete month
- **Y-axis:** monthly consumption in USD, labelled `"$ Consumption (USD)"`, formatted with `$` prefix and `k`/`M` suffixes
- **One line per account**, colour-coded to match their card below the chart
- **ASQ annotations:** custom Chart.js plugin drawing dashed vertical lines at the month the ASQ was executed. The **ASQ number (AR-XXXXXXXXX) must always be visible on the chart** — render it as a permanent label inside the callout box regardless of hover state

### Axis Configuration

```js
scales: {
  x: {
    title: { display: true, text: 'Month', font: { size: 13 } }
  },
  y: {
    title: { display: true, text: '$ Consumption (USD)', font: { size: 13 } },
    ticks: {
      callback: v => v >= 1_000_000 ? `$${(v/1_000_000).toFixed(1)}M`
                   : v >= 1_000     ? `$${(v/1_000).toFixed(0)}k`
                   : `$${v}`
    }
  }
}
```

### ASQ Annotation Plugin (custom)

The ASQ number must be rendered as a **persistent on-chart label** — never hidden behind a tooltip or hover interaction. Each annotation callout box must display the AR number prominently.

```js
const asqPlugin = {
  id: 'asqAnnotations',
  afterDraw(chart) {
    const ctx = chart.ctx;
    const xScale = chart.scales.x;
    const yScale = chart.scales.y;
    asqAnnotations.forEach(ann => {
      const x = xScale.getPixelForValue(ann.xIndex);
      // draw dashed vertical line
      ctx.save();
      ctx.setLineDash([4, 4]);
      ctx.strokeStyle = ann.color;
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.moveTo(x, yScale.top);
      ctx.lineTo(x, yScale.bottom);
      ctx.stroke();
      // draw callout box — always show AR number
      const label = ann.arNumber;   // e.g. "AR-000102330"
      const boxY = yScale.top + (yScale.bottom - yScale.top) * ann.yFrac;
      ctx.setLineDash([]);
      ctx.fillStyle = ann.color;
      ctx.font = 'bold 11px sans-serif';
      const w = ctx.measureText(label).width + 12;
      ctx.fillRect(x - w / 2, boxY - 10, w, 20);
      ctx.fillStyle = '#fff';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(label, x, boxY);
      ctx.restore();
    });
  }
};
```

> **Requirement:** The ASQ number (AR-XXXXXXXXX) must always be visible on the rendered chart — do not rely on hover or tooltip interactions to surface it.

### Account Cards (below the chart)

Each card shows:
- Rank (#1, #2, #3) and account name in the account's colour
- ASQ number and growth indicator (e.g. `5/5 months growing ↑`)
- Most recent completed month's consumption in large text
- **Account Owner** and **Primary SA** — sourced from `sfdc_bronze.account` and `sfdc_bronze.accountteammember` respectively, displayed side-by-side under small `ACCOUNT OWNER` / `PRIMARY SA` labels
- **STS Engineer** — the `OwnerId` → `u.Name` from the ASQ record (i.e. the STS team member who delivered the engagement), displayed under a `STS ENGINEER` label alongside Account Owner and Primary SA
- **Activities Delivered** — 2–3 sentence summary derived from `Request_Closure_Note__c`

---

## 7. Validate SKU Alignment (Optional)

To confirm consumption growth is coming from SKUs aligned with the ASQ activity, break down consumption by `product_type`:

```sql
SELECT
  sfdc_account_id,
  DATE_TRUNC('month', date) AS month,
  product_type,
  SUM(usage_dollars) AS dollars
FROM main.fin_live_gold.paid_usage_metering
WHERE sfdc_account_id IN (<account_ids>)
  AND date >= '2025-09-01'
GROUP BY 1, 2, 3
ORDER BY 1, 2, 4 DESC
```

Cross-reference against the ASQ activity type:

| ASQ Activity | Expected SKU Growth |
|---|---|
| Genie Space setup | `INTERACTIVE` (DBSQL) |
| Private Link / Networking | Broad-based (any SKU) |
| Pipeline / Ingestion | `DLT` (billed as SDP in product, still labelled DLT in billing data) |
| ML / Model Serving | `MODEL_INFERENCE` |

> **Note:** The `fin_live_gold` billing data still uses `product_type = 'DLT'` for Lakeflow Declarative Pipelines (formerly DLT / SDP). This is a data pipeline label — the rebranding has not yet propagated to billing. Raise with `#eng-money-team` if this needs updating.

---

## Tools Used

| Tool | Purpose |
|---|---|
| Logfood (`--profile=logfood`) | All SQL queries against `sfdc_bronze`, `fin_live_gold` |
| Databricks SQL Statements API | Query execution endpoint |
| Chart.js 4.4.0 (inlined) | Consumption line chart with custom annotation plugin |
| Chrome DevTools MCP | Render and screenshot the HTML page |

Chart.js must be **inlined** in the HTML (not loaded from CDN) when rendering via `file://` pages, as CDN requests are blocked. Download with:

```bash
curl -L https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js -o /tmp/chart.min.js
```

Then inject into the HTML template using Python string replacement before opening in the browser.

---

## Example Results — ANZ (Mar 2026)

Executed against ANZ STS team (Louis Chen, Pui-Ching Lee). Analysis window: Sep 2025 – Feb 2026.

| Rank | Account | ASQ | Growth | Feb-26 | Account Owner | Primary SA |
|---|---|---|---|---|---|---|
| #1 | AGL Energy | AR-000102330 (Nov-25) | 5/5 ↑ | $32,788 | Neil Carter | David O'Keeffe |
| #2 | Barrenjoey Services | AR-000098921 (Oct-25) | 4/5 ↑ | $17,872 | Felix Clemens | Sierra Yap |
| #3 | Australian Radio Network | AR-000097588 (Oct-25) | 4/5 ↑ | $13,318 | Chris Bohane | Alex Feng |

### Activities Delivered

**AGL Energy (AR-000102330):**
Reviewed and validated a custom hub-and-spoke networking architecture to support both front-end and back-end Private Link within a constrained /15 Azure subnet. Worked with the customer's networking team to resolve all open questions.

**Barrenjoey Services (AR-000098921):**
Engaged Launch Accelerator team to build a Genie Space on structured financial market data (client trade inquiries) as a blueprint for 20 planned Genie Spaces. Set up bronze/silver tables and SQL example queries for natural language access by non-technical sales users.

**Australian Radio Network (AR-000097588):**
Validated hub-and-spoke architecture with full Private Link. Configured back-end private link and provided documentation to implement front-end private link and NCC. Production-ready workspace stood up on Azure.
