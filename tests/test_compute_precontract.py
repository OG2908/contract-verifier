"""Tests for pre-contract payment table computation."""
import pytest

from contract_verifier.models import PreContractPaymentLine
from contract_verifier.compute_precontract import (
    compute_precontract_table,
    compute_mortgage_table,
)


def _make_lines(amounts: list[tuple[str, float]]) -> list[PreContractPaymentLine]:
    return [PreContractPaymentLine(name=n, amount=a) for n, a in amounts]


# --- Peraia example values ---
PERAIA_PAYMENTS = _make_lines([
    ("תשלום ראשון", 26_000),
    ("תשלום שני", 104_000),
    ("תשלום שלישי", 52_000),
    ("תשלום רביעי", 39_000),
    ("תשלום חמישי", 39_000),
])
PURCHASE_PRICE = 242_266.0
RESERVATION_FEE = 4_000.0


class TestPreContractTable:
    def test_basic_peraia(self):
        result = compute_precontract_table(
            PERAIA_PAYMENTS, PURCHASE_PRICE,
            deduct_reservation=True, reservation_fee=RESERVATION_FEE,
        )
        assert len(result.lines) == 5
        assert result.lines[0].amount == 22_000  # 26K - 4K reservation
        assert result.lines[1].amount == 104_000
        assert result.lines[2].amount == 52_000
        assert result.lines[3].amount == 39_000
        # Last = 242266 - (22000 + 104000 + 52000 + 39000) = 25266
        assert result.lines[4].amount == pytest.approx(25_266, abs=1)
        assert result.total == pytest.approx(PURCHASE_PRICE, abs=1)

    def test_no_reservation_deduction(self):
        result = compute_precontract_table(
            PERAIA_PAYMENTS, PURCHASE_PRICE,
            deduct_reservation=False,
        )
        assert result.lines[0].amount == 26_000  # unchanged
        # Last = 242266 - (26000 + 104000 + 52000 + 39000) = 21266
        assert result.lines[4].amount == pytest.approx(21_266, abs=1)
        assert result.total == pytest.approx(PURCHASE_PRICE, abs=1)

    def test_single_payment(self):
        lines = _make_lines([("תשלום יחיד", 100_000)])
        result = compute_precontract_table(lines, 80_000.0)
        assert len(result.lines) == 1
        assert result.lines[0].amount == 80_000
        assert result.total == 80_000

    def test_single_payment_with_reservation(self):
        lines = _make_lines([("תשלום יחיד", 100_000)])
        result = compute_precontract_table(
            lines, 80_000.0, deduct_reservation=True, reservation_fee=2_000.0,
        )
        assert result.lines[0].amount == 78_000
        assert result.total == 78_000

    def test_two_payments(self):
        lines = _make_lines([("ראשון", 60_000), ("שני", 40_000)])
        result = compute_precontract_table(lines, 90_000.0)
        assert result.lines[0].amount == 60_000
        assert result.lines[1].amount == 30_000  # 90K - 60K
        assert result.total == pytest.approx(90_000, abs=1)

    def test_empty_payments(self):
        result = compute_precontract_table([], 100_000.0)
        assert len(result.lines) == 0
        assert result.total == 0.0

    def test_total_always_equals_purchase_price(self):
        """Invariant: pre-contract total must equal purchase price."""
        result = compute_precontract_table(
            PERAIA_PAYMENTS, PURCHASE_PRICE,
            deduct_reservation=True, reservation_fee=RESERVATION_FEE,
        )
        assert result.total == pytest.approx(PURCHASE_PRICE, abs=0.01)


class TestSplitLastPayment:
    """Tests for split_last_payment in compute_precontract_table."""

    def test_split_two(self):
        """Last payment splits into 2 equal parts."""
        result = compute_precontract_table(
            PERAIA_PAYMENTS, PURCHASE_PRICE,
            deduct_reservation=True, reservation_fee=RESERVATION_FEE,
            split_last_payment=2,
        )
        # Original: 5 lines → now 6 (4 regular + 2 split)
        assert len(result.lines) == 6
        # Last balancing amount = 25266 → split into 12633 + 12633
        assert result.lines[4].amount + result.lines[5].amount == pytest.approx(25_266, abs=1)
        assert "(1/2)" in result.lines[4].name
        assert "(2/2)" in result.lines[5].name
        assert result.total == pytest.approx(PURCHASE_PRICE, abs=1)

    def test_split_zero_is_no_split(self):
        """split_last_payment=0 means no splitting (backward compatible)."""
        result = compute_precontract_table(
            PERAIA_PAYMENTS, PURCHASE_PRICE,
            deduct_reservation=True, reservation_fee=RESERVATION_FEE,
            split_last_payment=0,
        )
        assert len(result.lines) == 5
        assert result.total == pytest.approx(PURCHASE_PRICE, abs=1)

    def test_split_single_payment(self):
        """Splitting a single payment."""
        lines = _make_lines([("תשלום יחיד", 100_000)])
        result = compute_precontract_table(lines, 80_000.0, split_last_payment=2)
        assert len(result.lines) == 2
        assert result.lines[0].amount + result.lines[1].amount == 80_000
        assert result.total == 80_000


class TestMortgageTable:
    def test_peraia_mortgage_last_two(self):
        """Mortgage on payments 4 and 5 (39K + 39K = 78K)."""
        flags = [False, False, False, True, True]
        result = compute_mortgage_table(
            PERAIA_PAYMENTS, PURCHASE_PRICE, flags,
            deduct_reservation=True, reservation_fee=RESERVATION_FEE,
        )
        assert len(result.non_mortgage_lines) == 3
        assert result.non_mortgage_lines[0].amount == 22_000  # 26K - 4K
        assert result.non_mortgage_lines[1].amount == 104_000
        # Last non-mortgage = 242266 - 78000 - (22000 + 104000) = 38266
        assert result.non_mortgage_lines[2].amount == pytest.approx(38_266, abs=1)
        assert result.mortgage_line is not None
        assert result.mortgage_line.amount == 78_000
        assert result.total == pytest.approx(PURCHASE_PRICE, abs=1)

    def test_no_mortgage_flags(self):
        """No mortgage flags → same as pre-contract table."""
        flags = [False, False, False, False, False]
        result = compute_mortgage_table(
            PERAIA_PAYMENTS, PURCHASE_PRICE, flags,
            deduct_reservation=True, reservation_fee=RESERVATION_FEE,
        )
        assert result.mortgage_line is None
        assert len(result.non_mortgage_lines) == 5
        assert result.total == pytest.approx(PURCHASE_PRICE, abs=1)

    def test_all_mortgage(self):
        """All payments are mortgage → single mortgage line."""
        flags = [True, True, True, True, True]
        result = compute_mortgage_table(
            PERAIA_PAYMENTS, PURCHASE_PRICE, flags,
        )
        assert len(result.non_mortgage_lines) == 0
        assert result.mortgage_line is not None
        assert result.mortgage_line.amount == PURCHASE_PRICE
        assert result.total == PURCHASE_PRICE

    def test_mortgage_total_invariant(self):
        """Total must equal purchase price regardless of mortgage split."""
        flags = [False, True, False, True, False]
        result = compute_mortgage_table(
            PERAIA_PAYMENTS, PURCHASE_PRICE, flags,
            deduct_reservation=True, reservation_fee=RESERVATION_FEE,
        )
        assert result.total == pytest.approx(PURCHASE_PRICE, abs=0.01)

    def test_mortgage_with_split(self):
        """Mortgage table + split_last_payment should still total correctly."""
        flags = [False, False, False, True, True]
        result = compute_mortgage_table(
            PERAIA_PAYMENTS, PURCHASE_PRICE, flags,
            deduct_reservation=True, reservation_fee=RESERVATION_FEE,
            split_last_payment=2,
        )
        # Last non-mortgage line is split into 2
        assert len(result.non_mortgage_lines) == 4  # 2 regular + 2 split
        assert result.mortgage_line is not None
        assert result.total == pytest.approx(PURCHASE_PRICE, abs=1)

    def test_no_mortgage_flags_with_split(self):
        """No mortgage flags + split → delegates to precontract table with split."""
        flags = [False, False, False, False, False]
        result = compute_mortgage_table(
            PERAIA_PAYMENTS, PURCHASE_PRICE, flags,
            deduct_reservation=True, reservation_fee=RESERVATION_FEE,
            split_last_payment=2,
        )
        assert result.mortgage_line is None
        assert len(result.non_mortgage_lines) == 6  # 4 regular + 2 split
        assert result.total == pytest.approx(PURCHASE_PRICE, abs=1)
