"""PDF document generation - convert HTML to PDF and upload to Unity Catalog volumes."""

import logging
import tempfile
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

from ..auth import get_workspace_client
from ..unity_catalog.volume_files import upload_to_volume

logger = logging.getLogger(__name__)


class PDFResult(BaseModel):
    """Result from generating a PDF."""

    success: bool
    volume_path: Optional[str] = None
    error: Optional[str] = None


def _convert_html_to_pdf(html_content: str, output_path: str) -> bool:
    """Convert HTML content to PDF using PlutoPrint.

    Args:
        html_content: HTML string to convert
        output_path: Path where PDF should be saved

    Returns:
        True if successful, False otherwise
    """
    output_dir = Path(output_path).parent
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        import plutoprint

        logger.debug(f"Converting HTML to PDF using PlutoPrint: {output_path}")

        book = plutoprint.Book(plutoprint.PAGE_SIZE_A4)
        book.load_html(html_content)
        book.write_to_pdf(output_path)

        if Path(output_path).exists():
            file_size = Path(output_path).stat().st_size
            logger.info(f"PDF saved: {output_path} (size: {file_size:,} bytes)")
            return True
        else:
            logger.error("PlutoPrint conversion failed - file not created")
            return False

    except ImportError:
        logger.error("PlutoPrint is not installed. Install with: pip install plutoprint")
        return False
    except Exception as e:
        logger.error(f"Failed to convert HTML to PDF: {str(e)}", exc_info=True)
        return False


def _validate_volume_path(catalog: str, schema: str, volume: str) -> None:
    """Validate that the catalog, schema, and volume exist."""
    w = get_workspace_client()

    try:
        w.schemas.get(full_name=f"{catalog}.{schema}")
    except Exception as e:
        raise ValueError(f"Schema '{catalog}.{schema}' does not exist: {e}") from e

    try:
        w.volumes.read(name=f"{catalog}.{schema}.{volume}")
    except Exception as e:
        raise ValueError(f"Volume '{catalog}.{schema}.{volume}' does not exist: {e}") from e


def generate_and_upload_pdf(
    html_content: str,
    filename: str,
    catalog: str,
    schema: str,
    volume: str = "raw_data",
    folder: Optional[str] = None,
) -> PDFResult:
    """Convert HTML to PDF and upload to a Unity Catalog volume.

    Args:
        html_content: Complete HTML document (including <!DOCTYPE html>, <html>, <head>, <style>, <body>)
        filename: Name for the PDF file (e.g., "report.pdf" or "report" - .pdf added if missing)
        catalog: Unity Catalog name
        schema: Schema name
        volume: Volume name (default: "raw_data")
        folder: Optional folder within volume (e.g., "documents")

    Returns:
        PDFResult with success status and volume_path if successful

    Example:
        >>> html = '''
        ... <!DOCTYPE html>
        ... <html>
        ... <head><style>body { font-family: Arial; }</style></head>
        ... <body><h1>Hello World</h1></body>
        ... </html>
        ... '''
        >>> result = generate_and_upload_pdf(
        ...     html_content=html,
        ...     filename="hello.pdf",
        ...     catalog="my_catalog",
        ...     schema="my_schema",
        ... )
        >>> print(result.volume_path)
        /Volumes/my_catalog/my_schema/raw_data/hello.pdf
    """
    # Ensure filename ends with .pdf
    if not filename.lower().endswith(".pdf"):
        filename = f"{filename}.pdf"

    # Validate volume exists
    try:
        _validate_volume_path(catalog, schema, volume)
    except ValueError as e:
        return PDFResult(success=False, error=str(e))

    # Build volume path
    if folder:
        volume_path = f"/Volumes/{catalog}/{schema}/{volume}/{folder}/{filename}"
    else:
        volume_path = f"/Volumes/{catalog}/{schema}/{volume}/{filename}"

    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            local_pdf_path = str(Path(temp_dir) / filename)

            # Convert HTML to PDF
            if not _convert_html_to_pdf(html_content, local_pdf_path):
                return PDFResult(success=False, error="Failed to convert HTML to PDF")

            # Create folder if needed
            if folder:
                from ..unity_catalog.volume_files import create_volume_directory

                folder_path = f"/Volumes/{catalog}/{schema}/{volume}/{folder}"
                try:
                    create_volume_directory(folder_path)
                except Exception:
                    pass  # Folder may already exist

            # Upload to volume
            result = upload_to_volume(local_pdf_path, volume_path, overwrite=True)
            if not result.success:
                return PDFResult(success=False, error=f"Failed to upload PDF: {result.error}")

            logger.info(f"PDF uploaded to {volume_path}")
            return PDFResult(success=True, volume_path=volume_path)

    except Exception as e:
        error_msg = f"Error generating PDF: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return PDFResult(success=False, error=error_msg)
