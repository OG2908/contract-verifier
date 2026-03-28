"""Tests for the verification engine."""
import pytest
from contract_verifier.models import (
    ReservationData, ContractData, PaymentLine, CostLine,
    ProjectConfig, ProjectCostLine, ProjectPaymentLine,
)
from contract_verifier.verify import verify


def _make_config() -> ProjectConfig:
    return ProjectConfig(
        project_name="test",
        project_name_variants=["test"],
        total_costs_percentage=8.5,
        costs_calculated_on="price_without_costs",
        expected_cost_lines=[
            ProjectCostLine("מס רכישה", 3.09),
            ProjectCostLine("עו\"ד", 5.41),
        ],
        registration_fee=2000,
        surcharge_percentage=2.0,
        surcharge_clearshift=0.5,
        surcharge_security_buffer=1.5,
        payments_calculated_on="total_minus_registration",
        expected_payment_lines=[
            ProjectPaymentLine("מקדמה", 50, "company_bank", "immediate"),
            ProjectPaymentLine("תשלום", 50, "escrow", "later"),
        ],
        rounding_tolerance_eur=1.0,
        area_tolerance_sqm=0.01,
    )


def _make_matching_pair():
    """Create a reservation and contract that should pass all checks."""
    # total = base * (1 + 8.5/100) = base * 1.085
    # base = 10000 => total = 10850
    total = 10850.0
    base = 10000.0
    reg_fee = 2000.0
    remaining = total - reg_fee  # 8850

    reservation = ReservationData(
        client_name="ישראל ישראלי",
        apartment_number="1",
        floor="קרקע",
        area_gross_sqm=50.0,
        price_without_costs=base,
        price_with_costs=total,
        registration_fee=reg_fee,
        project_name="test",
    )

    contract = ContractData(
        client_name="ישראל ישראלי",
        apartment_number="1",
        floor="קרקע",
        area_gross_sqm=50.0,
        balcony_sqm=10.0,
        total_purchase_price=total,
        total_costs_percentage=8.5,
        cost_lines=[],
        registration_fee=reg_fee,
        remaining_after_registration=remaining,
        surcharge_percentage=2.0,
        payment_lines=[
            PaymentLine("מקדמה", 50, round(remaining * 0.5), round(remaining * 0.5 * 1.02)),
            PaymentLine("תשלום", 50, round(remaining * 0.5), round(remaining * 0.5 * 1.02)),
        ],
        project_name="test",
        delivery_date="01.01.2027",
    )

    return reservation, contract


def test_all_pass():
    config = _make_config()
    reservation, contract = _make_matching_pair()
    report = verify(reservation, contract, config)
    failures = [r for r in report.results if not r.passed]
    assert len(failures) == 0, f"Unexpected failures: {[(f.check_name, f.expected, f.actual) for f in failures]}"


def test_apartment_mismatch():
    config = _make_config()
    reservation, contract = _make_matching_pair()
    contract.apartment_number = "2"  # mismatch
    report = verify(reservation, contract, config)
    apt_check = [r for r in report.results if r.check_name == "Apartment number"][0]
    assert not apt_check.passed


def test_price_mismatch():
    config = _make_config()
    reservation, contract = _make_matching_pair()
    contract.total_purchase_price = 99999.0  # mismatch
    report = verify(reservation, contract, config)
    price_check = [r for r in report.results if r.check_name == "Total price (with costs)"][0]
    assert not price_check.passed


def test_client_name_mismatch():
    config = _make_config()
    reservation, contract = _make_matching_pair()
    contract.client_name = "אחר"
    report = verify(reservation, contract, config)
    name_check = [r for r in report.results if r.check_name == "Client name"][0]
    assert not name_check.passed


def test_surcharge_mismatch():
    config = _make_config()
    reservation, contract = _make_matching_pair()
    contract.surcharge_percentage = 3.0  # mismatch
    report = verify(reservation, contract, config)
    sc_check = [r for r in report.results if r.check_name == "Surcharge percentage"][0]
    assert not sc_check.passed
