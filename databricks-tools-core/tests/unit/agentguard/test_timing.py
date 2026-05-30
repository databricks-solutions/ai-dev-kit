"""
Unit tests for AgentGuard timing helpers.

Tests:
- Timer.measure and recorded durations
"""

import time

import pytest
from databricks_tools_core.agentguard.timing import Timer


class TestTimer:
    """Tests for Timer."""

    def test_measure_sync(self):
        timer = Timer()
        result = timer.measure("test_step", lambda x: x * 2, 5)
        assert result == 10
        assert len(timer.records) == 1
        assert timer.records[0].name == "test_step"
        assert timer.records[0].duration_ms >= 0

    def test_measure_captures_kwargs(self):
        timer = Timer()

        def add(a, b):
            return a + b

        result = timer.measure("add", add, a=3, b=7)
        assert result == 10

    def test_multiple_measurements(self):
        timer = Timer()
        timer.measure("step1", lambda: 1)
        timer.measure("step2", lambda: 2)
        timer.measure("step3", lambda: 3)
        assert len(timer.records) == 3
        assert [r.name for r in timer.records] == ["step1", "step2", "step3"]

    def test_total_ms(self):
        timer = Timer()

        def slow():
            time.sleep(0.01)
            return True

        timer.measure("slow_step", slow)
        assert timer.total_ms >= 10
        assert timer.total_ms < 500

    def test_total_ms_empty(self):
        timer = Timer()
        assert timer.total_ms == 0.0

    def test_measure_propagates_exception(self):
        timer = Timer()

        def boom():
            raise ValueError("test error")

        with pytest.raises(ValueError, match="test error"):
            timer.measure("boom", boom)

        # measure() does not record timing when the wrapped callable raises
        assert len(timer.records) == 0
