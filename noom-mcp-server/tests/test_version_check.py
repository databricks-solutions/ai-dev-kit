"""Unit tests for noom_mcp.version_check."""

import pytest


class TestCheckUpstreamVersion:
    def test_happy_path(self):
        """Current installed version matches the pin — no error."""
        from noom_mcp.version_check import check_upstream_version

        check_upstream_version()  # must not raise

    def test_version_mismatch_raises(self):
        """Stale pin triggers UpstreamChangedError with actionable message."""
        import noom_mcp.version_check as m
        from noom_mcp.version_check import UpstreamChangedError, check_upstream_version

        original = m.PATCHED_UPSTREAM_VERSION
        m.PATCHED_UPSTREAM_VERSION = "0.0.0"
        try:
            with pytest.raises(UpstreamChangedError) as exc_info:
                check_upstream_version()
            msg = str(exc_info.value)
            assert "version mismatch" in msg.lower()
            assert "0.0.0" in msg
            assert "PATCHED_UPSTREAM_VERSION" in msg
        finally:
            m.PATCHED_UPSTREAM_VERSION = original
