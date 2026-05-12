"""Configuration for the MCP table filter."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

_TAG_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")


@dataclass(frozen=True)
class FilterConfig:
    """Immutable configuration for the table filter.

    Use ``FilterConfig.from_env()`` to build from environment variables, or
    construct directly for tests / non-env-driven usage.

    Attributes:
        tag_name: UC tag key to filter on. Empty string disables filtering.
        tag_value: Required tag value (empty = match any value of ``tag_name``).
        cache_ttl_seconds: How long to cache the allowlist (default 300s).
        warehouse_id: Optional explicit SQL warehouse to use for queries.
        fail_closed: If True (default), unparseable SQL is rejected rather than
            allowed through. Disable only in trusted, debug-only contexts.
    """

    tag_name: str = ""
    tag_value: str = ""
    cache_ttl_seconds: int = 300
    warehouse_id: str | None = None
    fail_closed: bool = True

    def __post_init__(self) -> None:
        if self.tag_name and not _TAG_NAME_RE.match(self.tag_name):
            raise ValueError(
                f"Invalid tag_name {self.tag_name!r}: must match [A-Za-z_][A-Za-z0-9_-]*"
            )
        if self.cache_ttl_seconds < 0:
            raise ValueError(f"cache_ttl_seconds must be >= 0, got {self.cache_ttl_seconds}")

    @property
    def is_enabled(self) -> bool:
        return bool(self.tag_name)

    @classmethod
    def from_env(cls, env: dict | None = None) -> FilterConfig:
        """Build a FilterConfig from environment variables.

        Recognized env vars (all optional):
          - MCP_TABLE_FILTER_TAG_NAME
          - MCP_TABLE_FILTER_TAG_VALUE
          - MCP_TABLE_FILTER_CACHE_TTL  (integer seconds)
          - MCP_TABLE_FILTER_WAREHOUSE_ID
          - MCP_TABLE_FILTER_FAIL_CLOSED  (true/false, default true)
        """
        env = env if env is not None else os.environ

        ttl_raw = env.get("MCP_TABLE_FILTER_CACHE_TTL", "300").strip()
        try:
            cache_ttl = int(ttl_raw) if ttl_raw else 300
        except ValueError as exc:
            raise ValueError(
                f"MCP_TABLE_FILTER_CACHE_TTL must be an integer, got {ttl_raw!r}"
            ) from exc

        fail_closed_raw = env.get("MCP_TABLE_FILTER_FAIL_CLOSED", "true").strip().lower()
        fail_closed = fail_closed_raw not in {"0", "false", "no", "off"}

        return cls(
            tag_name=env.get("MCP_TABLE_FILTER_TAG_NAME", "").strip(),
            tag_value=env.get("MCP_TABLE_FILTER_TAG_VALUE", "").strip(),
            cache_ttl_seconds=cache_ttl,
            warehouse_id=env.get("MCP_TABLE_FILTER_WAREHOUSE_ID", "").strip() or None,
            fail_closed=fail_closed,
        )
