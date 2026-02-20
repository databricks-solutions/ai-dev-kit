#!/usr/bin/env python3
"""
Run a single benchmark question against a Databricks Genie Space.

Usage: python run_benchmark.py <space_id> <question>
Output: JSON to stdout
Exit codes: 0 = result available (success or Genie-level failure), 1 = script-level error (stderr)

Requires:
  - databricks-sdk >= 0.85 (pip install "databricks-sdk>=0.85")
  - Databricks CLI profile configured (databricks configure)
  - CAN EDIT permission on the target Genie Space
"""

import json
import sys
import time
from datetime import timedelta


def run_benchmark(space_id: str, question: str) -> dict:
    """Send a question to Genie and return the structured result."""
    try:
        from databricks.sdk import WorkspaceClient
        from databricks.sdk.service.dashboards import MessageStatus
    except ImportError:
        print(
            'Error: databricks-sdk is not installed. Run: pip install "databricks-sdk>=0.85"',
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        client = WorkspaceClient()
    except Exception as e:
        print(
            f"Error: Failed to initialize Databricks client. "
            f"Ensure your CLI profile is configured (databricks configure).\n{e}",
            file=sys.stderr,
        )
        sys.exit(1)

    result = {
        "space_id": space_id,
        "question": question,
        "status": None,
        "generated_sql": None,
        "query_description": None,
        "text_response": None,
        "error": None,
    }

    try:
        start = client.genie.start_conversation(
            space_id=space_id,
            content=question,
        )
    except Exception as e:
        error_msg = str(e)
        if "PERMISSION_DENIED" in error_msg or "403" in error_msg:
            print(
                f"Error: Permission denied on space '{space_id}'.",
                file=sys.stderr,
            )
            sys.exit(1)
        if "NOT_FOUND" in error_msg or "404" in error_msg:
            print(
                f"Error: Genie Space '{space_id}' not found.",
                file=sys.stderr,
            )
            sys.exit(1)
        result["status"] = "ERROR"
        result["error"] = f"SDK error: {error_msg}"
        return result

    conversation_id = start.response.conversation_id
    message_id = start.response.message_id
    deadline = time.time() + timedelta(minutes=5).total_seconds()
    sleep_seconds = 1
    message = None
    active_statuses = {
        MessageStatus.SUBMITTED,
        MessageStatus.ASKING_AI,
        MessageStatus.FETCHING_METADATA,
        MessageStatus.FILTERING_CONTEXT,
        MessageStatus.PENDING_WAREHOUSE,
        MessageStatus.EXECUTING_QUERY,
    }

    while time.time() < deadline:
        try:
            message = client.genie.get_message(
                space_id=space_id,
                conversation_id=conversation_id,
                message_id=message_id,
            )
        except Exception as e:
            result["status"] = "ERROR"
            result["error"] = f"SDK error while polling message: {e}"
            return result

        if message.status == MessageStatus.COMPLETED:
            result["status"] = "COMPLETED"
            break

        if message.status == MessageStatus.FAILED:
            result["status"] = "FAILED"
            result["error"] = (
                message.error.message if message.error else "Unknown Genie error"
            )
            return result

        if message.status in active_statuses:
            time.sleep(min(sleep_seconds, 10))
            sleep_seconds += 1
            continue

        result["status"] = "ERROR"
        result["error"] = (
            f"Genie returned terminal status '{message.status}' before completion"
        )
        return result

    if result["status"] is None:
        result["status"] = "TIMEOUT"
        result["error"] = "Genie did not respond within 5 minutes"
        return result

    if message.attachments:
        for attachment in message.attachments:
            if attachment.query and attachment.query.query:
                result["generated_sql"] = attachment.query.query
                if attachment.query.description:
                    result["query_description"] = attachment.query.description
                break
            if attachment.text and attachment.text.content:
                result["text_response"] = attachment.text.content

    return result


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(
            "Usage: python run_benchmark.py <space_id> <question>",
            file=sys.stderr,
        )
        sys.exit(1)

    output = run_benchmark(sys.argv[1], sys.argv[2])
    print(json.dumps(output, indent=2, ensure_ascii=False))
