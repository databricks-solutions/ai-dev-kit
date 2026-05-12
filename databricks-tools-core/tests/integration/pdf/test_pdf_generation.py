"""Integration tests for PDF generation."""

import pytest

from databricks_tools_core.pdf import generate_and_upload_pdf
from databricks_tools_core.pdf.generator import _convert_html_to_pdf


@pytest.fixture
def sample_html():
    """Sample HTML document for testing."""
    return """<!DOCTYPE html>
<html>
<head>
    <style>
        body { font-family: Arial, sans-serif; margin: 50px; }
        h1 { color: #333; }
        .highlight { background-color: #ffffcc; padding: 10px; }
    </style>
</head>
<body>
    <h1>Test Document</h1>
    <p>This is a simple test paragraph.</p>
    <div class="highlight">
        <p>This is highlighted content.</p>
    </div>
    <ul>
        <li>Item 1</li>
        <li>Item 2</li>
        <li>Item 3</li>
    </ul>
</body>
</html>"""


@pytest.fixture
def test_config():
    """Test configuration using ai_dev_kit catalog."""
    return {
        "catalog": "ai_dev_kit",
        "schema": "test_pdf_generation",
        "volume": "raw_data",
    }


@pytest.mark.integration
class TestHTMLToPDF:
    """Test HTML to PDF conversion (local only, no Databricks connection)."""

    def test_convert_simple_html(self, sample_html, tmp_path):
        """Test converting HTML to PDF locally."""
        output_path = str(tmp_path / "test.pdf")
        success = _convert_html_to_pdf(sample_html, output_path)

        assert success, "HTML to PDF conversion failed"
        assert (tmp_path / "test.pdf").exists()
        assert (tmp_path / "test.pdf").stat().st_size > 0


@pytest.mark.integration
class TestGenerateAndUploadPDF:
    """Test PDF generation and upload to Unity Catalog volume."""

    def test_generate_and_upload_pdf(self, sample_html, test_config):
        """Test generating PDF from HTML and uploading to volume."""
        result = generate_and_upload_pdf(
            html_content=sample_html,
            filename="test_document.pdf",
            catalog=test_config["catalog"],
            schema=test_config["schema"],
            volume=test_config["volume"],
        )

        assert result.success, f"PDF generation failed: {result.error}"
        assert result.volume_path is not None
        assert result.volume_path.endswith(".pdf")
        assert test_config["catalog"] in result.volume_path

    def test_generate_and_upload_pdf_with_folder(self, sample_html, test_config):
        """Test generating PDF and uploading to a subfolder."""
        result = generate_and_upload_pdf(
            html_content=sample_html,
            filename="subfolder_test",  # Without .pdf extension
            catalog=test_config["catalog"],
            schema=test_config["schema"],
            volume=test_config["volume"],
            folder="test_folder",
        )

        assert result.success, f"PDF generation failed: {result.error}"
        assert result.volume_path is not None
        assert result.volume_path.endswith(".pdf")
        assert "test_folder" in result.volume_path

    def test_generate_pdf_invalid_volume(self, sample_html, test_config):
        """Test error handling for invalid volume."""
        result = generate_and_upload_pdf(
            html_content=sample_html,
            filename="test.pdf",
            catalog=test_config["catalog"],
            schema=test_config["schema"],
            volume="nonexistent_volume",
        )

        assert not result.success
        assert result.error is not None
        assert "does not exist" in result.error
