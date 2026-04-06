"""Tests for the manage_genie_instructions MCP tool."""

from unittest.mock import MagicMock, patch

import pytest

from databricks_mcp_server.tools.genie import _manage_genie_instructions_impl as manage_genie_instructions

# Patch target for the manager singleton
_GET_MANAGER = "databricks_mcp_server.tools.genie._get_manager"


@pytest.fixture
def mock_manager():
    """Return a fresh MagicMock that stands in for AgentBricksManager."""
    return MagicMock()


# ---------------------------------------------------------------------------
# add_sql
# ---------------------------------------------------------------------------


def test_add_sql_dispatches_to_manager(mock_manager):
    """action='add_sql' calls genie_add_sql_instruction with title and content."""
    mock_manager.genie_add_sql_instruction.return_value = {"id": "instr-1"}
    with patch(_GET_MANAGER, return_value=mock_manager):
        result = manage_genie_instructions(
            action="add_sql", space_id="sp-1", title="Revenue", content="SELECT SUM(amount) FROM sales"
        )

    mock_manager.genie_add_sql_instruction.assert_called_once_with("sp-1", "Revenue", "SELECT SUM(amount) FROM sales")
    assert result["success"] is True
    assert result["action"] == "add_sql"


def test_add_sql_missing_title(mock_manager):
    """action='add_sql' without title returns error."""
    with patch(_GET_MANAGER, return_value=mock_manager):
        result = manage_genie_instructions(action="add_sql", space_id="sp-1", content="SELECT 1")

    assert "error" in result
    assert "title" in result["error"].lower()


def test_add_sql_missing_content(mock_manager):
    """action='add_sql' without content returns error."""
    with patch(_GET_MANAGER, return_value=mock_manager):
        result = manage_genie_instructions(action="add_sql", space_id="sp-1", title="Revenue")

    assert "error" in result
    assert "content" in result["error"].lower()


# ---------------------------------------------------------------------------
# add_text
# ---------------------------------------------------------------------------


def test_add_text_dispatches_to_manager(mock_manager):
    """action='add_text' calls genie_add_text_instruction with content and title."""
    mock_manager.genie_add_text_instruction.return_value = {"id": "instr-2"}
    with patch(_GET_MANAGER, return_value=mock_manager):
        result = manage_genie_instructions(
            action="add_text", space_id="sp-1", content="Always use fiscal year", title="Business Rules"
        )

    mock_manager.genie_add_text_instruction.assert_called_once_with("sp-1", "Always use fiscal year", "Business Rules")
    assert result["success"] is True
    assert result["action"] == "add_text"


def test_add_text_default_title(mock_manager):
    """action='add_text' without title defaults to 'Notes'."""
    mock_manager.genie_add_text_instruction.return_value = {"id": "instr-3"}
    with patch(_GET_MANAGER, return_value=mock_manager):
        result = manage_genie_instructions(action="add_text", space_id="sp-1", content="Use USD for currency")

    mock_manager.genie_add_text_instruction.assert_called_once_with("sp-1", "Use USD for currency", "Notes")
    assert result["success"] is True


def test_add_text_missing_content(mock_manager):
    """action='add_text' without content returns error."""
    with patch(_GET_MANAGER, return_value=mock_manager):
        result = manage_genie_instructions(action="add_text", space_id="sp-1")

    assert "error" in result
    assert "content" in result["error"].lower()


# ---------------------------------------------------------------------------
# add_function
# ---------------------------------------------------------------------------


def test_add_function_dispatches_to_manager(mock_manager):
    """action='add_function' calls genie_add_sql_function with function_name."""
    mock_manager.genie_add_sql_function.return_value = {"id": "instr-4"}
    with patch(_GET_MANAGER, return_value=mock_manager):
        result = manage_genie_instructions(
            action="add_function", space_id="sp-1", function_name="catalog.schema.calc_revenue"
        )

    mock_manager.genie_add_sql_function.assert_called_once_with("sp-1", "catalog.schema.calc_revenue")
    assert result["success"] is True
    assert result["action"] == "add_function"


def test_add_function_missing_name(mock_manager):
    """action='add_function' without function_name returns error."""
    with patch(_GET_MANAGER, return_value=mock_manager):
        result = manage_genie_instructions(action="add_function", space_id="sp-1")

    assert "error" in result
    assert "function_name" in result["error"]


# ---------------------------------------------------------------------------
# add_benchmark
# ---------------------------------------------------------------------------


def test_add_benchmark_dispatches_to_manager(mock_manager):
    """action='add_benchmark' calls genie_add_benchmark with question and answer."""
    mock_manager.genie_add_benchmark.return_value = {"id": "bm-1"}
    with patch(_GET_MANAGER, return_value=mock_manager):
        result = manage_genie_instructions(
            action="add_benchmark",
            space_id="sp-1",
            question_text="Total revenue last quarter?",
            answer_text="SELECT SUM(amount) FROM sales WHERE quarter = 'Q4'",
        )

    mock_manager.genie_add_benchmark.assert_called_once_with(
        "sp-1", "Total revenue last quarter?", "SELECT SUM(amount) FROM sales WHERE quarter = 'Q4'"
    )
    assert result["success"] is True
    assert result["action"] == "add_benchmark"


def test_add_benchmark_missing_question(mock_manager):
    """action='add_benchmark' without question_text returns error."""
    with patch(_GET_MANAGER, return_value=mock_manager):
        result = manage_genie_instructions(action="add_benchmark", space_id="sp-1", answer_text="SELECT 1")

    assert "error" in result
    assert "question_text" in result["error"]


def test_add_benchmark_missing_answer(mock_manager):
    """action='add_benchmark' without answer_text returns error."""
    with patch(_GET_MANAGER, return_value=mock_manager):
        result = manage_genie_instructions(action="add_benchmark", space_id="sp-1", question_text="Total revenue?")

    assert "error" in result
    assert "answer_text" in result["error"]


# ---------------------------------------------------------------------------
# add_batch
# ---------------------------------------------------------------------------


def test_add_batch_sql_instructions(mock_manager):
    """action='add_batch' with batch_type='sql_instructions' calls batch method."""
    items = [{"title": "Revenue", "content": "SELECT SUM(amount) FROM sales"}]
    mock_manager.genie_add_sql_instructions_batch.return_value = [{"id": "instr-10"}]
    with patch(_GET_MANAGER, return_value=mock_manager):
        result = manage_genie_instructions(
            action="add_batch", space_id="sp-1", batch_type="sql_instructions", items=items
        )

    mock_manager.genie_add_sql_instructions_batch.assert_called_once_with("sp-1", items)
    assert result["success"] is True
    assert result["count"] == 1


def test_add_batch_functions(mock_manager):
    """action='add_batch' with batch_type='functions' calls functions batch method."""
    items = ["catalog.schema.func1", "catalog.schema.func2"]
    mock_manager.genie_add_sql_functions_batch.return_value = [{"id": "f1"}, {"id": "f2"}]
    with patch(_GET_MANAGER, return_value=mock_manager):
        result = manage_genie_instructions(action="add_batch", space_id="sp-1", batch_type="functions", items=items)

    mock_manager.genie_add_sql_functions_batch.assert_called_once_with("sp-1", items)
    assert result["success"] is True
    assert result["count"] == 2


def test_add_batch_benchmarks(mock_manager):
    """action='add_batch' with batch_type='benchmarks' calls benchmarks batch method."""
    items = [{"question_text": "Total?", "answer_text": "SELECT COUNT(*) FROM t"}]
    mock_manager.genie_add_benchmarks_batch.return_value = [{"id": "bm-10"}]
    with patch(_GET_MANAGER, return_value=mock_manager):
        result = manage_genie_instructions(action="add_batch", space_id="sp-1", batch_type="benchmarks", items=items)

    mock_manager.genie_add_benchmarks_batch.assert_called_once_with("sp-1", items)
    assert result["success"] is True


def test_add_batch_missing_batch_type(mock_manager):
    """action='add_batch' without batch_type returns error."""
    with patch(_GET_MANAGER, return_value=mock_manager):
        result = manage_genie_instructions(action="add_batch", space_id="sp-1", items=[{"title": "x", "content": "y"}])

    assert "error" in result
    assert "batch_type" in result["error"]


def test_add_batch_invalid_batch_type(mock_manager):
    """action='add_batch' with invalid batch_type returns error."""
    with patch(_GET_MANAGER, return_value=mock_manager):
        result = manage_genie_instructions(
            action="add_batch", space_id="sp-1", batch_type="invalid", items=[{"x": "y"}]
        )

    assert "error" in result
    assert "invalid" in result["error"].lower()


def test_add_batch_missing_items(mock_manager):
    """action='add_batch' without items returns error."""
    with patch(_GET_MANAGER, return_value=mock_manager):
        result = manage_genie_instructions(action="add_batch", space_id="sp-1", batch_type="sql_instructions")

    assert "error" in result
    assert "items" in result["error"].lower()


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


def test_list_dispatches_to_both_methods(mock_manager):
    """action='list' calls genie_list_instructions and genie_list_questions."""
    mock_manager.genie_list_instructions.return_value = {
        "instructions": [{"title": "Revenue", "content": "SELECT ..."}]
    }
    mock_manager.genie_list_questions.return_value = {
        "curated_questions": [{"question_text": "Total sales?", "question_type": "SAMPLE_QUESTION"}]
    }
    with patch(_GET_MANAGER, return_value=mock_manager):
        result = manage_genie_instructions(action="list", space_id="sp-1")

    mock_manager.genie_list_instructions.assert_called_once_with("sp-1")
    mock_manager.genie_list_questions.assert_called_once_with("sp-1", question_type="SAMPLE_QUESTION")
    assert result["space_id"] == "sp-1"
    assert len(result["instructions"]) == 1
    assert len(result["curated_questions"]) == 1


def test_list_with_question_type_filter(mock_manager):
    """action='list' with question_type passes filter to genie_list_questions."""
    mock_manager.genie_list_instructions.return_value = {"instructions": []}
    mock_manager.genie_list_questions.return_value = {"curated_questions": []}
    with patch(_GET_MANAGER, return_value=mock_manager):
        result = manage_genie_instructions(action="list", space_id="sp-1", question_type="BENCHMARK")

    mock_manager.genie_list_questions.assert_called_once_with("sp-1", question_type="BENCHMARK")
    assert "error" not in result


# ---------------------------------------------------------------------------
# invalid action
# ---------------------------------------------------------------------------


def test_invalid_action():
    """An unrecognised action returns an error listing valid actions."""
    result = manage_genie_instructions(action="badaction", space_id="sp-1")
    assert "error" in result
    for valid in ("add_sql", "add_text", "add_function", "add_benchmark", "add_batch", "list"):
        assert valid in result["error"]


# ---------------------------------------------------------------------------
# error propagation
# ---------------------------------------------------------------------------


def test_add_sql_manager_error_returns_error_dict(mock_manager):
    """Manager exception is caught and returned as error dict."""
    mock_manager.genie_add_sql_instruction.side_effect = Exception("API error")
    with patch(_GET_MANAGER, return_value=mock_manager):
        result = manage_genie_instructions(action="add_sql", space_id="sp-1", title="T", content="C")

    assert "error" in result
    assert "API error" in result["error"]


def test_list_manager_error_returns_error_dict(mock_manager):
    """Manager exception during list is caught and returned as error dict."""
    mock_manager.genie_list_instructions.side_effect = Exception("timeout")
    with patch(_GET_MANAGER, return_value=mock_manager):
        result = manage_genie_instructions(action="list", space_id="sp-1")

    assert "error" in result
    assert "timeout" in result["error"]
