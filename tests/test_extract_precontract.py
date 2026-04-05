"""Tests for pre-contract PDF extraction against sample Peraia contract."""
import os
import shutil
import pytest

from contract_verifier.extract_precontract import (
    extract_safe,
    _extract_client_name,
    _extract_apartment_number,
    _extract_late_delivery_payment,
)
from contract_verifier.models import parse_hebrew_amount

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "sample-peraia-contract.pdf")

# Check if OCR tools (poppler + tesseract) are available
_ocr_available = shutil.which("pdfinfo") is not None and shutil.which("tesseract") is not None

# Skip if tesseract not installed (CI environments)
pytestmark = pytest.mark.skipif(
    not os.path.exists(FIXTURE_PATH),
    reason="Sample Peraia contract PDF not in fixtures",
)


@pytest.fixture(scope="module")
def extraction():
    """Run extraction once for all tests."""
    return extract_safe(FIXTURE_PATH)


@pytest.mark.skipif(not _ocr_available, reason="OCR tools (poppler/tesseract) not installed")
class TestPeraiaExtraction:
    def test_client_name(self, extraction):
        assert extraction.data.client_name != ""

    def test_apartment_number(self, extraction):
        # OCR may drop the "C" → "2" instead of "C2"
        assert extraction.data.apartment_number in ("C2", "2")

    def test_purchase_price(self, extraction):
        assert extraction.data.purchase_price == pytest.approx(242_266, abs=1)

    def test_total_with_costs(self, extraction):
        assert extraction.data.total_with_costs == pytest.approx(260_000, abs=1)

    def test_delivery_date(self, extraction):
        assert "31" in extraction.data.delivery_date
        assert "2026" in extraction.data.delivery_date

    def test_payment_lines_count(self, extraction):
        assert len(extraction.data.payment_lines) == 5

    def test_payment_lines_total(self, extraction):
        """Contract payment lines should sum to total_with_costs (260K)."""
        total = sum(pl.amount for pl in extraction.data.payment_lines)
        assert total == pytest.approx(260_000, abs=1)

    def test_payment_percentages(self, extraction):
        """Payment percentages should sum to 100."""
        pct_total = sum(pl.percentage for pl in extraction.data.payment_lines)
        assert pct_total == pytest.approx(100, abs=1)

    def test_has_mortgage(self, extraction):
        # Sample contract references mortgage appendix (נספח משכנתא)
        assert extraction.data.has_mortgage is True

    def test_no_critical_warnings(self, extraction):
        """purchase_price and total_with_costs must extract successfully."""
        critical = {"purchase_price", "total_with_costs", "payment_lines"}
        failed = extraction.failed_fields
        assert not (critical & failed), f"Critical fields failed: {critical & failed}"


# ============================================================
# Regex unit tests (no PDF needed)
# ============================================================


class TestLateDeliveryRegex:
    def test_euro_as_airo(self):
        text = 'פיצוי בגין איחור במסירה של 500 אירו לחודש'
        assert _extract_late_delivery_payment(text) == 500.0

    def test_euro_as_yuro(self):
        """OCR sometimes renders אירו as יורו."""
        text = 'פיצוי בגין איחור במסירה של 300 יורו לחודש'
        assert _extract_late_delivery_payment(text) == 300.0

    def test_euro_as_symbol(self):
        text = 'פיצוי בגין איחור במסירה של 500€ לחודש'
        assert _extract_late_delivery_payment(text) == 500.0

    def test_euro_as_ocr_6(self):
        text = 'פיצוי בגין איחור במסירה של 500 6 לחודש'
        assert _extract_late_delivery_payment(text) == 500.0


class TestApartmentNumberRegex:
    def test_letter_prefix(self):
        assert _extract_apartment_number('C2מספר דירה') == 'C2'

    def test_bare_digit(self):
        """OCR drops the letter prefix."""
        assert _extract_apartment_number('3מספר דירה') == '3'

    def test_with_space(self):
        assert _extract_apartment_number('מספר דירה: A10') == 'A10'

    def test_digit_only_after_label(self):
        assert _extract_apartment_number('מספר דירה: 5') == '5'


class TestClientNameRegex:
    def test_name_with_id(self):
        text = 'עופר שדה ת.ז. 123456789 מצד שני'
        assert _extract_client_name(text) == 'עופר שדה'

    def test_name_without_id_digits(self):
        """OCR may miss ID digits but capture ת.ז."""
        text = 'עופר שדה ת.ז מצד שני'
        assert _extract_client_name(text) == 'עופר שדה'

    def test_name_near_mitsad_sheni(self):
        text = 'נילי שטרן ביבר ת.ז 987654321 מצד שני'
        assert _extract_client_name(text) == 'נילי שטרן ביבר'


class TestParseHebrewAmountYuro:
    def test_yuro_currency(self):
        assert parse_hebrew_amount('300 יורו') == 300.0

    def test_airo_currency(self):
        assert parse_hebrew_amount('500 אירו') == 500.0


# ============================================================
# Kriopigi signed contract regression tests (pdfplumber path)
# ============================================================

from contract_verifier.project_config import load_config

KRIOPIGI_CONFIG = load_config("קריופיגי")

KRIOPIGI_OFER = os.path.join(os.path.dirname(__file__), "fixtures", "kriopigi-ofer-sade.pdf")
KRIOPIGI_MARSELO = os.path.join(os.path.dirname(__file__), "fixtures", "kriopigi-marselo-gilman.pdf")
KRIOPIGI_DORIT = os.path.join(os.path.dirname(__file__), "fixtures", "kriopigi-dorit-gat.pdf")


@pytest.fixture(scope="module")
def ofer_extraction():
    return extract_safe(KRIOPIGI_OFER, config=KRIOPIGI_CONFIG)


@pytest.fixture(scope="module")
def marselo_extraction():
    return extract_safe(KRIOPIGI_MARSELO, config=KRIOPIGI_CONFIG)


@pytest.fixture(scope="module")
def dorit_extraction():
    return extract_safe(KRIOPIGI_DORIT, config=KRIOPIGI_CONFIG)


@pytest.mark.skipif(not os.path.exists(KRIOPIGI_OFER), reason="Kriopigi Ofer fixture missing")
class TestKriopigi_OferSade:
    """Regression: Ofer Sade — Kriopigi apt 3."""

    def test_client_name(self, ofer_extraction):
        assert "עופר" in ofer_extraction.data.client_name
        assert "שדה" in ofer_extraction.data.client_name

    def test_apartment_number(self, ofer_extraction):
        assert ofer_extraction.data.apartment_number == "3"

    def test_total_with_costs(self, ofer_extraction):
        assert ofer_extraction.data.total_with_costs == pytest.approx(99_674, abs=5)

    def test_purchase_price(self, ofer_extraction):
        # Back-calculated: 99674 / 1.085 ≈ 91865
        assert ofer_extraction.data.purchase_price == pytest.approx(91_865, abs=5)

    def test_gross_sqm(self, ofer_extraction):
        assert ofer_extraction.data.gross_sqm == pytest.approx(29.01, abs=0.1)

    def test_balcony_sqm(self, ofer_extraction):
        assert ofer_extraction.data.balcony_sqm == pytest.approx(6.56, abs=0.1)

    @pytest.mark.skipif(not _ocr_available, reason="Delivery date requires OCR")
    def test_delivery_date(self, ofer_extraction):
        assert "30" in ofer_extraction.data.delivery_date
        assert "2026" in ofer_extraction.data.delivery_date

    @pytest.mark.skipif(not _ocr_available, reason="Late delivery requires OCR")
    def test_late_delivery(self, ofer_extraction):
        assert ofer_extraction.data.late_delivery_payment == pytest.approx(300, abs=1)

    def test_payment_lines_count(self, ofer_extraction):
        assert len(ofer_extraction.data.payment_lines) == 4

    def test_payment_lines_have_percentages(self, ofer_extraction):
        pct_total = sum(pl.percentage for pl in ofer_extraction.data.payment_lines)
        assert pct_total == pytest.approx(100, abs=1)

    def test_no_critical_warnings(self, ofer_extraction):
        critical = {"purchase_price", "total_with_costs", "payment_lines"}
        failed = ofer_extraction.failed_fields
        assert not (critical & failed), f"Critical fields failed: {critical & failed}"


@pytest.mark.skipif(not os.path.exists(KRIOPIGI_MARSELO), reason="Kriopigi Marselo fixture missing")
class TestKriopigi_MarseloGilman:
    """Regression: Marselo Gilman — Kriopigi apt A16."""

    def test_client_name(self, marselo_extraction):
        assert "גילמן" in marselo_extraction.data.client_name

    def test_apartment_number(self, marselo_extraction):
        assert marselo_extraction.data.apartment_number == "A16"

    def test_total_with_costs(self, marselo_extraction):
        assert marselo_extraction.data.total_with_costs == pytest.approx(108_933, abs=5)

    def test_purchase_price(self, marselo_extraction):
        # Back-calculated: 108933 / 1.085 ≈ 100399
        assert marselo_extraction.data.purchase_price == pytest.approx(100_399, abs=5)

    def test_gross_sqm(self, marselo_extraction):
        assert marselo_extraction.data.gross_sqm == pytest.approx(32.19, abs=0.1)

    def test_balcony_sqm(self, marselo_extraction):
        assert marselo_extraction.data.balcony_sqm == pytest.approx(6.11, abs=0.1)

    @pytest.mark.skipif(not _ocr_available, reason="Delivery date requires OCR")
    def test_delivery_date(self, marselo_extraction):
        assert "30" in marselo_extraction.data.delivery_date
        assert "2026" in marselo_extraction.data.delivery_date

    @pytest.mark.skipif(not _ocr_available, reason="Late delivery requires OCR")
    def test_late_delivery(self, marselo_extraction):
        assert marselo_extraction.data.late_delivery_payment == pytest.approx(300, abs=1)

    def test_payment_lines_count(self, marselo_extraction):
        assert len(marselo_extraction.data.payment_lines) == 4

    def test_payment_lines_have_percentages(self, marselo_extraction):
        pct_total = sum(pl.percentage for pl in marselo_extraction.data.payment_lines)
        assert pct_total == pytest.approx(100, abs=1)

    def test_no_critical_warnings(self, marselo_extraction):
        critical = {"purchase_price", "total_with_costs", "payment_lines"}
        failed = marselo_extraction.failed_fields
        assert not (critical & failed), f"Critical fields failed: {critical & failed}"


@pytest.mark.skipif(not os.path.exists(KRIOPIGI_DORIT), reason="Kriopigi Dorit fixture missing")
class TestKriopigi_DoritGat:
    """Regression: Dorit & Amit Gat — Kriopigi apt A17."""

    def test_client_name(self, dorit_extraction):
        assert "דורית" in dorit_extraction.data.client_name
        assert "גת" in dorit_extraction.data.client_name

    def test_apartment_number(self, dorit_extraction):
        assert dorit_extraction.data.apartment_number == "A17"

    def test_total_with_costs(self, dorit_extraction):
        assert dorit_extraction.data.total_with_costs == pytest.approx(136_706, abs=5)

    def test_purchase_price(self, dorit_extraction):
        # Back-calculated: 136706 / 1.085 ≈ 125996
        assert dorit_extraction.data.purchase_price == pytest.approx(125_996, abs=5)

    def test_gross_sqm(self, dorit_extraction):
        assert dorit_extraction.data.gross_sqm == pytest.approx(41.03, abs=0.1)

    def test_balcony_sqm(self, dorit_extraction):
        assert dorit_extraction.data.balcony_sqm == pytest.approx(7.79, abs=0.1)

    @pytest.mark.skipif(not _ocr_available, reason="Late delivery requires OCR")
    def test_late_delivery(self, dorit_extraction):
        assert dorit_extraction.data.late_delivery_payment == pytest.approx(300, abs=1)

    def test_payment_lines_count(self, dorit_extraction):
        assert len(dorit_extraction.data.payment_lines) == 4

    def test_payment_lines_have_percentages(self, dorit_extraction):
        pct_total = sum(pl.percentage for pl in dorit_extraction.data.payment_lines)
        assert pct_total == pytest.approx(100, abs=1)

    def test_no_critical_warnings(self, dorit_extraction):
        critical = {"purchase_price", "total_with_costs", "payment_lines"}
        failed = dorit_extraction.failed_fields
        assert not (critical & failed), f"Critical fields failed: {critical & failed}"
