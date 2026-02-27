"""
SQL Dependency Analyzer

Analyzes SQL queries to determine dependencies and optimal execution order.
Uses sqlglot for parsing and sqlfluff for comment stripping.
"""

import logging
from typing import Dict, List, Optional, Set

import sqlglot
from sqlglot import exp
from sqlfluff.core import Linter

logger = logging.getLogger(__name__)


class SQLDependencyAnalyzer:
    """Analyzes SQL queries to determine dependencies and execution order.

    Parses SQL statements to identify:
    - Which tables are created by each query
    - Which tables are referenced by each query
    - Dependencies between queries based on table usage

    Uses this information to group queries into execution levels where
    queries within a level can run in parallel.
    """

    def __init__(self, dialect: str = "databricks"):
        """
        Initialize the analyzer.

        Args:
            dialect: SQL dialect for parsing (default: "databricks")
        """
        self.dialect = dialect
        self.created_tables: Dict[str, int] = {}  # table_name -> query_index
        self.query_dependencies: Dict[int, Set[str]] = {}  # query_index -> referenced tables
        self._linter = Linter(dialect=self.dialect)

    def parse_sql_content(self, sql_content: str) -> List[str]:
        """
        Parse SQL content into individual queries.

        Handles:
        - Multiple statements separated by semicolons
        - Comments (both -- and /* */)
        - Complex statements with subqueries

        Args:
            sql_content: Raw SQL content with potentially multiple statements

        Returns:
            List of individual SQL queries (each ending with ;)
        """
        cleaned = self._strip_comments(sql_content)

        queries: List[str] = []
        # Split by semicolons first to preserve original SQL
        raw_statements = [s.strip() for s in cleaned.split(";") if s.strip()]

        for raw_sql in raw_statements:
            # Parse to validate and analyze dependencies, but keep original SQL
            # to preserve formatting like backticks that sqlglot might modify
            parsed = sqlglot.parse(raw_sql, read=self.dialect)
            if parsed and parsed[0] is not None:
                # Use original SQL to preserve backticks and other formatting
                # that sqlglot might change during regeneration
                queries.append(raw_sql + ";")
            elif raw_sql:
                # If parsing fails, still try to include the statement
                queries.append(raw_sql + ";")

        logger.debug(f"Parsed {len(queries)} queries from SQL content")
        return queries

    def analyze_dependencies(self, queries: List[str]) -> List[List[int]]:
        """
        Analyze query dependencies and return execution groups.

        Queries within a group have no dependencies on each other and
        can be executed in parallel. Groups must be executed sequentially.

        Args:
            queries: List of SQL query strings

        Returns:
            List of groups, where each group is a list of query indices
            Example: [[0, 1], [2], [3, 4]] means:
            - Queries 0 and 1 can run in parallel (group 1)
            - Query 2 runs after group 1 (group 2)
            - Queries 3 and 4 can run in parallel after query 2 (group 3)
        """
        self.created_tables.clear()
        self.query_dependencies.clear()

        # Pass 1: Discover created objects and references
        for idx, query in enumerate(queries):
            exprs = [e for e in (sqlglot.parse(query, read=self.dialect) or []) if e is not None]

            created_here: Set[str] = set()
            referenced_here: Set[str] = set()

            for root in exprs:
                # Track CREATE statements
                if isinstance(root, exp.Create):
                    table = self._bare(self._table_from_create(root))
                    if table:
                        created_here.add(table)

                # Track ALTER statements (reference existing table)
                if isinstance(root, exp.Alter):
                    table = self._bare(self._table_from_alter(root))
                    if table:
                        referenced_here.add(table)

                # Track DROP statements (reference existing table)
                if isinstance(root, exp.Drop):
                    table = self._bare(self._table_from_drop(root))
                    if table:
                        referenced_here.add(table)

                # Track general references (FROM, JOIN, etc.)
                refs = self._extract_referenced_tables(root)
                if refs:
                    referenced_here |= refs

            # Record created tables
            for table in created_here:
                self.created_tables[table] = idx
                logger.debug(f"Query {idx} creates: {table}")

            # Record dependencies
            if referenced_here:
                self.query_dependencies.setdefault(idx, set()).update(referenced_here)
                logger.debug(f"Query {idx} references: {sorted(referenced_here)}")

        # Pass 2: Build query-to-query dependency edges
        edges: Dict[int, Set[int]] = {}
        for query_idx, tables in self.query_dependencies.items():
            deps = set()
            for table in tables:
                creator = self.created_tables.get(table)
                if creator is not None and creator != query_idx:
                    deps.add(creator)
            if deps:
                edges[query_idx] = deps
                logger.debug(f"Query {query_idx} depends on queries: {sorted(deps)}")

        # Topological sort into execution groups
        groups = self._topological_sort(len(queries), edges)
        logger.info(f"Organized {len(queries)} queries into {len(groups)} execution groups")
        return groups

    def _strip_comments(self, sql: str) -> str:
        """Strip comments using sqlfluff, preserving line structure."""
        try:
            parsed = self._linter.parse_string(sql)
            if not parsed or not parsed.tree:
                return sql

            out_parts: List[str] = []
            for seg in parsed.tree.raw_segments:
                if seg.is_type("comment"):
                    # Preserve newlines to maintain line boundaries
                    if "\n" in seg.raw:
                        out_parts.append("\n")
                    continue
                out_parts.append(seg.raw)
            return "".join(out_parts)
        except Exception as e:
            logger.warning(f"Failed to strip comments with sqlfluff: {e}")
            return sql

    def _topological_sort(self, num_queries: int, dependencies: Dict[int, Set[int]]) -> List[List[int]]:
        """
        Kahn's algorithm for levelized topological ordering.

        Returns groups where each group can be executed in parallel.
        """
        in_degree = [0] * num_queries
        reverse_deps: Dict[int, Set[int]] = {i: set() for i in range(num_queries)}

        for query, deps in dependencies.items():
            in_degree[query] = len(deps)
            for dep in deps:
                reverse_deps[dep].add(query)

        # Start with queries that have no dependencies
        queue = [i for i in range(num_queries) if in_degree[i] == 0]
        groups: List[List[int]] = []
        visited: Set[int] = set()

        while queue:
            # All queries in current queue can run in parallel
            current = sorted(queue)
            groups.append(current)
            queue = []

            for query in current:
                visited.add(query)
                for next_query in reverse_deps[query]:
                    if next_query in visited:
                        continue
                    in_degree[next_query] -= 1
                    if in_degree[next_query] == 0:
                        queue.append(next_query)

        # Handle circular dependencies (shouldn't happen in well-formed SQL)
        remaining = [i for i in range(num_queries) if i not in visited]
        if remaining:
            logger.warning(f"Circular dependencies detected for queries: {remaining}")
            groups.append(remaining)

        return groups

    def _extract_referenced_tables(self, root: exp.Expression) -> Set[str]:
        """
        Extract referenced tables from an AST node.

        Excludes:
        - CTE names (WITH clause aliases)
        - The target table in CREATE/INSERT statements
        """
        referenced: Set[str] = set()
        if root is None:
            return referenced

        cte_names = self._collect_cte_names(root)
        created_target = None

        if isinstance(root, exp.Create):
            created_target = self._bare(self._table_from_create(root))

        for table in root.find_all(exp.Table):
            bare = self._bare(table)
            if not bare:
                continue
            if bare == created_target:
                continue
            if bare in cte_names:
                continue
            referenced.add(bare)

        # Exclude INSERT target from dependencies
        if isinstance(root, exp.Insert):
            target = getattr(root, "this", None)
            if isinstance(target, exp.Table):
                target_bare = self._bare(target)
                if target_bare:
                    referenced.discard(target_bare)

        return referenced

    def _collect_cte_names(self, root: exp.Expression) -> Set[str]:
        """Collect CTE names from WITH clause for exclusion."""
        names: Set[str] = set()
        with_clause = root.args.get("with")
        if isinstance(with_clause, exp.With):
            for cte in with_clause.expressions or []:
                alias = getattr(cte, "alias", None)
                if alias:
                    ident = getattr(alias, "this", None)
                    if isinstance(ident, exp.Identifier):
                        names.add(ident.this.lower())
        return names

    def _bare(self, table_exp: Optional[exp.Expression]) -> Optional[str]:
        """Extract bare table name (lowercase) from expression."""
        if table_exp is None:
            return None
        if isinstance(table_exp, exp.Table):
            name = table_exp.name or ""
            return name.strip('`"').lower() or None
        if hasattr(table_exp, "name"):
            name = table_exp.name
            if isinstance(name, str):
                return name.strip('`"').lower() or None
        if hasattr(table_exp, "this") and isinstance(table_exp.this, exp.Table):
            name = table_exp.this.name or ""
            return name.strip('`"').lower() or None
        return None

    def _table_from_create(self, node: exp.Create) -> Optional[exp.Table]:
        """Extract table from CREATE statement."""
        target = node.this
        if isinstance(target, exp.Table):
            return target
        if isinstance(target, exp.Schema) and isinstance(target.this, exp.Table):
            return target.this
        return None

    def _table_from_alter(self, node: exp.Alter) -> Optional[exp.Table]:
        """Extract table from ALTER statement."""
        target = node.this
        if isinstance(target, exp.Table):
            return target
        return None

    def _table_from_drop(self, node: exp.Drop) -> Optional[exp.Table]:
        """Extract table from DROP statement."""
        target = node.this
        if isinstance(target, exp.Table):
            return target
        return None
