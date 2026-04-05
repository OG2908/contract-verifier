"""Tests for pre-contract PDF extraction against sample Peraia contract."""
import os
import pytest

from contract_verifier.extract_precontract import (
    extract_safe,
    _extract_client_name,
    _extract_apartment_number,
    _extract_late_delivery_payment,
)
from contract_verifier.models import parse_hebrew_amount

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "sample-peraia-contract.pdf")

# Skip if tesseract not installed (CI environments)
pytestmark = pytest.mark.skipif(
    not os.path.exists(FIXTURE_PATH),
    reason="Sample Peraia contract PDF not in fixtures",
)


@pytest.fixture(scope="module")
def extraction():
    """Run extraction once for all tests."""
    return extract_safe(FIXTURE_PATH)


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
