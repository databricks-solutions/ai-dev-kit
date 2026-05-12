"""PDF tools - Convert HTML to PDF and upload to Unity Catalog volumes."""

from typing import Any, Dict, Optional

from databricks_tools_core.pdf import generate_and_upload_pdf as _generate_and_upload_pdf

from ..server import mcp


@mcp.tool
def generate_and_upload_pdf(
    html_content: str,
    filename: str,
    catalog: str,
    schema: str,
    volume: str = "raw_data",
    folder: Optional[str] = None,
) -> Dict[str, Any]:
    """Convert complete HTML (with styles) to PDF and upload to Unity Catalog volume.

    Returns: {success, volume_path, error}."""
    result = _generate_and_upload_pdf(
        html_content=html_content,
        filename=filename,
        catalog=catalog,
        schema=schema,
        volume=volume,
        folder=folder,
    )

    return {
        "success": result.success,
        "volume_path": result.volume_path,
        "error": result.error,
    }
