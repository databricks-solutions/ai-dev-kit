"""Pydantic models for PDF generation."""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class DocSize(str, Enum):
    """Document size options for PDF generation."""

    SMALL = "SMALL"  # ~1 page
    MEDIUM = "MEDIUM"  # ~5 pages (default)
    LARGE = "LARGE"  # ~10+ pages


class DocumentSpecification(BaseModel):
    """Specification for a single document to generate."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(description="A descriptive, professional title for the document")
    category: str = Field(description="Document category (e.g., Technical, Procedures, Guides, Templates, Reference)")
    model: str = Field(description="A unique identifier/code for the document")
    description: str = Field(
        description="Detailed summary of document contents, referencing specific tasks and context"
    )
    question: str = Field(description="A specific question that can be answered by reading this document")
    guideline: str = Field(
        description="Guideline for how to evaluate the answer - sets expectations for tone, structure, and behavior"
    )


class DocumentSpecifications(BaseModel):
    """Collection of document specifications."""

    model_config = ConfigDict(extra="forbid")

    documents: list[DocumentSpecification]


class PDFGenerationResult(BaseModel):
    """Result from generating a single PDF."""

    pdf_path: str
    question_path: Optional[str] = None
    success: bool
    error: Optional[str] = None


class PDFBatchResult(BaseModel):
    """Result from generating a batch of PDFs."""

    success: bool
    volume_path: str
    pdfs_generated: int
    pdfs_failed: int
    errors: list[str] = Field(default_factory=list)
