#!/usr/bin/env python3
"""Fetch MLflow trace metrics from tracking server."""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

# API endpoint path (MLflow 3.0 API)
API_PATH = "/api/3.0/mlflow/traces/metrics"

# Default max results - MLflow server limit is 1000
DEFAULT_MAX_RESULTS = 1000

# Aggregation type codes per MLflow protobuf spec
AGG_TYPES = {"COUNT": 1, "SUM": 2, "AVG": 3, "PERCENTILE": 4, "MIN": 5, "MAX": 6}

# View type codes per MLflow protobuf spec
VIEW_TYPES = {"TRACES": 1, "SPANS": 2, "ASSESSMENTS": 3}

# Valid metrics per view type
VALID_METRICS = {
    "TRACES": ["trace_count", "latency", "input_tokens", "output_tokens", "total_tokens"],
    "SPANS": ["span_count", "latency"],
    "ASSESSMENTS": ["assessment_count", "assessment_value"],
}

# Valid dimensions per view type
VALID_DIMENSIONS = {
    "TRACES": ["trace_name", "trace_status"],
    "SPANS": ["span_name", "span_type", "span_status"],
    "ASSESSMENTS": ["assessment_name", "assessment_value"],
}

# Time unit multipliers (seconds)
TIME_UNITS = {"m": 60, "h": 3600, "d": 86400, "w": 604800}


def parse_time(time_str: str) -> int:
    """Parse time string to epoch milliseconds.

    Formats: -24h, -7d, -1w, -30m, now, ISO 8601, epoch ms
    """
    if time_str == "now":
        return int(datetime.now(timezone.utc).timestamp() * 1000)

    # Relative time: -24h, -7d, -1w, -30m
    match = re.match(r"^-(\d+)([hdwm])$", time_str)
    if match:
        value, unit = int(match.group(1)), match.group(2)
        offset_seconds = value * TIME_UNITS[unit]
        return int((datetime.now(timezone.utc).timestamp() - offset_seconds) * 1000)

    # Epoch milliseconds
    if time_str.isdigit():
        return int(time_str)

    # ISO 8601
    try:
        dt = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
        return int(dt.timestamp() * 1000)
    except ValueError:
        raise ValueError(
            f"Invalid time format: '{time_str}'. "
            f"Valid formats: relative (-24h, -7d, -30m, now), ISO 8601 (2024-01-01T00:00:00Z), epoch ms"
        )


def parse_aggregations(agg_str: str) -> list[dict]:
    """Parse aggregation string. Supports COUNT, SUM, AVG, MIN, MAX, P50, P95, etc."""
    result = []
    for agg in agg_str.split(","):
        agg = agg.strip().upper()
        if agg.startswith("P") and agg[1:].replace(".", "", 1).replace("-", "", 1).isdigit():
            percentile_value = float(agg[1:])
            if not 0 <= percentile_value <= 100:
                raise ValueError(f"Percentile must be 0-100, got: {percentile_value}")
            result.append({"aggregation_type": AGG_TYPES["PERCENTILE"], "percentile_value": percentile_value})
        elif agg in AGG_TYPES:
            result.append({"aggregation_type": AGG_TYPES[agg]})
        else:
            raise ValueError(f"Unknown aggregation: '{agg}'. Valid: {', '.join(AGG_TYPES.keys())}, P<0-100>")
    return result


def validate_metric(metric: str, view_type: str) -> None:
    """Validate metric name for view type."""
    valid = VALID_METRICS.get(view_type, [])
    if metric not in valid:
        raise ValueError(f"Invalid metric '{metric}' for {view_type}. Valid: {', '.join(valid)}")


def validate_dimensions(dimensions: list[str] | None, view_type: str) -> None:
    """Validate dimensions for view type."""
    if not dimensions:
        return
    valid = VALID_DIMENSIONS.get(view_type, [])
    for dim in dimensions:
        if dim not in valid:
            raise ValueError(f"Invalid dimension '{dim}' for {view_type}. Valid: {', '.join(valid)}")


def fetch_metrics(
    server: str,
    experiment_ids: list[str],
    metric_name: str,
    aggregations: list[dict],
    view_type: int = 1,
    dimensions: list[str] | None = None,
    filters: list[str] | None = None,
    time_interval_seconds: int | None = None,
    start_time_ms: int | None = None,
    end_time_ms: int | None = None,
    max_results: int = DEFAULT_MAX_RESULTS,
) -> dict:
    """Fetch metrics from MLflow tracking server."""
    url = f"{server.rstrip('/')}{API_PATH}"

    payload = {
        "experiment_ids": experiment_ids,
        "view_type": view_type,
        "metric_name": metric_name,
        "aggregations": aggregations,
        "max_results": max_results,
    }

    if dimensions:
        payload["dimensions"] = dimensions
    if filters:
        payload["filters"] = filters
    if time_interval_seconds:
        payload["time_interval_seconds"] = time_interval_seconds
    if start_time_ms:
        payload["start_time_ms"] = start_time_ms
    if end_time_ms:
        payload["end_time_ms"] = end_time_ms

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        try:
            err = json.loads(body)
            msg = err.get("message", body)
        except json.JSONDecodeError:
            msg = body
        raise RuntimeError(f"MLflow API error (HTTP {e.code}): {msg}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Cannot connect to {server}: {e.reason}")


def format_table(data_points: list[dict]) -> str:
    """Format data points as aligned table."""
    if not data_points:
        return "No data points found."

    first = data_points[0]
    dim_keys = list(first.get("dimensions", {}).keys())
    value_keys = list(first.get("values", {}).keys())
    headers = dim_keys + value_keys

    rows = []
    for dp in data_points:
        row = [str(dp.get("dimensions", {}).get(k, "")) for k in dim_keys]
        for k in value_keys:
            val = dp.get("values", {}).get(k)
            if val is None:
                row.append("N/A")
            elif isinstance(val, float):
                row.append(f"{val:.2f}" if val != int(val) else str(int(val)))
            else:
                row.append(str(val))
        rows.append(row)

    widths = [max(len(h), max((len(r[i]) for r in rows), default=0)) for i, h in enumerate(headers)]
    lines = [
        "  ".join(h.ljust(widths[i]) for i, h in enumerate(headers)),
        "  ".join("-" * w for w in widths),
    ]
    lines.extend("  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)) for row in rows)
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Fetch MLflow trace metrics")
    parser.add_argument("-s", "--server", required=True, help="MLflow tracking server URL")
    parser.add_argument("-x", "--experiment-ids", required=True, help="Experiment IDs (comma-separated)")
    parser.add_argument("-m", "--metric", required=True, help="Metric name")
    parser.add_argument("-a", "--aggregations", required=True, help="Aggregations: COUNT,SUM,AVG,MIN,MAX,P50,P95")
    parser.add_argument("-v", "--view-type", default="TRACES", choices=VIEW_TYPES.keys(), help="View type")
    parser.add_argument("-d", "--dimensions", help="Dimensions to group by (comma-separated)")
    parser.add_argument("-f", "--filters", help="Filter expressions (comma-separated)")
    parser.add_argument("-t", "--time-interval", type=int, help="Time bucket in seconds (3600=hourly)")
    parser.add_argument("--start-time", help="Start time: -24h, -7d, now, ISO 8601, or epoch ms")
    parser.add_argument("--end-time", help="End time: same formats as start-time")
    parser.add_argument("--max-results", type=int, default=DEFAULT_MAX_RESULTS, help="Max results")
    parser.add_argument("-o", "--output", choices=["table", "json"], default="table", help="Output format")

    args = parser.parse_args()

    try:
        # Parse and validate
        experiment_ids = [x.strip() for x in args.experiment_ids.split(",")]
        aggregations = parse_aggregations(args.aggregations)
        validate_metric(args.metric, args.view_type)

        dimensions = [x.strip() for x in args.dimensions.split(",")] if args.dimensions else None
        validate_dimensions(dimensions, args.view_type)

        filters = [x.strip() for x in args.filters.split(",")] if args.filters else None
        start_time_ms = parse_time(args.start_time) if args.start_time else None
        end_time_ms = parse_time(args.end_time) if args.end_time else None

        if args.time_interval and (not start_time_ms or not end_time_ms):
            raise ValueError("--start-time and --end-time required with --time-interval")

        result = fetch_metrics(
            server=args.server,
            experiment_ids=experiment_ids,
            metric_name=args.metric,
            aggregations=aggregations,
            view_type=VIEW_TYPES[args.view_type],
            dimensions=dimensions,
            filters=filters,
            time_interval_seconds=args.time_interval,
            start_time_ms=start_time_ms,
            end_time_ms=end_time_ms,
            max_results=args.max_results,
        )

        if args.output == "json":
            print(json.dumps(result, indent=2))
        else:
            print(format_table(result.get("data_points", [])))
            if result.get("next_page_token"):
                print(f"\nMore results available (token: {result['next_page_token']})")

    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
