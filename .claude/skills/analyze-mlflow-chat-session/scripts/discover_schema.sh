#!/bin/bash
# Discover the input/output schema from the first trace in a session.
#
# Usage: bash discover_schema.sh <EXPERIMENT_ID> <SESSION_ID>

set -euo pipefail

EXPERIMENT_ID="$1"
SESSION_ID="$2"

# Find the first trace ID in the session
mlflow traces search \
  --experiment-id "$EXPERIMENT_ID" \
  --filter-string 'metadata.`mlflow.trace.session` = "'"$SESSION_ID"'"' \
  --order-by "timestamp_ms ASC" \
  --extract-fields 'info.trace_id' \
  --output json \
  --max-results 1 > first_trace.json

TRACE_ID=$(cat first_trace.json | jq -r '.traces[0].info.trace_id')
echo "First trace ID: $TRACE_ID"

# Fetch the full trace detail (always outputs JSON, no --output flag needed)
mlflow traces get \
  --trace-id "$TRACE_ID" > trace_detail.json

echo ""
echo "=== Root span attribute keys ==="
cat trace_detail.json | jq '.data.spans[] | select(.parent_span_id == null) | .attributes | keys'

echo ""
echo "=== Root span inputs ==="
cat trace_detail.json | jq '.data.spans[] | select(.parent_span_id == null) | .attributes["mlflow.spanInputs"]'

echo ""
echo "=== Root span outputs ==="
cat trace_detail.json | jq '.data.spans[] | select(.parent_span_id == null) | .attributes["mlflow.spanOutputs"]'
