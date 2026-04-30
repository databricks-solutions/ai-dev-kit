#!/usr/bin/env python3
"""
PDF Generator - Convert HTML files to PDF locally.

Usage:
    # Convert single file
    python pdf_generator.py convert --input ./raw_data/html/report.html --output ./raw_data/pdf

    # Convert entire folder (parallel)
    python pdf_generator.py convert --input ./raw_data/html --output ./raw_data/pdf

    # Force reconvert (ignore timestamps)
    python pdf_generator.py convert --input ./raw_data/html --output ./raw_data/pdf --force

Requires: plutoprint
    uv / pip install plutoprint
"""

import argparse
import logging
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

MAX_WORKERS = 4


@dataclass
class ConversionResult:
    """Result from converting HTML to PDF."""
    html_path: str
    pdf_path: Optional[str] = None
    success: bool = False
    skipped: bool = False
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "html_path": self.html_path,
            "pdf_path": self.pdf_path,
            "success": self.success,
            "skipped": self.skipped,
            "error": self.error,
        }


@dataclass
class BatchResult:
    """Result from batch conversion."""
    total: int = 0
    converted: int = 0
    skipped: int = 0
    failed: int = 0
    results: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "converted": self.converted,
            "skipped": self.skipped,
            "failed": self.failed,
            "results": [r.to_dict() for r in self.results],
        }


def _needs_conversion(html_path: Path, pdf_path: Path) -> bool:
    """Check if HTML needs to be converted (PDF missing or older than HTML).

    Args:
        html_path: Path to HTML file
        pdf_path: Path to output PDF file

    Returns:
        True if conversion needed, False if PDF is up-to-date
    """
    if not pdf_path.exists():
        return True

    html_mtime = html_path.stat().st_mtime
    pdf_mtime = pdf_path.stat().st_mtime

    return html_mtime > pdf_mtime


def convert_html_to_pdf(
    html_path: Path,
    pdf_path: Path,
    force: bool = False,
) -> ConversionResult:
    """Convert a single HTML file to PDF.

    Args:
        html_path: Path to HTML file
        pdf_path: Path to output PDF file
        force: If True, convert even if PDF is up-to-date

    Returns:
        ConversionResult with success/skip/error status
    """
    result = ConversionResult(html_path=str(html_path))

    # Check if conversion needed
    if not force and not _needs_conversion(html_path, pdf_path):
        result.skipped = True
        result.success = True
        result.pdf_path = str(pdf_path)
        logger.debug(f"Skipped (up-to-date): {html_path.name}")
        return result

    # Ensure output directory exists
    pdf_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        import plutoprint

        # Read HTML content
        html_content = html_path.read_text(encoding="utf-8")

        # Convert to PDF
        book = plutoprint.Book(plutoprint.PAGE_SIZE_A4)
        book.load_html(html_content)
        book.write_to_pdf(str(pdf_path))

        if pdf_path.exists():
            result.success = True
            result.pdf_path = str(pdf_path)
            logger.info(f"Converted: {html_path.name} -> {pdf_path.name}")
        else:
            result.error = "PDF file not created"
            logger.error(f"Failed: {html_path.name} - PDF not created")

    except ImportError:
        result.error = "plutoprint not installed. Run: pip install plutoprint"
        logger.error(result.error)
    except Exception as e:
        result.error = str(e)
        logger.error(f"Failed: {html_path.name} - {e}")

    return result


def convert_folder(
    input_dir: Path,
    output_dir: Path,
    force: bool = False,
    max_workers: int = MAX_WORKERS,
) -> BatchResult:
    """Convert all HTML files in a folder to PDF (parallel).

    Preserves subfolder structure from input to output.

    Args:
        input_dir: Directory containing HTML files
        output_dir: Directory for output PDF files
        force: If True, convert even if PDFs are up-to-date
        max_workers: Number of parallel workers (default: 4)

    Returns:
        BatchResult with counts and per-file results
    """
    batch = BatchResult()

    # Find all HTML files
    html_files = list(input_dir.rglob("*.html"))
    batch.total = len(html_files)

    if batch.total == 0:
        logger.warning(f"No HTML files found in {input_dir}")
        return batch

    logger.info(f"Found {batch.total} HTML file(s) in {input_dir}")

    def process_file(html_path: Path) -> ConversionResult:
        # Compute relative path to preserve folder structure
        relative_path = html_path.relative_to(input_dir)
        pdf_relative = relative_path.with_suffix(".pdf")
        pdf_path = output_dir / pdf_relative

        return convert_html_to_pdf(html_path, pdf_path, force=force)

    # Process files in parallel
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(process_file, f): f for f in html_files}

        for future in as_completed(futures):
            result = future.result()
            batch.results.append(result)

            if result.skipped:
                batch.skipped += 1
            elif result.success:
                batch.converted += 1
            else:
                batch.failed += 1

    logger.info(f"Done: {batch.converted} converted, {batch.skipped} skipped, {batch.failed} failed")
    return batch


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Convert HTML files to PDF",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Convert single file
    python pdf_generator.py convert --input ./raw_data/html/report.html --output ./raw_data/pdf

    # Convert entire folder (parallel)
    python pdf_generator.py convert --input ./raw_data/html --output ./raw_data/pdf

    # Force reconvert all
    python pdf_generator.py convert --input ./raw_data/html --output ./raw_data/pdf --force
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Convert command
    conv_parser = subparsers.add_parser("convert", help="Convert HTML to PDF")
    conv_parser.add_argument("--input", "-i", required=True, help="Input HTML file or folder")
    conv_parser.add_argument("--output", "-o", required=True, help="Output folder for PDFs")
    conv_parser.add_argument("--force", "-f", action="store_true", help="Force reconvert (ignore timestamps)")
    conv_parser.add_argument("--workers", "-w", type=int, default=MAX_WORKERS, help=f"Parallel workers (default: {MAX_WORKERS})")

    args = parser.parse_args()

    if args.command == "convert":
        input_path = Path(args.input)
        output_path = Path(args.output)

        if not input_path.exists():
            print(f"Error: Input path does not exist: {input_path}")
            sys.exit(1)

        if input_path.is_file():
            # Single file conversion
            if not input_path.suffix.lower() == ".html":
                print(f"Error: Input file must be .html: {input_path}")
                sys.exit(1)

            pdf_path = output_path / input_path.with_suffix(".pdf").name
            result = convert_html_to_pdf(input_path, pdf_path, force=args.force)

            if result.skipped:
                print(f"Skipped (up-to-date): {result.pdf_path}")
            elif result.success:
                print(f"Converted: {result.pdf_path}")
            else:
                print(f"Error: {result.error}")
                sys.exit(1)
        else:
            # Folder conversion
            batch = convert_folder(
                input_path,
                output_path,
                force=args.force,
                max_workers=args.workers,
            )

            print(f"\nSummary: {batch.converted} converted, {batch.skipped} skipped, {batch.failed} failed")
            if batch.failed > 0:
                sys.exit(1)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
