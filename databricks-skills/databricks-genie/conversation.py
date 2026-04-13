#!/usr/bin/env python3
"""
Genie Conversation API - CLI interface for asking questions to Genie Spaces.

Usage:
    python conversation.py ask SPACE_ID "What were total sales last month?"
    python conversation.py ask SPACE_ID "Break that down by region" --conversation-id CONV_ID
    python conversation.py ask SPACE_ID "Complex query" --timeout 120

Requires: databricks-sdk package
"""

import argparse
import json
import sys
import time
from typing import Any, Dict, Optional

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.dashboards import GenieMessage


def ask_genie(
    space_id: str,
    question: str,
    conversation_id: Optional[str] = None,
    timeout_seconds: int = 60,
) -> Dict[str, Any]:
    """Ask a question to a Genie Space.

    Args:
        space_id: The Genie Space ID
        question: Natural language question to ask
        conversation_id: Optional conversation ID for follow-up questions
        timeout_seconds: Maximum time to wait for response (default: 60)

    Returns:
        Dict with question, conversation_id, message_id, status, sql, columns, data, row_count
    """
    client = WorkspaceClient()

    # Start or continue conversation
    if conversation_id:
        response = client.genie.start_conversation_and_wait(
            space_id=space_id,
            content=question,
            conversation_id=conversation_id,
        )
    else:
        response = client.genie.start_conversation_and_wait(
            space_id=space_id,
            content=question,
        )

    # Extract conversation and message IDs
    conv_id = response.conversation_id if hasattr(response, 'conversation_id') else None
    msg_id = response.message_id if hasattr(response, 'message_id') else None

    # Poll for completion
    start_time = time.time()
    while True:
        if time.time() - start_time > timeout_seconds:
            return {
                "question": question,
                "conversation_id": conv_id,
                "message_id": msg_id,
                "status": "TIMEOUT",
                "error": f"Query timed out after {timeout_seconds} seconds",
            }

        # Get message details
        message = client.genie.get_message(
            space_id=space_id,
            conversation_id=conv_id,
            message_id=msg_id,
        )

        status = message.status.value if hasattr(message.status, 'value') else str(message.status)

        if status == "COMPLETED":
            # Extract results
            result = {
                "question": question,
                "conversation_id": conv_id,
                "message_id": msg_id,
                "status": "COMPLETED",
            }

            # Get SQL and data from attachments
            if message.attachments:
                for attachment in message.attachments:
                    if hasattr(attachment, 'query') and attachment.query:
                        result["sql"] = attachment.query.query
                    if hasattr(attachment, 'text') and attachment.text:
                        result["text_response"] = attachment.text.content

            # Get query result if available
            if hasattr(message, 'query_result') and message.query_result:
                qr = message.query_result
                if hasattr(qr, 'columns'):
                    result["columns"] = [c.name for c in qr.columns]
                if hasattr(qr, 'data_array'):
                    result["data"] = qr.data_array
                    result["row_count"] = len(qr.data_array)

            return result

        elif status in ["FAILED", "CANCELLED"]:
            error_msg = ""
            if message.attachments:
                for attachment in message.attachments:
                    if hasattr(attachment, 'text') and attachment.text:
                        error_msg = attachment.text.content
            return {
                "question": question,
                "conversation_id": conv_id,
                "message_id": msg_id,
                "status": status,
                "error": error_msg or f"Query {status.lower()}",
            }

        # Still processing, wait and retry
        time.sleep(2)


def _print_json(data: Any) -> None:
    """Print data as formatted JSON."""
    print(json.dumps(data, indent=2, default=str))


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Ask questions to a Genie Space",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # ask command
    ask_parser = subparsers.add_parser("ask", help="Ask a question to a Genie Space")
    ask_parser.add_argument("space_id", help="The Genie Space ID")
    ask_parser.add_argument("question", help="Natural language question to ask")
    ask_parser.add_argument(
        "--conversation-id", "-c",
        help="Conversation ID for follow-up questions",
    )
    ask_parser.add_argument(
        "--timeout", "-t",
        type=int,
        default=60,
        help="Timeout in seconds (default: 60)",
    )

    args = parser.parse_args()

    if args.command == "ask":
        result = ask_genie(
            space_id=args.space_id,
            question=args.question,
            conversation_id=args.conversation_id,
            timeout_seconds=args.timeout,
        )
        _print_json(result)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
