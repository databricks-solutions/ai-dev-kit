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
    """Convert HTML to PDF and upload to a Unity Catalog volume.

    Takes complete HTML content (including styles) and converts it to a PDF document,
    then uploads it to the specified Unity Catalog volume.

    Args:
        html_content: Complete HTML document including <!DOCTYPE html>, <html>, <head>,
            <style>, and <body> tags. Use modern CSS3 for styling.
        filename: Name for the PDF file (e.g., "report.pdf" or "report" - .pdf added if missing)
        catalog: Unity Catalog name
        schema: Schema name
        volume: Volume name (must already exist). Default: "raw_data"
        folder: Optional folder within volume (e.g., "documents")

    Returns:
        Dictionary with:
        - success: True if PDF generated and uploaded successfully
        - volume_path: Full path to the PDF in the volume (if successful)
        - error: Error message (if failed)

    Example:
        >>> generate_and_upload_pdf(
        ...     html_content='''<!DOCTYPE html>
        ...     <html>
        ...     <head><style>body { font-family: Arial; } h1 { color: #333; }</style></head>
        ...     <body><h1>My Report</h1><p>Content here...</p></body>
        ...     </html>''',
        ...     filename="my_report.pdf",
        ...     catalog="my_catalog",
        ...     schema="my_schema",
        ... )
        {
            "success": True,
            "volume_path": "/Volumes/my_catalog/my_schema/raw_data/my_report.pdf",
            "error": None
        }
    """
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
