"""
Slack Operations via Databricks UC Connection

Uses the Databricks SQL `http_request` function with a Unity Catalog
connection named "slack" to call the Slack Web API. All authentication
is handled by the UC connection's OAuth U2M mapping.
"""

import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_CONNECTION_NAME = "slack"


def _slack_api_call(
    method: str,
    path: str,
    body: Optional[Dict[str, Any]] = None,
    connection_name: str = DEFAULT_CONNECTION_NAME,
    warehouse_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Make an authenticated Slack API call via http_request and a UC connection.

    Args:
        method: HTTP method (GET or POST)
        path: Slack API path (e.g., "/chat.postMessage")
        body: JSON body for POST requests
        connection_name: UC connection name (default: "slack")
        warehouse_id: Optional SQL warehouse ID

    Returns:
        Parsed Slack API response dict.

    Raises:
        RuntimeError: If the HTTP call or Slack API returns an error.
    """
    from .sql.sql import execute_sql

    if method.upper() == "GET":
        sql = (
            f"SELECT http_request("
            f"  conn => '{connection_name}', "
            f"  method => 'GET', "
            f"  path => '{path}'"
            f") AS response"
        )
    else:
        body_json = json.dumps(body or {}).replace("'", "\\'")
        sql = (
            f"SELECT http_request("
            f"  conn => '{connection_name}', "
            f"  method => 'POST', "
            f"  path => '{path}', "
            f"  json => '{body_json}'"
            f") AS response"
        )

    rows = execute_sql(sql_query=sql, warehouse_id=warehouse_id)
    if not rows:
        raise RuntimeError("http_request returned no rows")

    raw = rows[0].get("response") or rows[0].get("RESPONSE")
    if raw is None:
        raise RuntimeError(f"Unexpected http_request result: {rows[0]}")

    if isinstance(raw, str):
        resp = json.loads(raw)
    elif isinstance(raw, dict):
        resp = raw
    else:
        raise RuntimeError(f"Unexpected response type: {type(raw)}")

    status_code = resp.get("status_code", 200)
    resp_body = resp.get("body", resp)
    if isinstance(resp_body, str):
        resp_body = json.loads(resp_body)

    if status_code >= 400:
        raise RuntimeError(f"Slack API returned HTTP {status_code}: {resp_body}")

    if isinstance(resp_body, dict) and not resp_body.get("ok", True):
        error = resp_body.get("error", "unknown_error")
        raise RuntimeError(f"Slack API error: {error}")

    return resp_body


def slack_list_channels(
    limit: int = 100,
    cursor: Optional[str] = None,
    connection_name: str = DEFAULT_CONNECTION_NAME,
    warehouse_id: Optional[str] = None,
) -> Dict[str, Any]:
    """List public or pre-defined channels in the workspace.

    Args:
        limit: Max channels to return (default 100, max 200)
        cursor: Pagination cursor for next page
        connection_name: UC connection name
        warehouse_id: Optional SQL warehouse ID

    Returns:
        Dict with channels list and pagination metadata.
    """
    path = f"/conversations.list?types=public_channel&limit={min(limit, 200)}&exclude_archived=true"
    if cursor:
        path += f"&cursor={cursor}"
    return _slack_api_call("GET", path, connection_name=connection_name, warehouse_id=warehouse_id)


def slack_get_channel_history(
    channel_id: str,
    limit: int = 10,
    connection_name: str = DEFAULT_CONNECTION_NAME,
    warehouse_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Get recent messages from a channel.

    Args:
        channel_id: The Slack channel ID
        limit: Number of messages to retrieve (default 10)
        connection_name: UC connection name
        warehouse_id: Optional SQL warehouse ID

    Returns:
        Dict with messages list.
    """
    path = f"/conversations.history?channel={channel_id}&limit={limit}"
    return _slack_api_call("GET", path, connection_name=connection_name, warehouse_id=warehouse_id)


def slack_post_message(
    channel_id: str,
    text: str,
    connection_name: str = DEFAULT_CONNECTION_NAME,
    warehouse_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Post a new message to a Slack channel.

    Args:
        channel_id: The Slack channel ID
        text: Message text to post
        connection_name: UC connection name
        warehouse_id: Optional SQL warehouse ID

    Returns:
        Dict with posted message details.
    """
    return _slack_api_call(
        "POST",
        "/chat.postMessage",
        body={"channel": channel_id, "text": text},
        connection_name=connection_name,
        warehouse_id=warehouse_id,
    )


def slack_reply_to_thread(
    channel_id: str,
    thread_ts: str,
    text: str,
    connection_name: str = DEFAULT_CONNECTION_NAME,
    warehouse_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Reply to a specific message thread in Slack.

    Args:
        channel_id: The Slack channel ID
        thread_ts: Timestamp of the parent message (e.g., '1234567890.123456')
        text: The reply text
        connection_name: UC connection name
        warehouse_id: Optional SQL warehouse ID

    Returns:
        Dict with posted reply details.
    """
    return _slack_api_call(
        "POST",
        "/chat.postMessage",
        body={"channel": channel_id, "thread_ts": thread_ts, "text": text},
        connection_name=connection_name,
        warehouse_id=warehouse_id,
    )


def slack_add_reaction(
    channel_id: str,
    timestamp: str,
    reaction: str,
    connection_name: str = DEFAULT_CONNECTION_NAME,
    warehouse_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Add a reaction emoji to a message.

    Args:
        channel_id: The Slack channel ID
        timestamp: Timestamp of the message to react to
        reaction: Emoji name without colons (e.g., 'thumbsup')
        connection_name: UC connection name
        warehouse_id: Optional SQL warehouse ID

    Returns:
        Dict with reaction result.
    """
    return _slack_api_call(
        "POST",
        "/reactions.add",
        body={"channel": channel_id, "timestamp": timestamp, "name": reaction},
        connection_name=connection_name,
        warehouse_id=warehouse_id,
    )


def slack_get_thread_replies(
    channel_id: str,
    thread_ts: str,
    connection_name: str = DEFAULT_CONNECTION_NAME,
    warehouse_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Get all replies in a message thread.

    Args:
        channel_id: The Slack channel ID
        thread_ts: Timestamp of the parent message
        connection_name: UC connection name
        warehouse_id: Optional SQL warehouse ID

    Returns:
        Dict with messages in the thread.
    """
    path = f"/conversations.replies?channel={channel_id}&ts={thread_ts}"
    return _slack_api_call("GET", path, connection_name=connection_name, warehouse_id=warehouse_id)


def slack_get_users(
    limit: int = 100,
    cursor: Optional[str] = None,
    connection_name: str = DEFAULT_CONNECTION_NAME,
    warehouse_id: Optional[str] = None,
) -> Dict[str, Any]:
    """List users in the workspace.

    Args:
        limit: Max users to return (default 100, max 200)
        cursor: Pagination cursor
        connection_name: UC connection name
        warehouse_id: Optional SQL warehouse ID

    Returns:
        Dict with members list.
    """
    path = f"/users.list?limit={min(limit, 200)}"
    if cursor:
        path += f"&cursor={cursor}"
    return _slack_api_call("GET", path, connection_name=connection_name, warehouse_id=warehouse_id)


def slack_get_user_profile(
    user_id: str,
    connection_name: str = DEFAULT_CONNECTION_NAME,
    warehouse_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Get detailed profile for a specific user.

    Args:
        user_id: The Slack user ID
        connection_name: UC connection name
        warehouse_id: Optional SQL warehouse ID

    Returns:
        Dict with user profile information.
    """
    path = f"/users.info?user={user_id}"
    return _slack_api_call("GET", path, connection_name=connection_name, warehouse_id=warehouse_id)


def slack_search_messages(
    query: str,
    count: int = 20,
    connection_name: str = DEFAULT_CONNECTION_NAME,
    warehouse_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Search for messages matching a query.

    Args:
        query: Search query string
        count: Number of results to return (default 20)
        connection_name: UC connection name
        warehouse_id: Optional SQL warehouse ID

    Returns:
        Dict with search results.
    """
    from urllib.parse import quote
    encoded_query = quote(query)
    path = f"/search.messages?query={encoded_query}&count={count}"
    return _slack_api_call("GET", path, connection_name=connection_name, warehouse_id=warehouse_id)
