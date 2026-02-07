# SQL Alerts Resources for Databricks Asset Bundles

## Critical: Schema Validation First

**ALWAYS start by inspecting the schema:**
```bash
databricks bundle schema | grep -A 100 'sql.AlertV2'
```

The Alert v2 API schema differs significantly from other resources. Don't assume field names.

## Common Schema Mistakes to Avoid

### ❌ WRONG - These fields don't exist:
```yaml
condition:                    # Should be "evaluation"
  op: LESS_THAN
  operand:
    column:                   # Wrong nesting
      name: "r"

schedule:
  cron_schedule:              # Should be direct fields under schedule
    quartz_cron_expression: "..."

subscriptions:                # Should be under evaluation.notification
  - destination_type: "EMAIL"
```

### ✅ CORRECT - Alerts v2 API structure:
```yaml
evaluation:                   # Not "condition"
  comparison_operator: 'LESS_THAN_OR_EQUAL'
  source:                     # Not nested under "operand.column"
    name: 'column_name'
    display: 'column_name'
  threshold:
    value:
      double_value: 100
  notification:               # Subscriptions nested here
    notify_on_ok: false
    subscriptions:
      - user_email: "${workspace.current_user.userName}"

schedule:                     # Fields directly under schedule
  pause_status: 'UNPAUSED'    # REQUIRED
  quartz_cron_schedule: '0 38 16 * * ?'  # REQUIRED
  timezone_id: 'America/Los_Angeles'     # REQUIRED
```

## Alert Trigger Logic

**Critical:** Alerts trigger when condition evaluates to **TRUE**, not FALSE.

**Wrong approach:** Using `GREATER_THAN` and expecting alert when condition is false
**Correct approach:** Use the operator that directly matches your intent

### Example: Alert when count is NOT > 100 (i.e., ≤ 100)
```yaml
# ❌ WRONG - This triggers when count IS > 100
comparison_operator: 'GREATER_THAN'

# ✅ CORRECT - This triggers when count IS <= 100
comparison_operator: 'LESS_THAN_OR_EQUAL'
```

## Email Notifications

```yaml
evaluation:
  notification:
    subscriptions:
      - user_email: "${workspace.current_user.userName}"
```

## Quartz Cron

Format: `second minute hour day-of-month month day-of-week` (use `?` for day-of-week with `*` day-of-month)

Examples: `'0 0 9 * * ?'` (9 AM daily), `'0 */30 * * * ?'` (every 30 min)

## Required Fields

```yaml
resources:
  alerts:
    alert_name:
      display_name: "[${bundle.target}] Alert Name"     # REQUIRED
      query_text: "SELECT count(*) c FROM table"        # REQUIRED
      warehouse_id: ${var.warehouse_id}                 # REQUIRED

      evaluation:                                        # REQUIRED
        comparison_operator: 'LESS_THAN'                # REQUIRED
        source:                                          # REQUIRED
          name: 'c'
          display: 'c'
        threshold:
          value:
            double_value: 100
        notification:
          notify_on_ok: false
          subscriptions:
            - user_email: "${workspace.current_user.userName}"

      schedule:                                          # REQUIRED
        pause_status: 'UNPAUSED'                        # REQUIRED
        quartz_cron_schedule: '0 0 9 * * ?'            # REQUIRED
        timezone_id: 'America/Los_Angeles'             # REQUIRED

      permissions:
        - level: CAN_RUN
          group_name: "users"
```

## Comparison Operators

`EQUAL`, `NOT_EQUAL`, `GREATER_THAN`, `GREATER_THAN_OR_EQUAL`, `LESS_THAN`, `LESS_THAN_OR_EQUAL`

## Permission Levels

`CAN_READ`, `CAN_RUN` (recommended), `CAN_EDIT`, `CAN_MANAGE`
