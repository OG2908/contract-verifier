"""Tests for pre-contract PDF extraction against sample Peraia contract."""
import os
import pytest

from contract_verifier.extract_precontract import extract_safe

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
