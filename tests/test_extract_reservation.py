"""Tests for reservation PDF extraction."""
import pytest
from contract_verifier.extract_reservation import extract, extract_safe

FIXTURE_APT1 = "tests/fixtures/טופס_הצטרפות_--_קריופיגי_-דירה_1.pdf"
FIXTURE_APT6 = "tests/fixtures/טופס הצטרפות -- קריופיגי -דירה 6.pdf"


def test_extract_all_fields_apt1():
    data = extract(FIXTURE_APT1)
    assert data.apartment_number == "1"
    assert data.floor == "קרקע"
    assert data.area_gross_sqm == 29.59
    assert data.price_without_costs == 91322.0
    assert data.price_with_costs == 99085.0
    assert data.registration_fee == 2000.0
    assert "קריופיגי" in data.project_name


def test_client_details_apt1():
    data = extract(FIXTURE_APT1)
    assert data.client_name == "ורד יסעור"


def test_extract_all_fields_apt6():
    """Apartment 6 PDF: 'דירה6' with no space — tests pypdf raw text handling."""
    data = extract(FIXTURE_APT6)
    assert data.apartment_number == "6"
    assert data.floor == "קרקע"
    assert data.area_gross_sqm == 37.07
    assert data.price_without_costs == 112649.0
    assert data.price_with_costs == 122224.0
    assert data.registration_fee == 2000.0
    assert "קריופיגי" in data.project_name


def test_client_details_apt6():
    data = extract(FIXTURE_APT6)
    assert data.client_name == "נילי שטרן ביבר"


def test_nonexistent_file():
    with pytest.raises(Exception):
        extract("nonexistent.pdf")


# --- extract_safe tests ---

def test_extract_safe_no_warnings_apt1():
    result = extract_safe(FIXTURE_APT1)
    assert not result.has_warnings
    assert result.data.apartment_number == "1"
    assert result.data.price_with_costs == 99085.0


def test_extract_safe_no_warnings_apt6():
    result = extract_safe(FIXTURE_APT6)
    assert not result.has_warnings
    assert result.data.apartment_number == "6"
    assert result.data.client_name == "נילי שטרן ביבר"


def test_extract_safe_returns_partial_on_bad_pdf(tmp_path):
    """A minimal PDF with no reservation content should return defaults + warnings."""
    from pypdf import PdfWriter
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    pdf_path = tmp_path / "blank.pdf"
    with open(pdf_path, "wb") as f:
        writer.write(f)

    result = extract_safe(str(pdf_path))
    assert result.has_warnings
    assert len(result.warnings) > 0
    assert result.data.apartment_number == ""
    assert result.data.price_with_costs == 0.0
    failed = result.failed_fields
    assert "apartment_number" in failed
    assert "price_with_costs" in failed
