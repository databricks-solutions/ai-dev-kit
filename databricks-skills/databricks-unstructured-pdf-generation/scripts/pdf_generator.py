#!/usr/bin/env python3
"""
PDF Generator - Self-contained HTML to PDF generation and upload to Unity Catalog volumes.

Usage:
    python pdf_generator.py generate --html '<html>...</html>' --filename report.pdf --catalog my_catalog --schema my_schema
    python pdf_generator.py generate --html-file input.html --filename report.pdf --catalog my_catalog --schema my_schema --volume raw_data --folder docs

Requires: plutoprint
    pip install plutoprint
"""

import argparse
import json
import logging
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class PDFResult:
    """Result from generating a PDF."""
    success: bool
    volume_path: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "volume_path": self.volume_path,
            "error": self.error,
        }


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


def _run_cli(args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    """Run a databricks CLI command.

    Args:
        args: Command arguments (without 'databricks' prefix)
        check: Whether to raise on non-zero exit code

    Returns:
        CompletedProcess with stdout/stderr
    """
    cmd = ["databricks"] + args
    logger.debug(f"Running: {' '.join(cmd)}")
    return subprocess.run(cmd, capture_output=True, text=True, check=check)


def _validate_volume_exists(catalog: str, schema: str, volume: str) -> Optional[str]:
    """Validate that the volume exists using CLI.

    Args:
        catalog: Catalog name
        schema: Schema name
        volume: Volume name

    Returns:
        Error message if validation fails, None if successful
    """
    # Check volume exists
    result = _run_cli(["volumes", "read", f"{catalog}.{schema}.{volume}"], check=False)
    if result.returncode != 0:
        return f"Volume '{catalog}.{schema}.{volume}' does not exist or is not accessible: {result.stderr}"
    return None


def _upload_to_volume(local_path: str, volume_path: str) -> Optional[str]:
    """Upload a file to Unity Catalog volume using CLI.

    Args:
        local_path: Local file path
        volume_path: Volume path (e.g., /Volumes/catalog/schema/volume/file.pdf)

    Returns:
        Error message if upload fails, None if successful
    """
    result = _run_cli(["fs", "cp", local_path, volume_path, "--overwrite"], check=False)
    if result.returncode != 0:
        return f"Failed to upload to {volume_path}: {result.stderr}"
    return None


def _create_volume_directory(volume_path: str) -> None:
    """Create a directory in the volume using CLI (best effort).

    Args:
        volume_path: Volume directory path
    """
    # Use fs mkdirs - it's idempotent
    _run_cli(["fs", "mkdirs", volume_path], check=False)


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
    error = _validate_volume_exists(catalog, schema, volume)
    if error:
        return PDFResult(success=False, error=error)

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
                folder_path = f"/Volumes/{catalog}/{schema}/{volume}/{folder}"
                _create_volume_directory(folder_path)

            # Upload to volume
            error = _upload_to_volume(local_pdf_path, volume_path)
            if error:
                return PDFResult(success=False, error=error)

            logger.info(f"PDF uploaded to {volume_path}")
            return PDFResult(success=True, volume_path=volume_path)

    except Exception as e:
        error_msg = f"Error generating PDF: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return PDFResult(success=False, error=error_msg)


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Generate PDFs from HTML and upload to Unity Catalog volumes",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Generate from inline HTML
    python pdf_generator.py generate --html '<html><body><h1>Hello</h1></body></html>' \\
        --filename hello.pdf --catalog my_catalog --schema my_schema

    # Generate from HTML file
    python pdf_generator.py generate --html-file input.html \\
        --filename report.pdf --catalog my_catalog --schema my_schema --folder reports
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Generate command
    gen_parser = subparsers.add_parser("generate", help="Generate PDF from HTML")
    gen_parser.add_argument("--html", help="HTML content as string")
    gen_parser.add_argument("--html-file", help="Path to HTML file")
    gen_parser.add_argument("--filename", required=True, help="Output PDF filename")
    gen_parser.add_argument("--catalog", required=True, help="Unity Catalog name")
    gen_parser.add_argument("--schema", required=True, help="Schema name")
    gen_parser.add_argument("--volume", default="raw_data", help="Volume name (default: raw_data)")
    gen_parser.add_argument("--folder", help="Optional folder within volume")
    gen_parser.add_argument("--json", action="store_true", help="Output result as JSON")

    args = parser.parse_args()

    if args.command == "generate":
        # Get HTML content
        if args.html:
            html_content = args.html
        elif args.html_file:
            with open(args.html_file, "r") as f:
                html_content = f.read()
        else:
            print("Error: Either --html or --html-file is required")
            sys.exit(1)

        result = generate_and_upload_pdf(
            html_content=html_content,
            filename=args.filename,
            catalog=args.catalog,
            schema=args.schema,
            volume=args.volume,
            folder=args.folder,
        )

        if args.json:
            print(json.dumps(result.to_dict(), indent=2))
        else:
            if result.success:
                print(f"Success: PDF uploaded to {result.volume_path}")
            else:
                print(f"Error: {result.error}")
                sys.exit(1)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
