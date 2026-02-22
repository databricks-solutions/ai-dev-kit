"""Tool description extraction and writing for MCP server tools.

Extracts @mcp.tool docstrings from Python source files, formats them for GEPA
optimization, and writes optimized descriptions back to source files.

Each tool module (sql.py, compute.py, etc.) becomes one GEPA component so
GEPA's round-robin selector cycles through modules efficiently.
"""

import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Separator used between tools within a module's GEPA component text
TOOL_SEPARATOR = "\n\n### TOOL: "

MCP_TOOLS_DIR = Path(__file__).resolve().parents[5] / "databricks-mcp-server" / "databricks_mcp_server" / "tools"


@dataclass
class ToolDescription:
    """A single tool's description extracted from source."""

    name: str  # Function name
    docstring: str  # The full docstring text
    module: str  # Module name (e.g., "sql", "compute")
    lineno: int  # Line number of the function def
    source_path: Path  # Path to the source file


def _find_tools_dir() -> Path:
    """Find the MCP tools directory."""
    if MCP_TOOLS_DIR.exists():
        return MCP_TOOLS_DIR
    # Fallback: search from repo root
    from .evaluator import _find_repo_root

    repo_root = _find_repo_root()
    candidate = repo_root / "databricks-mcp-server" / "databricks_mcp_server" / "tools"
    if candidate.exists():
        return candidate
    raise FileNotFoundError(
        "Could not find MCP tools directory. "
        "Expected at databricks-mcp-server/databricks_mcp_server/tools/"
    )


def extract_tool_descriptions(
    modules: list[str] | None = None,
    tools_dir: Path | None = None,
) -> dict[str, list[ToolDescription]]:
    """Extract all @mcp.tool docstrings from MCP server tool files.

    Args:
        modules: Optional list of module names to extract (e.g., ["sql", "compute"]).
                 If None, extracts all modules.
        tools_dir: Override path to tools directory.

    Returns:
        Dict mapping module_name -> list of ToolDescription.
    """
    if tools_dir is None:
        tools_dir = _find_tools_dir()

    results: dict[str, list[ToolDescription]] = {}

    for py_file in sorted(tools_dir.glob("*.py")):
        module_name = py_file.stem
        if module_name == "__init__":
            continue
        if modules and module_name not in modules:
            continue

        source = py_file.read_text()
        tree = ast.parse(source)

        tool_descs = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            # Check if decorated with @mcp.tool
            for dec in node.decorator_list:
                is_mcp_tool = False
                if isinstance(dec, ast.Attribute) and isinstance(dec.value, ast.Name):
                    if dec.value.id == "mcp" and dec.attr == "tool":
                        is_mcp_tool = True
                elif isinstance(dec, ast.Name) and dec.id == "mcp":
                    is_mcp_tool = True
                if is_mcp_tool:
                    docstring = ast.get_docstring(node) or ""
                    tool_descs.append(
                        ToolDescription(
                            name=node.name,
                            docstring=docstring,
                            module=module_name,
                            lineno=node.lineno,
                            source_path=py_file,
                        )
                    )
                    break

        if tool_descs:
            results[module_name] = tool_descs

    return results


def tools_to_gepa_components(
    tool_map: dict[str, list[ToolDescription]],
    per_module: bool = True,
) -> dict[str, str]:
    """Convert extracted tool descriptions into GEPA component text blocks.

    Args:
        tool_map: Output of extract_tool_descriptions()
        per_module: If True, one GEPA component per module (e.g., "tools_sql").
                    If False, all tools in a single "tool_descriptions" component.

    Returns:
        Dict mapping component_name -> text block.
    """
    if per_module:
        components = {}
        for module_name, tools in tool_map.items():
            text_parts = []
            for td in tools:
                text_parts.append(f"### TOOL: {td.name}\n{td.docstring}")
            components[f"tools_{module_name}"] = "\n\n".join(text_parts)
        return components
    else:
        all_parts = []
        for module_name, tools in sorted(tool_map.items()):
            for td in tools:
                all_parts.append(f"### TOOL: {td.name} (module: {module_name})\n{td.docstring}")
        return {"tool_descriptions": "\n\n".join(all_parts)}


def parse_gepa_component(component_text: str) -> dict[str, str]:
    """Parse a GEPA component text block back into individual tool descriptions.

    Args:
        component_text: Text block with ### TOOL: markers

    Returns:
        Dict mapping tool_name -> optimized docstring
    """
    tools = {}
    parts = re.split(r"### TOOL:\s*", component_text)
    for part in parts:
        part = part.strip()
        if not part:
            continue
        # First line has the tool name (possibly with module annotation)
        lines = part.split("\n", 1)
        name_line = lines[0].strip()
        # Remove module annotation if present: "execute_sql (module: sql)"
        name = re.match(r"(\w+)", name_line).group(1) if re.match(r"(\w+)", name_line) else name_line
        docstring = lines[1].strip() if len(lines) > 1 else ""
        tools[name] = docstring
    return tools


def write_tool_descriptions(
    optimized: dict[str, str],
    tool_map: dict[str, list[ToolDescription]],
) -> list[Path]:
    """Write optimized docstrings back to MCP server source files.

    Uses AST to locate the exact docstring positions and replaces them
    in the source text while preserving all other code.

    Args:
        optimized: Dict mapping tool_name -> optimized docstring text
        tool_map: Original extraction map (for source file locations)

    Returns:
        List of modified file paths
    """
    # Group updates by file
    updates_by_file: dict[Path, list[tuple[ToolDescription, str]]] = {}
    for module_name, tools in tool_map.items():
        for td in tools:
            if td.name in optimized:
                updates_by_file.setdefault(td.source_path, []).append((td, optimized[td.name]))

    modified_files = []
    for file_path, updates in updates_by_file.items():
        source = file_path.read_text()
        tree = ast.parse(source)
        source_lines = source.splitlines(keepends=True)

        # Process updates in reverse line order to preserve positions
        updates_sorted = sorted(updates, key=lambda x: x[0].lineno, reverse=True)

        for td, new_docstring in updates_sorted:
            # Find the function node
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and node.name == td.name and node.lineno == td.lineno:
                    # Find the docstring node (first Expr with a Constant string)
                    if (
                        node.body
                        and isinstance(node.body[0], ast.Expr)
                        and isinstance(node.body[0].value, ast.Constant)
                        and isinstance(node.body[0].value.value, str)
                    ):
                        doc_node = node.body[0]
                        # Get the docstring's line range
                        start_line = doc_node.lineno - 1  # 0-indexed
                        end_line = doc_node.end_lineno  # exclusive

                        # Detect indentation from the original docstring line
                        original_line = source_lines[start_line]
                        indent = re.match(r"(\s*)", original_line).group(1)

                        # Build new docstring with proper indentation
                        new_doc_lines = [f'{indent}"""\n']
                        for line in new_docstring.split("\n"):
                            if line.strip():
                                new_doc_lines.append(f"{indent}{line}\n")
                            else:
                                new_doc_lines.append("\n")
                        new_doc_lines.append(f'{indent}"""\n')

                        # Replace lines
                        source_lines[start_line:end_line] = new_doc_lines
                    break

        new_source = "".join(source_lines)

        # Validate the new source parses
        try:
            ast.parse(new_source)
        except SyntaxError as e:
            print(f"WARNING: Optimized source for {file_path.name} has syntax error: {e}")
            print("Skipping this file.")
            continue

        file_path.write_text(new_source)
        modified_files.append(file_path)

    return modified_files


def list_tool_modules(tools_dir: Path | None = None) -> list[str]:
    """List available tool module names."""
    if tools_dir is None:
        tools_dir = _find_tools_dir()
    return sorted(
        f.stem for f in tools_dir.glob("*.py")
        if f.stem != "__init__"
    )


def get_tool_stats(tools_dir: Path | None = None) -> dict[str, Any]:
    """Get statistics about available MCP tools."""
    tool_map = extract_tool_descriptions(tools_dir=tools_dir)
    total_tools = sum(len(tools) for tools in tool_map.values())
    total_chars = sum(
        len(td.docstring) for tools in tool_map.values() for td in tools
    )
    return {
        "modules": len(tool_map),
        "total_tools": total_tools,
        "total_description_chars": total_chars,
        "per_module": {
            name: {"tools": len(tools), "chars": sum(len(td.docstring) for td in tools)}
            for name, tools in tool_map.items()
        },
    }
