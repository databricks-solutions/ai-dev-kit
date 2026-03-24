"""PDF document generation with LLM and parallelization."""

import json
import logging
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

from ..auth import get_workspace_client
from ..unity_catalog.volume_files import upload_to_volume
from .llm import call_llm
from .models import (
    DocSize,
    DocumentSpecification,
    DocumentSpecifications,
    PDFBatchResult,
    PDFGenerationResult,
)

logger = logging.getLogger(__name__)


# =============================================================================
# VALIDATION
# =============================================================================


def _validate_volume_path(catalog: str, schema: str, volume: str) -> None:
    """Validate that the catalog, schema, and volume exist.

    Raises:
        ValueError: If any of the components don't exist
    """
    w = get_workspace_client()

    # Check schema exists (this implicitly checks catalog too)
    try:
        w.schemas.get(full_name=f"{catalog}.{schema}")
    except Exception as e:
        raise ValueError(f"Schema '{catalog}.{schema}' does not exist: {e}") from e

    # Check volume exists
    try:
        w.volumes.read(name=f"{catalog}.{schema}.{volume}")
    except Exception as e:
        raise ValueError(f"Volume '{catalog}.{schema}.{volume}' does not exist: {e}") from e


# =============================================================================
# PROMPTS
# =============================================================================

# Size configurations for document generation
_SIZE_CONFIG = {
    DocSize.SMALL: {
        "pages": "1 page",
        "max_tokens": 4000,
        "content_guidance": "Keep it concise and focused. Include only the most essential information.",
        "structure": (
            "Use a simple structure: title, brief introduction, main content (2-3 short sections), and conclusion."
        ),
    },
    DocSize.MEDIUM: {
        "pages": "4-6 pages",
        "max_tokens": 12000,
        "content_guidance": ("Provide comprehensive coverage with good detail. Include examples and explanations."),
        "structure": (
            "Use a standard structure: title, table of contents, introduction, "
            "multiple detailed sections, examples, and conclusion."
        ),
    },
    DocSize.LARGE: {
        "pages": "10+ pages",
        "max_tokens": 20000,
        "content_guidance": (
            "Be exhaustive and thorough. Include extensive examples, edge cases, troubleshooting, and appendices."
        ),
        "structure": (
            "Use a comprehensive structure: title page, table of contents, executive summary, "
            "multiple chapters with subsections, detailed examples, appendices, and glossary."
        ),
    },
}


def _get_document_list_prompt(description: str, count: int) -> str:
    """Generate prompt for document list generation."""
    return f"""Generate exactly {count} document specifications based on this description:

DESCRIPTION: {description}

Each document must have:
- title: Professional, descriptive title
- category: One of Technical, Procedures, Guides, Templates, or Reference
- model: Unique ID (e.g., "DOC-001", "PROC-AUTH-01")
- description: What the document contains, with specific details from the description above
- question: A specific question answerable by reading this document
- guideline: How to evaluate if an answer is correct (without giving the exact answer)

Make documents diverse, covering different aspects of the description. Generate exactly {count} documents."""


def _get_html_generation_prompt(doc_spec: DocumentSpecification, description: str, doc_size: DocSize) -> str:
    """Generate prompt for HTML content generation."""
    config = _SIZE_CONFIG[doc_size]

    return f"""Generate professional HTML5 documentation for RAG applications.

DOCUMENT:
- Title: {doc_spec.title}
- Category: {doc_spec.category}
- ID: {doc_spec.model}
- Description: {doc_spec.description}

CONTEXT: {description}

TARGET LENGTH: {config["pages"]}

CONTENT GUIDANCE: {config["content_guidance"]}

STRUCTURE: {config["structure"]}

Generate complete, valid HTML5 (<!DOCTYPE html>, <html>, <head>, <style>, <body>). No markdown wrapping."""


def _get_html_system_prompt(doc_size: DocSize) -> str:
    """Get system prompt for HTML generation based on document size."""
    base_prompt = """You are a technical documentation specialist creating HTML documents for PDF conversion.

DOCUMENT TYPE ADAPTATION:
- Technical: Precise language, code examples, procedures
- HR/Policy: Friendly language, policy explanations, FAQs
- Training: Educational tone, objectives, exercises
- User Guides: Clear language, scenarios, tips

HTML REQUIREMENTS:
- Complete HTML5: <!DOCTYPE html>, <html>, <head>, <style>, <body>
- Output ONLY valid HTML - no markdown wrapping
- Professional formatting: headings (h1-h4), paragraphs, lists, tables

CSS REQUIREMENTS (CRITICAL - PyMuPDF compatibility):
- Use ONLY CSS 2.1 syntax
- NO CSS variables (--var-name)
- NO complex selectors (:has, :is, :where)
- Simple selectors only: .class, element
- Safe properties: color, background-color, font-family, font-size, margin, padding, border, text-align"""

    size_specific = {
        DocSize.SMALL: """

SMALL DOCUMENT (~1 page):
- Brief, focused content
- 2-3 short sections maximum
- No table of contents needed
- Essential information only
- Minimal styling""",
        DocSize.MEDIUM: """

MEDIUM DOCUMENT (~4-6 pages):
- Comprehensive coverage
- Table of contents with anchor links
- Multiple sections with examples
- Balanced detail level
- Professional styling""",
        DocSize.LARGE: """

LARGE DOCUMENT (~10+ pages):
- Exhaustive, thorough coverage
- Detailed table of contents
- Multiple chapters with subsections
- Extensive examples and code snippets
- Troubleshooting sections
- Appendices and references
- Full professional styling""",
    }

    return base_prompt + size_specific[doc_size]


# =============================================================================
# HTML TO PDF CONVERSION
# =============================================================================


def _convert_html_to_pdf(html_content: str, output_path: str) -> bool:
    """Convert HTML content to PDF using PyMuPDF.

    Args:
        html_content: HTML string to convert
        output_path: Path where PDF should be saved

    Returns:
        True if successful, False otherwise
    """
    output_dir = Path(output_path).parent
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        import fitz  # PyMuPDF

        logger.debug(f"Converting HTML to PDF using PyMuPDF: {output_path}")

        # Create a Story from the HTML
        story = fitz.Story(html=html_content)

        # Create DocumentWriter
        writer = fitz.DocumentWriter(output_path)

        # Define page layout function
        def rect_fn(page_num, filled_rect):
            page_rect = fitz.Rect(0, 0, 595, 842)  # A4 page size (in points)
            content_rect = fitz.Rect(50, 50, 545, 792)  # Margins (50pt = ~0.7 inches)
            footer_rect = fitz.Rect(0, 0, 0, 0)  # No footer area
            return page_rect, content_rect, footer_rect

        # Write the story to PDF with proper pagination and formatting
        story.write(writer, rect_fn)
        writer.close()

        # Check if file was created successfully
        if Path(output_path).exists():
            file_size = Path(output_path).stat().st_size
            logger.info(f"PDF saved: {output_path} (size: {file_size:,} bytes)")
            return True
        else:
            logger.error("PyMuPDF conversion failed - file not created")
            return False

    except ImportError:
        logger.error("PyMuPDF is not installed. Install with: pip install pymupdf")
        return False
    except Exception as e:
        logger.error(f"Failed to convert HTML to PDF: {str(e)}", exc_info=True)
        return False


# =============================================================================
# VOLUME OPERATIONS
# =============================================================================


def _delete_folder_contents(catalog: str, schema: str, volume: str, folder: str, max_workers: int = 5) -> None:
    """Delete all files in a volume folder in parallel."""
    w = get_workspace_client()
    volume_path = f"/Volumes/{catalog}/{schema}/{volume}/{folder}"

    def delete_file(file_path: str) -> bool:
        try:
            w.files.delete(file_path)
            logger.debug(f"Deleted: {file_path}")
            return True
        except Exception as e:
            logger.warning(f"Could not delete {file_path}: {e}")
            return False

    try:
        files = list(w.files.list_directory_contents(volume_path))
        if not files:
            return

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(delete_file, f.path): f.path for f in files}
            for future in as_completed(futures):
                future.result()  # Raise any exceptions

        logger.info(f"Cleared folder contents: {volume_path} ({len(files)} files)")
    except Exception as e:
        # Folder might not exist yet, which is fine
        logger.debug(f"Folder does not exist or could not be listed: {volume_path} - {e}")


def _upload_to_volume(local_path: str, catalog: str, schema: str, volume: str, folder: str, filename: str) -> bool:
    """Upload a file to a volume, creating the folder if needed."""
    from ..unity_catalog.volume_files import create_volume_directory

    folder_path = f"/Volumes/{catalog}/{schema}/{volume}/{folder}"
    volume_path = f"{folder_path}/{filename}"

    # Ensure folder exists
    try:
        create_volume_directory(folder_path)
    except Exception as e:
        logger.debug(f"Folder may already exist: {folder_path} - {e}")

    result = upload_to_volume(local_path, volume_path, overwrite=True)
    if result.success:
        logger.debug(f"Uploaded: {volume_path}")
        return True
    else:
        logger.error(f"Failed to upload {local_path} to {volume_path}: {result.error}")
        return False


# =============================================================================
# SINGLE PDF GENERATION
# =============================================================================


def generate_single_pdf(
    doc_spec: DocumentSpecification,
    description: str,
    catalog: str,
    schema: str,
    volume: str,
    folder: str,
    temp_dir: str,
    doc_size: DocSize = DocSize.MEDIUM,
) -> PDFGenerationResult:
    """Generate a single PDF from a document specification.

    Args:
        doc_spec: Document specification with title, description, etc.
        description: Overall context description
        catalog: Unity Catalog name
        schema: Schema name
        volume: Volume name
        folder: Folder within volume
        temp_dir: Temporary directory for local file creation
        doc_size: Size of document to generate (SMALL, MEDIUM, LARGE). Default: MEDIUM

    Returns:
        PDFGenerationResult with paths and success status

    Raises:
        ValueError: If catalog, schema, or volume don't exist
    """
    # Validate volume path exists before doing any LLM work
    _validate_volume_path(catalog, schema, volume)

    try:
        import time

        # Generate safe filename from model identifier
        safe_name = doc_spec.model.replace(" ", "_").replace("-", "_").lower()

        logger.info(f"Generating PDF: {doc_spec.title} ({safe_name}) - size: {doc_size.value}")

        # Step 1: Generate HTML content
        html_prompt = _get_html_generation_prompt(doc_spec, description, doc_size)
        system_prompt = _get_html_system_prompt(doc_size)
        max_tokens = _SIZE_CONFIG[doc_size]["max_tokens"]

        t0 = time.time()
        html_content = call_llm(
            prompt=html_prompt,
            system_prompt=system_prompt,
            mini=True,
            max_tokens=max_tokens,
        )
        logger.info(f"[{safe_name}] LLM call took {time.time() - t0:.1f}s")

        # Step 2: Convert HTML to PDF
        pdf_filename = f"{safe_name}.pdf"
        local_pdf_path = str(Path(temp_dir) / pdf_filename)

        if not _convert_html_to_pdf(html_content, local_pdf_path):
            return PDFGenerationResult(
                pdf_path="",
                success=False,
                error=f"Failed to convert HTML to PDF for {doc_spec.title}",
            )

        # Step 3: Upload PDF to volume
        if not _upload_to_volume(local_pdf_path, catalog, schema, volume, folder, pdf_filename):
            return PDFGenerationResult(
                pdf_path="",
                success=False,
                error=f"Failed to upload PDF for {doc_spec.title}",
            )

        volume_pdf_path = f"/Volumes/{catalog}/{schema}/{volume}/{folder}/{pdf_filename}"

        # Step 4: Save question/guideline JSON
        question_data = {
            "title": doc_spec.title,
            "category": doc_spec.category,
            "pdf_path": volume_pdf_path,
            "question": doc_spec.question,
            "guideline": doc_spec.guideline,
        }

        json_filename = f"{safe_name}.json"
        local_json_path = str(Path(temp_dir) / json_filename)

        with open(local_json_path, "w") as f:
            json.dump(question_data, f, indent=2)

        volume_json_path = None
        if _upload_to_volume(local_json_path, catalog, schema, volume, folder, json_filename):
            volume_json_path = f"/Volumes/{catalog}/{schema}/{volume}/{folder}/{json_filename}"

        logger.info(f"Successfully generated: {doc_spec.title}")

        return PDFGenerationResult(
            pdf_path=volume_pdf_path,
            question_path=volume_json_path,
            success=True,
        )

    except Exception as e:
        error_msg = f"Error generating PDF for {doc_spec.title}: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return PDFGenerationResult(
            pdf_path="",
            success=False,
            error=error_msg,
        )


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================


def generate_pdf_documents(
    catalog: str,
    schema: str,
    description: str,
    count: int,
    volume: str = "raw_data",
    folder: str = "pdf_documents",
    doc_size: DocSize = DocSize.MEDIUM,
    overwrite_folder: bool = False,
    max_workers: int = 4,
    temp_dir: Optional[str] = None,
) -> PDFBatchResult:
    """Generate multiple PDF documents based on a description.

    This is the main entry point for PDF generation. It follows a 2-step process:
    1. Generate a list of document specifications using LLM
    2. Generate PDFs in parallel from those specifications

    Args:
        catalog: Unity Catalog name
        schema: Schema name
        description: Detailed description of what PDFs should contain
        count: Number of PDFs to generate
        volume: Volume name (must already exist). Default: "raw_data"
        folder: Folder within volume for PDFs. Default: "pdf_documents"
        doc_size: Size of documents (SMALL=~1 page, MEDIUM=~5 pages, LARGE=~10+ pages). Default: MEDIUM
        overwrite_folder: If True, delete existing folder content first (default: False)
        max_workers: Maximum concurrent PDF generations (default: 4)
        temp_dir: Optional directory for local PDF files (kept after generation).
                  If None, uses a temporary directory that is cleaned up.

    Returns:
        PDFBatchResult with success status and statistics

    Raises:
        ValueError: If catalog, schema, or volume don't exist
    """
    volume_path = f"/Volumes/{catalog}/{schema}/{volume}/{folder}"
    errors: list[str] = []

    logger.info(f"Starting PDF generation: {count} documents to {volume_path}")

    # Validate volume path exists before doing any LLM work
    _validate_volume_path(catalog, schema, volume)

    try:
        # Clear folder if requested
        if overwrite_folder:
            logger.info(f"Clearing existing folder contents: {volume_path}")
            _delete_folder_contents(catalog, schema, volume, folder)

        import time

        # Step 1: Generate document specifications
        logger.info(f"Step 1: Generating {count} document specifications...")

        doc_list_prompt = _get_document_list_prompt(description, count)
        system_prompt = """You are an expert technical documentation specialist. \
Generate document specifications based on the given description.

Return a JSON object with a "documents" array containing exactly the requested number \
of document specifications. Each document should have:
- title: string
- category: string (Technical, Procedures, Guides, Templates, or Reference)
- model: string (unique identifier like DOC-001)
- description: string
- question: string
- guideline: string"""

        t0 = time.time()
        doc_list_response = call_llm(
            prompt=doc_list_prompt,
            system_prompt=system_prompt,
            mini=True,
            max_tokens=8000,
            response_format="json_object",
        )
        logger.info(f"Step 1 LLM call took {time.time() - t0:.1f}s")

        try:
            response_data = json.loads(doc_list_response)
            doc_specs_model = DocumentSpecifications(**response_data)
            document_specs = doc_specs_model.documents
        except (json.JSONDecodeError, ValueError) as e:
            error_msg = f"Failed to parse document specifications: {e}. Response: {doc_list_response[:500]}"
            logger.error(error_msg)
            return PDFBatchResult(
                success=False,
                volume_path=volume_path,
                pdfs_generated=0,
                pdfs_failed=count,
                errors=[error_msg],
            )

        if not document_specs:
            return PDFBatchResult(
                success=False,
                volume_path=volume_path,
                pdfs_generated=0,
                pdfs_failed=count,
                errors=["No documents generated in response"],
            )

        logger.info(f"Generated {len(document_specs)} document specifications")

        # Step 2: Generate PDFs in parallel
        logger.info(f"Step 2: Generating PDFs ({max_workers} concurrent)...")

        def run_pdf_generation(working_dir: str) -> list:
            """Run PDF generation tasks in the given directory."""
            results = []

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {
                    executor.submit(
                        generate_single_pdf,
                        doc_spec=doc_spec,
                        description=description,
                        catalog=catalog,
                        schema=schema,
                        volume=volume,
                        folder=folder,
                        temp_dir=working_dir,
                        doc_size=doc_size,
                    ): doc_spec
                    for doc_spec in document_specs
                }

                for future in as_completed(futures):
                    try:
                        result = future.result()
                        results.append(result)
                    except Exception as e:
                        results.append(e)

            return results

        # Use provided temp_dir or create a temporary one
        if temp_dir:
            Path(temp_dir).mkdir(parents=True, exist_ok=True)
            results = run_pdf_generation(temp_dir)
        else:
            with tempfile.TemporaryDirectory() as auto_temp_dir:
                results = run_pdf_generation(auto_temp_dir)

        # Process results
        pdfs_generated = 0
        pdfs_failed = 0

        for result in results:
            if isinstance(result, Exception):
                errors.append(str(result))
                pdfs_failed += 1
            elif isinstance(result, PDFGenerationResult):
                if result.success:
                    pdfs_generated += 1
                else:
                    pdfs_failed += 1
                    if result.error:
                        errors.append(result.error)

        success = pdfs_generated > 0 and pdfs_failed == 0

        logger.info(f"PDF generation complete: {pdfs_generated}/{len(document_specs)} successful")

        return PDFBatchResult(
            success=success,
            volume_path=volume_path,
            pdfs_generated=pdfs_generated,
            pdfs_failed=pdfs_failed,
            errors=errors,
        )

    except Exception as e:
        error_msg = f"PDF generation failed: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return PDFBatchResult(
            success=False,
            volume_path=volume_path,
            pdfs_generated=0,
            pdfs_failed=count,
            errors=[error_msg],
        )
