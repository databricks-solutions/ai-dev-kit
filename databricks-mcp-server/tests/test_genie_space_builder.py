"""Unit tests for GenieSpaceBuilder.

These tests exercise the pure-Python authoring surface. They do not call the
Databricks workspace — only the builder's in-memory state is verified.
"""

import json

import pytest

from databricks_mcp_server.tools.genie_space_builder import GenieSpaceBuilder


# ---------------------------------------------------------------- helpers
def _ids(entries):
    return {e["id"] for e in entries}


# --------------------------------------------------------------- init / io
def test_init_sets_version_two():
    b = GenieSpaceBuilder()
    assert b.to_dict()["version"] == 2


def test_round_trip_preserves_unknown_fields():
    original = {
        "version": 2,
        "data_sources": {"tables": []},
        "some_future_field": {"foo": "bar"},
    }
    b = GenieSpaceBuilder.from_json(original)
    out = b.to_dict()
    assert out["some_future_field"] == {"foo": "bar"}


def test_from_json_accepts_string():
    payload = json.dumps({"version": 2, "config": {"sample_questions": []}})
    b = GenieSpaceBuilder.from_json(payload)
    assert b.list_sample_questions() == []


def test_from_json_accepts_envelope():
    inner = json.dumps({"version": 2})
    envelope = {
        "title": "My Space",
        "description": "Desc",
        "warehouse_id": "wh_1",
        "serialized_space": inner,
    }
    b = GenieSpaceBuilder.from_json(envelope)
    assert b.title == "My Space"
    assert b.description == "Desc"
    assert b.warehouse_id == "wh_1"


def test_from_json_rejects_non_dict_payload():
    with pytest.raises(TypeError):
        GenieSpaceBuilder.from_json(123)  # type: ignore[arg-type]


def test_to_envelope_contains_json_string():
    b = GenieSpaceBuilder(title="T", description="D", warehouse_id="W")
    env = b.to_envelope()
    assert env["title"] == "T"
    assert env["description"] == "D"
    assert env["warehouse_id"] == "W"
    assert isinstance(env["serialized_space"], str)
    assert json.loads(env["serialized_space"])["version"] == 2


# -------------------------------------------------------------- data_sources
def test_add_table_and_metric_view():
    b = GenieSpaceBuilder()
    b.add_table("cat.sch.orders", description="Order facts")
    b.add_metric_view("cat.sch.metrics_orders", description="Order metrics")
    assert len(b.list_tables()) == 1
    assert len(b.list_metric_views()) == 1
    assert b.list_tables()[0]["identifier"] == "cat.sch.orders"
    assert b.list_tables()[0]["description"] == ["Order facts"]


def test_add_column_config_on_table():
    b = GenieSpaceBuilder()
    b.add_table("cat.sch.orders")
    b.add_column_config(
        "cat.sch.orders",
        "order_id",
        description="Unique order identifier",
        synonyms=["order", "id"],
        enable_entity_matching=True,
        enable_format_assistance=True,
    )
    configs = b.list_tables()[0]["column_configs"]
    assert configs[0]["column_name"] == "order_id"
    assert configs[0]["description"] == ["Unique order identifier"]
    assert configs[0]["enable_entity_matching"] is True


def test_add_column_config_replaces_existing():
    b = GenieSpaceBuilder()
    b.add_table("cat.sch.orders")
    b.add_column_config("cat.sch.orders", "status", description="v1")
    b.add_column_config("cat.sch.orders", "status", description="v2")
    configs = b.list_tables()[0]["column_configs"]
    assert len(configs) == 1
    assert configs[0]["description"] == ["v2"]


def test_add_column_config_sorted_by_name():
    b = GenieSpaceBuilder()
    b.add_table("cat.sch.orders")
    b.add_column_config("cat.sch.orders", "zzz")
    b.add_column_config("cat.sch.orders", "aaa")
    b.add_column_config("cat.sch.orders", "mmm")
    names = [c["column_name"] for c in b.list_tables()[0]["column_configs"]]
    assert names == ["aaa", "mmm", "zzz"]


def test_add_column_config_exclude():
    b = GenieSpaceBuilder()
    b.add_table("cat.sch.orders")
    b.add_column_config("cat.sch.orders", "_rescued_data", exclude=True)
    cc = b.list_tables()[0]["column_configs"][0]
    assert cc == {"column_name": "_rescued_data", "exclude": True}


def test_add_column_config_unknown_identifier_raises():
    b = GenieSpaceBuilder()
    with pytest.raises(KeyError):
        b.add_column_config("cat.sch.missing", "col_a")


# -------------------------------------------------------- config & instructions
def test_sample_questions_get_unique_ids():
    b = GenieSpaceBuilder()
    q1 = b.add_sample_question("Q1?")
    q2 = b.add_sample_question("Q2?")
    assert q1["id"] != q2["id"]
    assert len(q1["id"]) == 32  # uuid4 hex


def test_text_instruction_roundtrips_content():
    b = GenieSpaceBuilder()
    entry = b.add_text_instruction("## Best practices\n* tip one")
    assert entry["content"] == ["## Best practices\n* tip one"]


def test_example_sql_adds_question_and_sql():
    b = GenieSpaceBuilder()
    entry = b.add_example_sql(
        "What were total sales?",
        "SELECT SUM(total_amount) FROM orders",
    )
    assert entry["question"] == ["What were total sales?"]
    assert entry["sql"] == ["SELECT SUM(total_amount) FROM orders"]


def test_join_spec_full_fields():
    b = GenieSpaceBuilder()
    entry = b.add_join_spec(
        left_table="orders",
        right_table="customers",
        join_type="LEFT",
        condition="orders.customer_id = customers.customer_id",
        relationship_type="MANY_TO_ONE",
        display_name="Orders to Customers",
        comment="Each order has one customer",
        instruction="Use when joining customer attributes to orders",
    )
    assert entry["join_type"] == "LEFT"
    assert entry["relationship_type"] == "MANY_TO_ONE"
    assert entry["display_name"] == "Orders to Customers"


def test_join_spec_omits_empty_optional_fields():
    b = GenieSpaceBuilder()
    entry = b.add_join_spec(
        left_table="a",
        right_table="b",
        join_type="INNER",
        condition="a.id = b.id",
    )
    assert "relationship_type" not in entry
    assert "display_name" not in entry
    assert "comment" not in entry
    assert "instruction" not in entry


# -------------------------------------------------------------- sql_snippets
def test_sql_filter_measure_expression():
    b = GenieSpaceBuilder()
    b.add_sql_filter(
        "orders.status = 'Confirmed'",
        display_name="Confirmed",
        synonyms=["active"],
        comment="Only confirmed orders",
    )
    b.add_sql_measure(
        "total_revenue",
        "SUM(orders.total_amount)",
        display_name="Total Revenue",
    )
    b.add_sql_expression(
        "order_year",
        "YEAR(orders.order_date)",
        display_name="Order Year",
    )
    assert len(b.list_sql_filters()) == 1
    assert len(b.list_sql_measures()) == 1
    assert len(b.list_sql_expressions()) == 1
    assert b.list_sql_filters()[0]["display_name"] == "Confirmed"


def test_sql_snippet_strips_empty_fields():
    b = GenieSpaceBuilder()
    entry = b.add_sql_measure("cnt", "COUNT(*)")
    assert "display_name" not in entry
    assert "comment" not in entry


# --------------------------------------------------------------- benchmarks
def test_benchmark_structure():
    b = GenieSpaceBuilder()
    entry = b.add_benchmark(
        "How many orders?",
        "SELECT COUNT(*) FROM orders",
    )
    assert entry["question"] == ["How many orders?"]
    assert entry["answers"] == [{"format": "SQL", "body": ["SELECT COUNT(*) FROM orders"]}]


# ------------------------------------------------------------- generic ops
def test_find_replace_remove_by_id():
    b = GenieSpaceBuilder()
    q1 = b.add_sample_question("Q1?")
    q2 = b.add_sample_question("Q2?")

    assert b.find_by_id(b.SAMPLE_QUESTIONS_PATH, q1["id"]) == q1
    assert b.find_by_id(b.SAMPLE_QUESTIONS_PATH, "missing") is None

    assert b.replace_by_id(
        b.SAMPLE_QUESTIONS_PATH,
        q1["id"],
        {"id": q1["id"], "question": ["Updated?"]},
    )
    assert b.find_by_id(b.SAMPLE_QUESTIONS_PATH, q1["id"])["question"] == ["Updated?"]

    assert b.remove_by_id(b.SAMPLE_QUESTIONS_PATH, q2["id"])
    assert b.find_by_id(b.SAMPLE_QUESTIONS_PATH, q2["id"]) is None
    assert len(b.list_sample_questions()) == 1


def test_replace_by_id_returns_false_for_missing():
    b = GenieSpaceBuilder()
    b.add_sample_question("Q?")
    assert not b.replace_by_id(b.SAMPLE_QUESTIONS_PATH, "does-not-exist", {})


def test_ids_are_unique_across_slots():
    b = GenieSpaceBuilder()
    b.add_sample_question("A?")
    b.add_text_instruction("T")
    b.add_example_sql("Q?", "SELECT 1")
    b.add_join_spec("a", "b", "INNER", "a.id = b.id")
    b.add_sql_filter("a.x = 1")
    b.add_sql_expression("alias", "YEAR(a.d)")
    b.add_sql_measure("m", "COUNT(*)")
    b.add_benchmark("bq", "SELECT 1")

    all_ids = set()
    for path in GenieSpaceBuilder.ID_LIST_PATHS:
        for entry in b._get_list(path):
            all_ids.add(entry["id"])
    assert len(all_ids) == 8


def test_explicit_id_honored():
    b = GenieSpaceBuilder()
    entry = b.add_sample_question("Q?", id="deadbeef" * 4)
    assert entry["id"] == "deadbeef" * 4


# ------------------------------------------------------- full roundtrip test
def test_full_build_to_import_envelope():
    """End-to-end: build a space, export envelope, reload, confirm equivalence."""
    src = GenieSpaceBuilder(title="Sales", description="D", warehouse_id="wh")
    src.add_table("cat.sch.orders", description="Orders fact")
    src.add_table("cat.sch.customers", description="Customers dim")
    src.add_column_config("cat.sch.orders", "order_id", description="id")
    src.add_sample_question("What were sales last month?")
    src.add_example_sql("Total sales?", "SELECT SUM(amt) FROM cat.sch.orders")
    src.add_join_spec(
        "orders",
        "customers",
        "LEFT",
        "orders.customer_id = customers.customer_id",
        relationship_type="MANY_TO_ONE",
    )
    src.add_sql_measure("rev", "SUM(orders.amt)", display_name="Revenue")
    src.add_text_instruction("Always round to 2 decimals.")
    src.add_benchmark("How many?", "SELECT COUNT(*) FROM orders")

    envelope = src.to_envelope()
    dst = GenieSpaceBuilder.from_json(envelope)

    assert dst.title == "Sales"
    assert dst.warehouse_id == "wh"
    assert len(dst.list_tables()) == 2
    assert len(dst.list_join_specs()) == 1
    assert len(dst.list_sql_measures()) == 1
    assert len(dst.list_benchmarks()) == 1
    assert dst.to_dict() == src.to_dict()
