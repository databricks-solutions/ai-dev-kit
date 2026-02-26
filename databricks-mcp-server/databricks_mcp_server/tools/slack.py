"""Slack MCP Tools — interact with Slack via a Databricks UC connection.

Uses the ``http_request`` SQL function with a Unity Catalog connection
named "slack" to call the Slack Web API.  All OAuth authentication is
managed by the UC connection.
"""

from typing import Any, Dict, List, Optional

from databricks_tools_core.slack import (
    slack_list_channels as _list_channels,
    slack_get_channel_history as _get_channel_history,
    slack_post_message as _post_message,
    slack_reply_to_thread as _reply_to_thread,
    slack_add_reaction as _add_reaction,
    slack_get_thread_replies as _get_thread_replies,
    slack_get_users as _get_users,
    slack_get_user_profile as _get_user_profile,
    slack_search_messages as _search_messages,
)

from ..server import mcp


@mcp.tool
def slack_list_channels(
    limit: int = 100,
    cursor: str = None,
) -> Dict[str, Any]:
    """List public or pre-defined channels in the Slack workspace with pagination.

    Args:
        limit: Maximum number of channels to return (default 100, max 200)
        cursor: Pagination cursor for next page of results

    Returns:
        Dict with channels list and response_metadata for pagination.
    """
    return _list_channels(limit=limit, cursor=cursor)


@mcp.tool
def slack_get_channel_history(
    channel_id: str,
    limit: int = 10,
) -> Dict[str, Any]:
    """Get recent messages from a Slack channel.

    Args:
        channel_id: The ID of the channel
        limit: Number of messages to retrieve (default 10)

    Returns:
        Dict with messages list.
    """
    return _get_channel_history(channel_id=channel_id, limit=limit)


@mcp.tool
def slack_post_message(
    channel_id: str,
    text: str,
) -> Dict[str, Any]:
    """Post a new message to a Slack channel.

    Args:
        channel_id: The ID of the channel to post to
        text: The message text to post

    Returns:
        Dict with posted message details.
    """
    return _post_message(channel_id=channel_id, text=text)


@mcp.tool
def slack_reply_to_thread(
    channel_id: str,
    thread_ts: str,
    text: str,
) -> Dict[str, Any]:
    """Reply to a specific message thread in Slack.

    Args:
        channel_id: The ID of the channel containing the thread
        thread_ts: The timestamp of the parent message (format: '1234567890.123456')
        text: The reply text

    Returns:
        Dict with posted reply details.
    """
    return _reply_to_thread(channel_id=channel_id, thread_ts=thread_ts, text=text)


@mcp.tool
def slack_add_reaction(
    channel_id: str,
    timestamp: str,
    reaction: str,
) -> Dict[str, Any]:
    """Add a reaction emoji to a Slack message.

    Args:
        channel_id: The ID of the channel containing the message
        timestamp: The timestamp of the message to react to
        reaction: The name of the emoji reaction (without colons)

    Returns:
        Dict with reaction result.
    """
    return _add_reaction(channel_id=channel_id, timestamp=timestamp, reaction=reaction)


@mcp.tool
def slack_get_thread_replies(
    channel_id: str,
    thread_ts: str,
) -> Dict[str, Any]:
    """Get all replies in a Slack message thread.

    Args:
        channel_id: The ID of the channel containing the thread
        thread_ts: The timestamp of the parent message (format: '1234567890.123456')

    Returns:
        Dict with messages in the thread.
    """
    return _get_thread_replies(channel_id=channel_id, thread_ts=thread_ts)


@mcp.tool
def slack_get_users(
    limit: int = 100,
    cursor: str = None,
) -> Dict[str, Any]:
    """Get a list of all users in the Slack workspace.

    Args:
        limit: Maximum number of users to return (default 100, max 200)
        cursor: Pagination cursor for next page of results

    Returns:
        Dict with members list and pagination metadata.
    """
    return _get_users(limit=limit, cursor=cursor)


@mcp.tool
def slack_get_user_profile(
    user_id: str,
) -> Dict[str, Any]:
    """Get detailed profile information for a specific Slack user.

    Args:
        user_id: The ID of the user

    Returns:
        Dict with user profile information.
    """
    return _get_user_profile(user_id=user_id)


@mcp.tool
def slack_search_messages(
    query: str,
    count: int = 20,
) -> Dict[str, Any]:
    """Search for messages across Slack channels.

    Args:
        query: Search query string
        count: Number of results to return (default 20)

    Returns:
        Dict with search results containing matching messages.
    """
    return _search_messages(query=query, count=count)
