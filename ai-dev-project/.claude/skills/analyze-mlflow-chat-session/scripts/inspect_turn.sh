#!/bin/bash
# Inspect a specific turn (trace) in detail.
#
# Usage: bash inspect_turn.sh <TRACE_ID>

set -euo pipefail

TRACE_ID="$1"

# Fetch the full trace (always outputs JSON, no --output flag needed)
mlflow traces get \
  --trace-id "$TRACE_ID" > turn_detail.json

echo "=== All spans ==="
cat turn_detail.json | jq '.data.spans[] | {name: .name, status: .status.code, parent_span_id: .parent_span_id}'

echo ""
echo "=== Error spans ==="
cat turn_detail.json | jq '.data.spans[] | select(.status.code != "STATUS_CODE_OK")'

echo ""
echo "=== Assessments ==="
cat turn_detail.json | jq '.info.assessments'
