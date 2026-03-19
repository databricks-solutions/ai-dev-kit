"""Unit tests for SQL output formatting (markdown vs JSON)."""

from databricks_mcp_server.tools.sql import _format_results_markdown


class TestFormatResultsMarkdown:
    """Tests for _format_results_markdown helper."""

    def test_empty_list_returns_no_results(self):
        assert _format_results_markdown([]) == "(no results)"

    def test_single_row(self):
        rows = [{"id": "1", "name": "Alice"}]
        result = _format_results_markdown(rows)
        lines = result.strip().split("\n")
        assert lines[0] == "| id | name |"
        assert lines[1] == "| --- | --- |"
        assert lines[2] == "| 1 | Alice |"
        assert "(1 row)" in result

    def test_multiple_rows(self):
        rows = [
            {"id": "1", "name": "Alice", "city": "NYC"},
            {"id": "2", "name": "Bob", "city": "Chicago"},
            {"id": "3", "name": "Carol", "city": "Denver"},
        ]
        result = _format_results_markdown(rows)
        lines = result.strip().split("\n")
        # Header + separator + 3 data rows + blank + count
        assert lines[0] == "| id | name | city |"
        assert lines[1] == "| --- | --- | --- |"
        assert lines[2] == "| 1 | Alice | NYC |"
        assert lines[3] == "| 2 | Bob | Chicago |"
        assert lines[4] == "| 3 | Carol | Denver |"
        assert "(3 rows)" in result

    def test_none_values_become_empty(self):
        rows = [{"id": "1", "name": None}]
        result = _format_results_markdown(rows)
        assert "| 1 |  |" in result

    def test_pipe_chars_escaped(self):
        rows = [{"expr": "a | b"}]
        result = _format_results_markdown(rows)
        assert "a \\| b" in result

    def test_column_names_appear_once(self):
        """The whole point: column names should appear exactly once (in the header)."""
        rows = [
            {"event_id": "1", "event_name": "Concert A"},
            {"event_id": "2", "event_name": "Concert B"},
            {"event_id": "3", "event_name": "Concert C"},
        ]
        result = _format_results_markdown(rows)
        # Column name should appear once in header, not repeated per row
        assert result.count("event_id") == 1
        assert result.count("event_name") == 1

    def test_markdown_smaller_than_json(self):
        """Markdown output should be significantly smaller than JSON for many rows."""
        import json

        rows = [
            {
                "id": str(i),
                "name": f"User {i}",
                "email": f"user{i}@example.com",
                "department": "Engineering",
                "status": "Active",
            }
            for i in range(50)
        ]
        md = _format_results_markdown(rows)
        js = json.dumps(rows)
        # Markdown should be at least 30% smaller
        assert len(md) < len(js) * 0.7, f"Markdown ({len(md)} chars) should be <70% of JSON ({len(js)} chars)"
