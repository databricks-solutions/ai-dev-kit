"""Builder for Databricks Genie Space ``serialized_space`` payloads.

Provides a typed authoring API over the JSON envelope that backs a Genie Space.
It covers every slot the Genie Space API accepts at create/import time:

* ``data_sources.tables`` and ``data_sources.metric_views`` (including nested
  ``column_configs``)
* ``config.sample_questions``
* ``instructions.text_instructions``
* ``instructions.example_question_sqls``
* ``instructions.join_specs``
* ``instructions.sql_snippets.{filters,expressions,measures}``
* ``benchmarks.questions``

The builder is intentionally a thin layer — no network calls, no LLM
dependencies. Pair it with the ``manage_genie`` MCP tool (``create_or_update``
or ``import`` actions) to push the resulting payload to a workspace. See
``databricks-skills/databricks-genie/spaces-authoring.md`` for a full
authoring walkthrough.

Round-trip behaviour: unknown fields on loaded payloads are preserved, so
existing spaces can be fetched via ``manage_genie(action="export")``, patched
with this builder, and sent back via ``manage_genie(action="import")`` without
losing data the builder does not model.
"""

from __future__ import annotations

import copy
import json
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union
from uuid import uuid4


class GenieSpaceBuilder:
    """Typed builder for ``serialized_space`` JSON payloads.

    Usage::

        builder = GenieSpaceBuilder(
            title="Sales Analytics",
            description="Explore sales data",
            warehouse_id="abc123",
        )
        builder.add_table("main.sales.orders", description="Order facts")
        builder.add_sample_question("What were total sales last month?")
        builder.add_join_spec(
            left_table="orders",
            right_table="customers",
            join_type="LEFT",
            condition="orders.customer_id = customers.customer_id",
        )
        envelope = builder.to_envelope()
        # envelope ready for manage_genie(action="import", **envelope)
    """

    # ------------------------------------------------------------------ paths
    # Each constant is a tuple of nested keys into the ``serialized_space``
    # dict. Using tuples (rather than dotted strings) avoids ambiguity when
    # column or table names contain dots.

    TABLES_PATH: Tuple[str, ...] = ("data_sources", "tables")
    METRIC_VIEWS_PATH: Tuple[str, ...] = ("data_sources", "metric_views")
    SAMPLE_QUESTIONS_PATH: Tuple[str, ...] = ("config", "sample_questions")
    TEXT_INSTRUCTIONS_PATH: Tuple[str, ...] = ("instructions", "text_instructions")
    EXAMPLE_QUESTION_SQLS_PATH: Tuple[str, ...] = ("instructions", "example_question_sqls")
    JOIN_SPECS_PATH: Tuple[str, ...] = ("instructions", "join_specs")
    SQL_SNIPPETS_FILTERS_PATH: Tuple[str, ...] = ("instructions", "sql_snippets", "filters")
    SQL_SNIPPETS_EXPRESSIONS_PATH: Tuple[str, ...] = ("instructions", "sql_snippets", "expressions")
    SQL_SNIPPETS_MEASURES_PATH: Tuple[str, ...] = ("instructions", "sql_snippets", "measures")
    BENCHMARKS_PATH: Tuple[str, ...] = ("benchmarks", "questions")

    #: Paths that store a list of ``{"id": ..., ...}`` entries.
    ID_LIST_PATHS: Tuple[Tuple[str, ...], ...] = (
        SAMPLE_QUESTIONS_PATH,
        TEXT_INSTRUCTIONS_PATH,
        EXAMPLE_QUESTION_SQLS_PATH,
        JOIN_SPECS_PATH,
        SQL_SNIPPETS_FILTERS_PATH,
        SQL_SNIPPETS_EXPRESSIONS_PATH,
        SQL_SNIPPETS_MEASURES_PATH,
        BENCHMARKS_PATH,
    )

    # ------------------------------------------------------------------ init
    def __init__(
        self,
        title: str = "",
        description: str = "",
        warehouse_id: str = "",
        space: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.title = title
        self.description = description
        self.warehouse_id = warehouse_id
        self._space: Dict[str, Any] = copy.deepcopy(space) if space is not None else {}
        self._space.setdefault("version", 2)

    # ----------------------------------------------------------- round-trip
    @classmethod
    def from_json(
        cls,
        serialized_space: Union[str, Dict[str, Any]],
        title: Optional[str] = None,
        description: Optional[str] = None,
        warehouse_id: Optional[str] = None,
    ) -> "GenieSpaceBuilder":
        """Load a builder from a ``serialized_space`` JSON string, dict, or export envelope.

        Accepts:
          * the raw payload (``{"version": 2, ...}``) as a dict
          * the JSON-encoded string form of the same
          * the envelope returned by ``manage_genie(action="export")``
            (``{"title": ..., "serialized_space": "..."}``)
        """
        t, d, w = title, description, warehouse_id

        if isinstance(serialized_space, dict) and "serialized_space" in serialized_space:
            envelope = serialized_space
            t = t if t is not None else envelope.get("title", "")
            d = d if d is not None else envelope.get("description", "")
            w = w if w is not None else envelope.get("warehouse_id", "")
            serialized_space = envelope["serialized_space"]

        if isinstance(serialized_space, str):
            serialized_space = json.loads(serialized_space)

        if not isinstance(serialized_space, dict):
            raise TypeError(f"serialized_space must be a dict or JSON string, got {type(serialized_space).__name__}")

        return cls(
            title=t or "",
            description=d or "",
            warehouse_id=w or "",
            space=serialized_space,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Return a deep copy of the current ``serialized_space`` dict."""
        return copy.deepcopy(self._space)

    def to_json(self, *, indent: Optional[int] = None) -> str:
        """Return the ``serialized_space`` as a JSON string."""
        return json.dumps(self._space, indent=indent, sort_keys=False)

    def to_envelope(self, *, indent: Optional[int] = None) -> Dict[str, str]:
        """Return the full envelope used by ``manage_genie(action="import")``.

        Keys: ``title``, ``description``, ``warehouse_id``, ``serialized_space``
        (the last is a JSON-encoded string, as the API expects).
        """
        return {
            "title": self.title,
            "description": self.description,
            "warehouse_id": self.warehouse_id,
            "serialized_space": self.to_json(indent=indent),
        }

    # ------------------------------------------------------- internal utils
    def _get_list(self, path: Tuple[str, ...]) -> List[Dict[str, Any]]:
        """Return the list at ``path``, creating parent dicts as needed."""
        if not path:
            raise ValueError("path must not be empty")
        node: Any = self._space
        for key in path[:-1]:
            if not isinstance(node, dict):
                raise TypeError(f"Cannot traverse into non-dict at path segment {key!r}")
            node = node.setdefault(key, {})
        if not isinstance(node, dict):
            raise TypeError(f"Cannot set list on non-dict at path {path!r}")
        leaf = node.setdefault(path[-1], [])
        if not isinstance(leaf, list):
            raise TypeError(f"Expected list at {path!r}, found {type(leaf).__name__}")
        return leaf

    @staticmethod
    def _gen_id() -> str:
        """Return a 32-char hex UUID (matches the Genie API format)."""
        return uuid4().hex

    @staticmethod
    def _as_str_list(value: Union[str, Iterable[str], None]) -> List[str]:
        """Coerce a scalar string or iterable-of-strings into a list of strings."""
        if value is None or value == "":
            return []
        if isinstance(value, str):
            return [value]
        return list(value)

    # ---------------------------------------------- data_sources (tables)
    def add_table(
        self,
        identifier: str,
        description: Union[str, Iterable[str], None] = None,
        column_configs: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Add a Unity Catalog table to the space.

        ``identifier`` must be fully qualified (``catalog.schema.table``).
        ``column_configs`` is an optional list of dicts with shape:
        ``{"column_name": ..., "description": [...], "synonyms": [...],
        "enable_format_assistance": bool, "enable_entity_matching": bool,
        "exclude": bool}``. Entries are sorted by ``column_name``.
        """
        entry: Dict[str, Any] = {
            "identifier": identifier,
            "description": self._as_str_list(description),
        }
        if column_configs:
            entry["column_configs"] = sorted(column_configs, key=lambda c: c.get("column_name", ""))
        self._get_list(self.TABLES_PATH).append(entry)
        return entry

    def add_metric_view(
        self,
        identifier: str,
        description: Union[str, Iterable[str], None] = None,
        column_configs: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Add a Unity Catalog metric view to the space."""
        entry: Dict[str, Any] = {
            "identifier": identifier,
            "description": self._as_str_list(description),
        }
        if column_configs:
            entry["column_configs"] = sorted(column_configs, key=lambda c: c.get("column_name", ""))
        self._get_list(self.METRIC_VIEWS_PATH).append(entry)
        return entry

    def add_column_config(
        self,
        table_identifier: str,
        column_name: str,
        *,
        description: Union[str, Iterable[str], None] = None,
        synonyms: Optional[Iterable[str]] = None,
        enable_format_assistance: Optional[bool] = None,
        enable_entity_matching: Optional[bool] = None,
        exclude: bool = False,
    ) -> Dict[str, Any]:
        """Add or replace a column_config on a table or metric_view entry.

        Looks up the data-source entry by ``identifier`` across both
        ``tables`` and ``metric_views`` lists.
        Existing entries for ``column_name`` are replaced (not duplicated).
        The resulting ``column_configs`` list is kept sorted by column name,
        which is what the Genie API expects.
        """
        for path in (self.TABLES_PATH, self.METRIC_VIEWS_PATH):
            for entry in self._get_list(path):
                if entry.get("identifier") != table_identifier:
                    continue
                cc: Dict[str, Any] = {"column_name": column_name}
                if exclude:
                    cc["exclude"] = True
                else:
                    if description:
                        cc["description"] = self._as_str_list(description)
                    if synonyms:
                        cc["synonyms"] = list(synonyms)
                    if enable_format_assistance is not None:
                        cc["enable_format_assistance"] = bool(enable_format_assistance)
                    if enable_entity_matching is not None:
                        cc["enable_entity_matching"] = bool(enable_entity_matching)
                configs = entry.setdefault("column_configs", [])
                configs[:] = [c for c in configs if c.get("column_name") != column_name]
                configs.append(cc)
                configs.sort(key=lambda c: c.get("column_name", ""))
                return cc
        raise KeyError(f"No table or metric_view found with identifier: {table_identifier!r}")

    # -------------------------------------------- config.sample_questions
    def add_sample_question(self, question: str, *, id: Optional[str] = None) -> Dict[str, Any]:
        """Add a sample question (natural language only; no SQL)."""
        entry = {"id": id or self._gen_id(), "question": [question]}
        self._get_list(self.SAMPLE_QUESTIONS_PATH).append(entry)
        return entry

    # ----------------------------------- instructions.text_instructions
    def add_text_instruction(self, content: str, *, id: Optional[str] = None) -> Dict[str, Any]:
        """Add a free-form text instruction (markdown supported)."""
        entry = {"id": id or self._gen_id(), "content": [content]}
        self._get_list(self.TEXT_INSTRUCTIONS_PATH).append(entry)
        return entry

    # ----------------------------- instructions.example_question_sqls
    def add_example_sql(self, question: str, sql: str, *, id: Optional[str] = None) -> Dict[str, Any]:
        """Add a certified question/SQL pair.

        Example SQL is the strongest lever for steering Genie's generations —
        each entry pins a canonical SQL answer for a canonical question.
        """
        entry = {"id": id or self._gen_id(), "question": [question], "sql": [sql]}
        self._get_list(self.EXAMPLE_QUESTION_SQLS_PATH).append(entry)
        return entry

    # -------------------------------------- instructions.join_specs
    def add_join_spec(
        self,
        left_table: str,
        right_table: str,
        join_type: str,
        condition: str,
        *,
        relationship_type: str = "",
        display_name: str = "",
        comment: str = "",
        instruction: str = "",
        id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Add a join definition used by Genie when queries span tables.

        ``join_type`` is typically ``INNER``, ``LEFT``, or ``RIGHT``.
        ``relationship_type`` is optional and one of ``MANY_TO_ONE``,
        ``ONE_TO_MANY``, or ``ONE_TO_ONE``.
        """
        entry: Dict[str, Any] = {
            "id": id or self._gen_id(),
            "left_table": left_table,
            "right_table": right_table,
            "join_type": join_type,
            "condition": condition,
        }
        if relationship_type:
            entry["relationship_type"] = relationship_type
        if display_name:
            entry["display_name"] = display_name
        if comment:
            entry["comment"] = comment
        if instruction:
            entry["instruction"] = instruction
        self._get_list(self.JOIN_SPECS_PATH).append(entry)
        return entry

    # ------------------------------- instructions.sql_snippets.filters
    def add_sql_filter(
        self,
        sql: str,
        *,
        display_name: str = "",
        synonyms: Optional[Iterable[str]] = None,
        comment: str = "",
        instruction: str = "",
        id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Add a named, reusable WHERE-style predicate (e.g. status filters)."""
        return self._add_snippet(
            self.SQL_SNIPPETS_FILTERS_PATH,
            id=id,
            sql=sql,
            display_name=display_name,
            synonyms=synonyms,
            comment=comment,
            instruction=instruction,
        )

    # --------------------------- instructions.sql_snippets.expressions
    def add_sql_expression(
        self,
        alias: str,
        sql: str,
        *,
        display_name: str = "",
        synonyms: Optional[Iterable[str]] = None,
        comment: str = "",
        instruction: str = "",
        id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Add a named, reusable SELECT-list expression (e.g. date extracts, CASE bucketing)."""
        return self._add_snippet(
            self.SQL_SNIPPETS_EXPRESSIONS_PATH,
            id=id,
            alias=alias,
            sql=sql,
            display_name=display_name,
            synonyms=synonyms,
            comment=comment,
            instruction=instruction,
        )

    # ----------------------------- instructions.sql_snippets.measures
    def add_sql_measure(
        self,
        name: str,
        sql: str,
        *,
        display_name: str = "",
        synonyms: Optional[Iterable[str]] = None,
        comment: str = "",
        instruction: str = "",
        id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Add a named, reusable aggregate (e.g. ``SUM(orders.total_amount)``)."""
        return self._add_snippet(
            self.SQL_SNIPPETS_MEASURES_PATH,
            id=id,
            name=name,
            sql=sql,
            display_name=display_name,
            synonyms=synonyms,
            comment=comment,
            instruction=instruction,
        )

    def _add_snippet(
        self,
        path: Tuple[str, ...],
        *,
        id: Optional[str],
        **fields: Any,
    ) -> Dict[str, Any]:
        """Shared implementation for filters / expressions / measures snippets."""
        entry: Dict[str, Any] = {"id": id or self._gen_id()}
        for key, value in fields.items():
            if value is None or value == "":
                continue
            if key == "synonyms":
                entry[key] = list(value)
            else:
                entry[key] = value
        self._get_list(path).append(entry)
        return entry

    # --------------------------------------------- benchmarks.questions
    def add_benchmark(self, question: str, sql: str, *, id: Optional[str] = None) -> Dict[str, Any]:
        """Add a benchmark question with a canonical SQL answer.

        Benchmarks are used by the Genie quality evaluator; each entry pairs a
        question with one or more SQL bodies treated as ground truth.
        """
        entry = {
            "id": id or self._gen_id(),
            "question": [question],
            "answers": [{"format": "SQL", "body": [sql]}],
        }
        self._get_list(self.BENCHMARKS_PATH).append(entry)
        return entry

    # ---------------------------------------------------- generic list ops
    def find_by_id(self, path: Iterable[str], id: str) -> Optional[Dict[str, Any]]:
        """Return the entry with the given ``id`` at ``path``, or ``None``."""
        for entry in self._get_list(tuple(path)):
            if entry.get("id") == id:
                return entry
        return None

    def replace_by_id(self, path: Iterable[str], id: str, new_entry: Dict[str, Any]) -> bool:
        """Replace the entry with ``id`` at ``path``. Returns ``True`` if replaced."""
        lst = self._get_list(tuple(path))
        for idx, entry in enumerate(lst):
            if entry.get("id") == id:
                lst[idx] = new_entry
                return True
        return False

    def remove_by_id(self, path: Iterable[str], id: str) -> bool:
        """Remove the entry with ``id`` at ``path``. Returns ``True`` if removed."""
        lst = self._get_list(tuple(path))
        for idx, entry in enumerate(lst):
            if entry.get("id") == id:
                lst.pop(idx)
                return True
        return False

    # ----------------------------------------------------- bulk accessors
    def list_tables(self) -> List[Dict[str, Any]]:
        """Return a shallow copy of the ``data_sources.tables`` list."""
        return list(self._get_list(self.TABLES_PATH))

    def list_metric_views(self) -> List[Dict[str, Any]]:
        """Return a shallow copy of the ``data_sources.metric_views`` list."""
        return list(self._get_list(self.METRIC_VIEWS_PATH))

    def list_sample_questions(self) -> List[Dict[str, Any]]:
        """Return a shallow copy of the ``config.sample_questions`` list."""
        return list(self._get_list(self.SAMPLE_QUESTIONS_PATH))

    def list_text_instructions(self) -> List[Dict[str, Any]]:
        """Return a shallow copy of the ``instructions.text_instructions`` list."""
        return list(self._get_list(self.TEXT_INSTRUCTIONS_PATH))

    def list_example_sqls(self) -> List[Dict[str, Any]]:
        """Return a shallow copy of the ``instructions.example_question_sqls`` list."""
        return list(self._get_list(self.EXAMPLE_QUESTION_SQLS_PATH))

    def list_join_specs(self) -> List[Dict[str, Any]]:
        """Return a shallow copy of the ``instructions.join_specs`` list."""
        return list(self._get_list(self.JOIN_SPECS_PATH))

    def list_sql_filters(self) -> List[Dict[str, Any]]:
        """Return a shallow copy of the ``instructions.sql_snippets.filters`` list."""
        return list(self._get_list(self.SQL_SNIPPETS_FILTERS_PATH))

    def list_sql_expressions(self) -> List[Dict[str, Any]]:
        """Return a shallow copy of the ``instructions.sql_snippets.expressions`` list."""
        return list(self._get_list(self.SQL_SNIPPETS_EXPRESSIONS_PATH))

    def list_sql_measures(self) -> List[Dict[str, Any]]:
        """Return a shallow copy of the ``instructions.sql_snippets.measures`` list."""
        return list(self._get_list(self.SQL_SNIPPETS_MEASURES_PATH))

    def list_benchmarks(self) -> List[Dict[str, Any]]:
        """Return a shallow copy of the ``benchmarks.questions`` list."""
        return list(self._get_list(self.BENCHMARKS_PATH))


__all__ = ["GenieSpaceBuilder"]
