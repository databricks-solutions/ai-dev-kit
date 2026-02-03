"""Integration tests for PDF generation."""

import asyncio
import os
import shutil
from pathlib import Path

import pytest

# Local output directory for generated PDFs
GENERATED_PDF_DIR = Path(__file__).parent / "generated_pdf"


def requires_llm():
    """Skip decorator for tests that require LLM."""
    return pytest.mark.skipif(
        not os.getenv("DATABRICKS_MODEL") and not os.getenv("AZURE_OPENAI_DEPLOYMENT"),
        reason="No LLM endpoint configured (set DATABRICKS_MODEL or AZURE_OPENAI_DEPLOYMENT)",
    )


@pytest.fixture(scope="module", autouse=True)
def setup_generated_pdf_dir():
    """Setup generated_pdf directory - clean at start, keep at end."""
    # Clean up at the beginning
    if GENERATED_PDF_DIR.exists():
        shutil.rmtree(GENERATED_PDF_DIR)
    GENERATED_PDF_DIR.mkdir(parents=True, exist_ok=True)
    yield
    # Don't clean up at end - keep files for inspection


@pytest.mark.integration
class TestHTMLToPDF:
    """Test HTML to PDF conversion (no LLM required)."""

    def test_convert_simple_html(self):
        """Test converting simple HTML to PDF."""
        from databricks_tools_core.pdf.generator import _convert_html_to_pdf

        html_content = """
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body { font-family: Arial, sans-serif; margin: 50px; }
                h1 { color: #333; }
            </style>
        </head>
        <body>
            <h1>Test Document</h1>
            <p>This is a simple test paragraph.</p>
        </body>
        </html>
        """

        output_path = str(GENERATED_PDF_DIR / "simple_test.pdf")
        success = asyncio.run(_convert_html_to_pdf(html_content, output_path))

        assert success, "HTML to PDF conversion failed"
        assert Path(output_path).exists()
        assert Path(output_path).stat().st_size > 0


@requires_llm()
@pytest.mark.integration
class TestPDFGeneration:
    """Integration tests for PDF document generation (requires LLM)."""

    @pytest.fixture
    def test_config(self):
        """Test configuration using ai_dev_kit catalog."""
        return {
            "catalog": "ai_dev_kit",
            "schema": "test_pdf_generation",
            "volume": "raw_data",
            "folder": "test_docs",
        }

    def test_generate_single_pdf(self, test_config):
        """Test generating a single PDF document."""
        from databricks_tools_core.pdf import DocSize, generate_single_pdf
        from databricks_tools_core.pdf.models import DocumentSpecification

        doc_spec = DocumentSpecification(
            title="Test API Guide",
            category="Technical",
            model="TEST-001",
            description="A simple test document about REST API best practices.",
            question="What are the recommended HTTP methods for CRUD operations?",
            guideline="Answer should mention GET, POST, PUT/PATCH, DELETE methods.",
        )

        # Use local directory for temp files
        temp_dir = str(GENERATED_PDF_DIR / "single_pdf")
        Path(temp_dir).mkdir(parents=True, exist_ok=True)

        result = asyncio.run(
            generate_single_pdf(
                doc_spec=doc_spec,
                description="Technical documentation for a REST API service.",
                catalog=test_config["catalog"],
                schema=test_config["schema"],
                volume=test_config["volume"],
                folder=test_config["folder"],
                temp_dir=temp_dir,
                doc_size=DocSize.SMALL,  # Use SMALL for faster tests
            )
        )

        assert result.success, f"PDF generation failed: {result.error}"
        assert result.pdf_path.endswith(".pdf")
        assert test_config["catalog"] in result.pdf_path

    def test_generate_pdf_documents_batch(self, test_config):
        """Test generating multiple PDF documents."""
        from databricks_tools_core.pdf import DocSize, generate_pdf_documents

        # Use local directory for batch output
        batch_dir = str(GENERATED_PDF_DIR / "batch_pdf")
        Path(batch_dir).mkdir(parents=True, exist_ok=True)

        result = asyncio.run(
            generate_pdf_documents(
                catalog=test_config["catalog"],
                schema=test_config["schema"],
                description="HR policy documents including employee guidelines and procedures.",
                count=2,  # Small count for faster test
                volume=test_config["volume"],
                folder="batch_test",
                doc_size=DocSize.SMALL,  # Use SMALL for faster tests
                overwrite_folder=True,
                max_workers=4,
                temp_dir=batch_dir,
            )
        )

        assert result.success or result.pdfs_generated > 0, (
            f"No PDFs generated: {result.errors}"
        )
        assert result.pdfs_generated >= 1
        assert (
            result.volume_path
            == f"/Volumes/{test_config['catalog']}/{test_config['schema']}/{test_config['volume']}/batch_test"
        )
