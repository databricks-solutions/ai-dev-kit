"""PDF tools - Generate synthetic PDF documents for RAG/unstructured data use cases."""

import tempfile
from typing import Any, Dict, Literal

from databricks_tools_core.pdf import DocSize
from databricks_tools_core.pdf import generate_pdf_documents as _generate_pdf_documents
from databricks_tools_core.pdf import generate_single_pdf as _generate_single_pdf
from databricks_tools_core.pdf.models import DocumentSpecification

from ..server import mcp


@mcp.tool(timeout=300.0)
def generate_and_upload_pdfs(
    catalog: str,
    schema: str,
    description: str,
    count: int,
    volume: str = "raw_data",
    folder: str = "pdf_documents",
    doc_size: Literal["SMALL", "MEDIUM", "LARGE"] = "MEDIUM",
    overwrite_folder: bool = False,
) -> Dict[str, Any]:
    """
    Generate synthetic PDF documents and upload to a Unity Catalog volume.

    This tool generates realistic PDF documents using a 2-step process:
    1. Uses LLM to generate diverse document specifications
    2. Generates HTML content and converts to PDF in parallel

    Each PDF also gets a companion JSON file with a question/guideline pair
    for RAG evaluation purposes.

    Args:
        catalog: Unity Catalog name
        schema: Schema name
        description: Detailed description of what PDFs should contain.
            Be specific about the domain, document types, and content.
            Example: "Technical documentation for a cloud infrastructure platform
            including API guides, troubleshooting manuals, and security policies."
        count: Number of PDFs to generate (recommended: 5-20)
        volume: Volume name (must already exist). Default: "raw_data"
        folder: Folder within volume (e.g., "technical_docs"). Default: "pdf_documents"
        doc_size: Size of documents to generate. Default: "MEDIUM"
            - "SMALL": ~1 page, concise content
            - "MEDIUM": ~4-6 pages, comprehensive coverage (default)
            - "LARGE": ~10+ pages, exhaustive documentation
        overwrite_folder: If True, delete existing folder content first (default: False)

    Returns:
        Dictionary with:
        - success: True if all PDFs generated successfully
        - volume_path: Path to the volume folder containing PDFs
        - pdfs_generated: Number of PDFs successfully created
        - pdfs_failed: Number of PDFs that failed
        - errors: List of error messages if any

    Example:
        >>> generate_and_upload_pdfs(
        ...     catalog="my_catalog",
        ...     schema="my_schema",
        ...     description="HR policy documents including employee handbook, "
        ...                 "leave policies, code of conduct, and benefits guide",
        ...     count=10,
        ...     doc_size="SMALL"
        ... )
        {
            "success": True,
            "volume_path": "/Volumes/my_catalog/my_schema/raw_data/pdf_documents",
            "pdfs_generated": 10,
            "pdfs_failed": 0,
            "errors": []
        }

    Environment Variables:
        - DATABRICKS_MODEL: Model serving endpoint name (auto-discovered if not set)
        - DATABRICKS_MODEL_NANO: Smaller model for faster generation (auto-discovered if not set)
    """
    # Convert string to DocSize enum
    size_enum = DocSize(doc_size)

    result = _generate_pdf_documents(
        catalog=catalog,
        schema=schema,
        description=description,
        count=count,
        volume=volume,
        folder=folder,
        doc_size=size_enum,
        overwrite_folder=overwrite_folder,
        max_workers=4,
    )

    return {
        "success": result.success,
        "volume_path": result.volume_path,
        "pdfs_generated": result.pdfs_generated,
        "pdfs_failed": result.pdfs_failed,
        "errors": result.errors,
    }


@mcp.tool(timeout=60.0)
def generate_and_upload_pdf(
    title: str,
    description: str,
    question: str,
    guideline: str,
    catalog: str,
    schema: str,
    volume: str = "raw_data",
    folder: str = "pdf_documents",
    doc_size: Literal["SMALL", "MEDIUM", "LARGE"] = "MEDIUM",
) -> Dict[str, Any]:
    """
    Generate a single PDF document and upload to a Unity Catalog volume.

    Use this when you need to create one PDF with precise control over its
    content, title, and associated question/guideline for RAG evaluation.

    Args:
        title: Document title (e.g., "API Authentication Guide")
        description: What this document should contain. Be detailed about
            the content, sections, topics, and domain context to cover.
        question: A question that can be answered by reading this document.
            Used for RAG evaluation.
        guideline: How to evaluate if an answer to the question is correct.
            Should describe what a good answer includes without giving the exact answer.
        catalog: Unity Catalog name
        schema: Schema name
        volume: Volume name (must already exist). Default: "raw_data"
        folder: Folder within volume. Default: "pdf_documents"
        doc_size: Size of document to generate. Default: "MEDIUM"
            - "SMALL": ~1 page, concise content
            - "MEDIUM": ~4-6 pages, comprehensive coverage
            - "LARGE": ~10+ pages, exhaustive documentation

    Returns:
        Dictionary with:
        - success: True if PDF generated successfully
        - pdf_path: Volume path to the generated PDF
        - question_path: Volume path to the companion JSON file (question/guideline)
        - error: Error message if generation failed

    Example:
        >>> generate_and_upload_pdf(
        ...     title="REST API Authentication Guide",
        ...     description="Complete guide to API authentication for a cloud platform "
        ...                 "including OAuth2 flows, API keys, and JWT tokens.",
        ...     question="What are the supported authentication methods?",
        ...     guideline="Answer should mention OAuth2, API keys, and JWT tokens",
        ...     catalog="my_catalog",
        ...     schema="my_schema",
        ...     doc_size="SMALL"
        ... )
        {
            "success": True,
            "pdf_path": "/Volumes/my_catalog/my_schema/raw_data/pdf_documents/rest_api_authentication_guide.pdf",
            "question_path": "/Volumes/my_catalog/my_schema/raw_data/pdf_documents/rest_api_authentication_guide.json",
            "error": None
        }
    """
    # Generate model_id from title (used for filename)
    import re

    model_id = re.sub(r"[^a-zA-Z0-9]+", "_", title).strip("_").upper()

    # Create document specification
    doc_spec = DocumentSpecification(
        title=title,
        category="Document",  # Simplified - category info can be in description
        model=model_id,
        description=description,
        question=question,
        guideline=guideline,
    )

    # Convert string to DocSize enum
    size_enum = DocSize(doc_size)

    # Use a temporary directory for local file creation
    with tempfile.TemporaryDirectory() as temp_dir:
        result = _generate_single_pdf(
            doc_spec=doc_spec,
            description=description,  # Same description used for context
            catalog=catalog,
            schema=schema,
            volume=volume,
            folder=folder,
            temp_dir=temp_dir,
            doc_size=size_enum,
        )

    return {
        "success": result.success,
        "pdf_path": result.pdf_path,
        "question_path": result.question_path,
        "error": result.error,
    }
