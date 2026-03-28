"""Tests for contract DOCX extraction."""
import pytest
from contract_verifier.extract_contract import extract

FIXTURE = "tests/fixtures/נילי_שטרן_ביבר-_הסכם_מאסטר_חלקידיקי_סופי.docx"


def test_extract_property_details():
    data = extract(FIXTURE)
    assert data.apartment_number == "6"
    assert data.floor == "קרקע"
    assert data.area_gross_sqm == 37.07
    assert data.balcony_sqm == 7.19


def test_extract_financial_details():
    data = extract(FIXTURE)
    assert data.total_purchase_price == 122224.0
    assert data.total_costs_percentage == 8.5
    assert data.registration_fee == 2000.0
    assert data.remaining_after_registration == 120224.0
    assert data.surcharge_percentage == 2.0


def test_extract_client():
    data = extract(FIXTURE)
    assert data.client_name == "נילי שטרן ביבר"


def test_extract_payment_lines():
    data = extract(FIXTURE)
    assert len(data.payment_lines) == 4

    # מקדמה: 10% = €12,022 → €12,263
    pl = data.payment_lines[0]
    assert pl.name == "מקדמה"
    assert pl.percentage == 10.0
    assert pl.base_amount == 12022.0
    assert pl.amount_with_surcharge == 12263.0

    # תשלום ראשון: 50%
    pl = data.payment_lines[1]
    assert pl.name == "תשלום ראשון"
    assert pl.percentage == 50.0
    assert pl.base_amount == 60112.0
    assert pl.amount_with_surcharge == 61314.0


def test_extract_project():
    data = extract(FIXTURE)
    assert "קריופיגי" in data.project_name


def test_extract_delivery_date():
    data = extract(FIXTURE)
    assert data.delivery_date == "30.11.2026"


def test_nonexistent_file():
    with pytest.raises(Exception):
        extract("nonexistent.docx")
