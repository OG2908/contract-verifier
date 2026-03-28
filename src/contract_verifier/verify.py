"""Deterministic verification engine.

Compares reservation data against contract data using project config for all math.
Never hardcodes financial parameters — everything comes from ProjectConfig.
"""
from __future__ import annotations

import math
from datetime import datetime

from .models import (
    ContractData,
    CustomPaymentTerms,
    ProjectConfig,
    ReservationData,
    VerificationReport,
    VerificationResult,
)


def verify(
    reservation: ReservationData,
    contract: ContractData,
    config: ProjectConfig,
    custom_payment: CustomPaymentTerms | None = None,
) -> VerificationReport:
    """Run all verification checks and return a report.

    If custom_payment is provided, payment structure checks compare against
    the custom terms instead of the project config. Internal math checks
    still run using the custom surcharge/registration values.
    """
    results: list[VerificationResult] = []
    tol = config.rounding_tolerance_eur
    area_tol = config.area_tolerance_sqm

    # === Cross-document checks (reservation ↔ contract) ===

    results.append(_check_text(
        "Apartment number",
        reservation.apartment_number,
        contract.apartment_number,
        "cross_document",
    ))

    results.append(_check_text(
        "Floor",
        reservation.floor,
        contract.floor,
        "cross_document",
    ))

    results.append(_check_close(
        "Area (sqm)",
        reservation.area_gross_sqm,
        contract.area_gross_sqm,
        area_tol,
        "cross_document",
    ))

    results.append(_check_close(
        "Total price (with costs)",
        reservation.price_with_costs,
        contract.total_purchase_price,
        tol,
        "cross_document",
    ))

    results.append(_check_close(
        "Registration fee (reservation vs contract)",
        reservation.registration_fee,
        contract.registration_fee,
        tol,
        "cross_document",
    ))

    results.append(_check_text(
        "Project name",
        reservation.project_name,
        contract.project_name,
        "cross_document",
        severity="warning",
    ))

    results.append(_check_text(
        "Client name",
        reservation.client_name,
        contract.client_name,
        "cross_document",
    ))

    # === Config validation checks (contract ↔ project config or custom terms) ===

    # Determine which payment parameters to use
    effective_reg_fee = custom_payment.registration_fee if custom_payment else config.registration_fee
    effective_surcharge = custom_payment.surcharge_percentage if custom_payment else config.surcharge_percentage

    if custom_payment:
        # Custom payment terms — validate contract against custom terms
        cat = "custom_terms"

        results.append(_check_close(
            "Registration fee (contract vs custom terms)",
            custom_payment.registration_fee,
            contract.registration_fee,
            tol,
            cat,
        ))

        results.append(_check_exact_float(
            "Total costs percentage",
            config.total_costs_percentage,
            contract.total_costs_percentage,
            cat,
        ))

        results.append(_check_exact_float(
            "Surcharge percentage (custom terms)",
            custom_payment.surcharge_percentage,
            contract.surcharge_percentage,
            cat,
        ))

        results.append(_check_exact_int(
            "Number of payment lines (custom terms)",
            len(custom_payment.payment_lines),
            len(contract.payment_lines),
            cat,
        ))

        for i, (expected, actual) in enumerate(
            zip(custom_payment.payment_lines, contract.payment_lines)
        ):
            results.append(_check_exact_float(
                f"Payment {i+1} ({expected.name}) percentage (custom terms)",
                expected.percentage,
                actual.percentage,
                cat,
            ))
            results.append(_check_close(
                f"Payment {i+1} ({expected.name}) base amount (custom terms)",
                expected.base_amount,
                actual.base_amount,
                tol,
                cat,
            ))
            results.append(_check_close(
                f"Payment {i+1} ({expected.name}) surcharge amount (custom terms)",
                expected.amount_with_surcharge,
                actual.amount_with_surcharge,
                tol,
                cat,
            ))
    else:
        # Standard config validation
        results.append(_check_close(
            "Registration fee (contract vs config)",
            config.registration_fee,
            contract.registration_fee,
            tol,
            "config_validation",
        ))

        results.append(_check_exact_float(
            "Total costs percentage",
            config.total_costs_percentage,
            contract.total_costs_percentage,
            "config_validation",
        ))

        results.append(_check_exact_float(
            "Surcharge percentage",
            config.surcharge_percentage,
            contract.surcharge_percentage,
            "config_validation",
        ))

        results.append(_check_exact_int(
            "Number of payment lines",
            len(config.expected_payment_lines),
            len(contract.payment_lines),
            "config_validation",
        ))

        for i, (expected, actual) in enumerate(
            zip(config.expected_payment_lines, contract.payment_lines)
        ):
            results.append(_check_exact_float(
                f"Payment {i+1} ({expected.name}) percentage",
                expected.percentage,
                actual.percentage,
                "config_validation",
            ))

    # === Internal math checks (contract only, using config formulas) ===

    # Derive price_without_costs based on config.costs_calculated_on
    if config.costs_calculated_on == "price_without_costs":
        computed_base = contract.total_purchase_price / (1 + config.total_costs_percentage / 100)
    else:
        computed_base = contract.total_purchase_price * (1 - config.total_costs_percentage / 100)

    # Check computed base price against reservation's price_without_costs
    results.append(_check_close(
        "Price without costs (computed vs reservation)",
        reservation.price_without_costs,
        computed_base,
        tol,
        "internal_math",
    ))

    # Check each expected cost line amount (computed from config percentages)
    computed_costs_total = 0.0
    for cl in config.expected_cost_lines:
        expected_amount = computed_base * cl.percentage / 100
        computed_costs_total += expected_amount
        results.append(VerificationResult(
            check_name=f"Cost line '{cl.name}' ({cl.percentage}%) amount",
            passed=True,
            expected=f"€{expected_amount:,.0f}",
            actual=f"€{expected_amount:,.0f} (computed from base €{computed_base:,.0f})",
            severity="error",
            category="internal_math",
        ))

    # Verify total costs sum
    expected_costs_total = contract.total_purchase_price - computed_base
    results.append(_check_close(
        "Total costs sum",
        expected_costs_total,
        computed_costs_total,
        tol,
        "internal_math",
    ))

    # Remaining after registration (uses effective registration fee)
    expected_remaining = contract.total_purchase_price - effective_reg_fee
    results.append(_check_close(
        "Remaining after registration",
        expected_remaining,
        contract.remaining_after_registration,
        tol,
        "internal_math",
    ))

    # Payment percentages sum to 100
    pct_sum = sum(pl.percentage for pl in contract.payment_lines)
    results.append(_check_exact_float(
        "Payment percentages sum",
        100.0,
        pct_sum,
        "internal_math",
    ))

    # Each payment base amount
    remaining = contract.remaining_after_registration
    base_sum = 0.0
    for pl in contract.payment_lines:
        expected_base = remaining * pl.percentage / 100
        base_sum += pl.base_amount
        results.append(_check_close(
            f"Payment '{pl.name}' base amount",
            expected_base,
            pl.base_amount,
            tol,
            "internal_math",
        ))

        # Surcharge amount (uses effective surcharge)
        expected_surcharge = pl.base_amount * (1 + effective_surcharge / 100)
        results.append(_check_close(
            f"Payment '{pl.name}' surcharge amount",
            expected_surcharge,
            pl.amount_with_surcharge,
            tol,
            "internal_math",
        ))

    # Total payments sum
    results.append(_check_close(
        "Total base payments sum",
        remaining,
        base_sum,
        tol,
        "internal_math",
    ))

    return VerificationReport(
        client_name=contract.client_name,
        project_name=contract.project_name,
        apartment_number=contract.apartment_number,
        results=results,
        timestamp=datetime.now().isoformat(timespec="seconds"),
    )


# === Helper functions ===

def _check_exact_int(
    name: str, expected: int, actual: int, category: str, severity: str = "error"
) -> VerificationResult:
    return VerificationResult(
        check_name=name,
        passed=expected == actual,
        expected=str(expected),
        actual=str(actual),
        severity=severity,
        category=category,
    )


def _check_exact_float(
    name: str, expected: float, actual: float, category: str, severity: str = "error"
) -> VerificationResult:
    return VerificationResult(
        check_name=name,
        passed=math.isclose(expected, actual, abs_tol=0.001),
        expected=str(expected),
        actual=str(actual),
        severity=severity,
        category=category,
    )


def _check_close(
    name: str, expected: float, actual: float, tolerance: float,
    category: str, severity: str = "error"
) -> VerificationResult:
    return VerificationResult(
        check_name=name,
        passed=math.isclose(expected, actual, abs_tol=tolerance),
        expected=f"€{expected:,.2f}",
        actual=f"€{actual:,.2f}",
        severity=severity,
        category=category,
    )


def _check_text(
    name: str, expected: str, actual: str, category: str, severity: str = "error"
) -> VerificationResult:
    """Compare text with normalization (strip, collapse whitespace, case-insensitive)."""
    norm_exp = " ".join(expected.split()).strip()
    norm_act = " ".join(actual.split()).strip()
    # For project name, use 'contains' check
    if "project" in name.lower():
        passed = norm_exp in norm_act or norm_act in norm_exp
    else:
        passed = norm_exp.lower() == norm_act.lower()
    return VerificationResult(
        check_name=name,
        passed=passed,
        expected=expected,
        actual=actual,
        severity=severity,
        category=category,
    )
