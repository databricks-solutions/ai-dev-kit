"""
PDF - Synthetic PDF Document Generation

Generate realistic PDF documents using LLM for RAG/unstructured data use cases.
"""

from .generator import generate_pdf_documents, generate_single_pdf
from .llm import LLMConfigurationError
from .models import (
    DocSize,
    DocumentSpecification,
    DocumentSpecifications,
    PDFBatchResult,
    PDFGenerationResult,
)

__all__ = [
    # Main functions
    "generate_pdf_documents",
    "generate_single_pdf",
    # Exceptions
    "LLMConfigurationError",
    # Enums
    "DocSize",
    # Models
    "DocumentSpecification",
    "DocumentSpecifications",
    "PDFGenerationResult",
    "PDFBatchResult",
]
