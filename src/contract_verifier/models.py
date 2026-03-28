"""Data models for contract verification."""
from __future__ import annotations

import re
from dataclasses import dataclass, field


def parse_hebrew_amount(raw: str) -> float:
    """
    Parse a number from Hebrew text.
    Handles: "122,224", "€122,224", "122224", "122.224" (European thousands),
    "29.59" (decimal), "122,224 אירו"
    """
    # Remove currency symbols, Hebrew "אירו", spaces, non-breaking spaces, RTL marks
    cleaned = re.sub(r'[€\s\u00a0\u200f\u200e\u200b]', '', raw)
    cleaned = re.sub(r'אירו', '', cleaned)
    cleaned = cleaned.strip()

    if not cleaned:
        raise ValueError(f"Cannot parse amount from: {raw!r}")

    # Remove thousands separators (commas)
    cleaned = cleaned.replace(',', '')

    # Handle European notation: period as thousands separator (e.g., "122.224")
    # Only if there are exactly 3 digits after the period and no other period
    if re.match(r'^\d+\.\d{3}$', cleaned):
        cleaned = cleaned.replace('.', '')

    try:
        return float(cleaned)
    except ValueError:
        raise ValueError(f"Cannot parse amount from: {raw!r} (cleaned: {cleaned!r})")


@dataclass
class ExtractionWarning:
    """A field that failed to extract from a document."""
    field_name: str
    reason: str


@dataclass
class ReservationData:
    """Source of truth - extracted from reservation agreement PDF."""
    client_name: str
    apartment_number: str
    floor: str
    area_gross_sqm: float
    price_without_costs: float
    price_with_costs: float
    registration_fee: float
    project_name: str


@dataclass
class ReservationExtractionResult:
    """Result of reservation extraction — may be partial with warnings."""
    data: ReservationData
    warnings: list[ExtractionWarning] = field(default_factory=list)

    @property
    def has_warnings(self) -> bool:
        return len(self.warnings) > 0

    @property
    def failed_fields(self) -> set[str]:
        return {w.field_name for w in self.warnings}


@dataclass
class CostLine:
    """Single line in the deal costs breakdown."""
    name: str
    percentage: float
    amount: float


@dataclass
class PaymentLine:
    """Single line in the payment schedule."""
    name: str
    percentage: float
    base_amount: float
    amount_with_surcharge: float
    notes: str = ""


@dataclass
class ContractData:
    """Extracted from the purchase contract DOCX."""
    client_name: str
    apartment_number: str
    floor: str
    area_gross_sqm: float
    balcony_sqm: float
    total_purchase_price: float
    total_costs_percentage: float
    cost_lines: list[CostLine]
    registration_fee: float
    remaining_after_registration: float
    surcharge_percentage: float
    payment_lines: list[PaymentLine]
    project_name: str
    delivery_date: str = ""


@dataclass
class VerificationResult:
    """Single check result."""
    check_name: str
    passed: bool
    expected: str
    actual: str
    severity: str  # "error" or "warning"
    category: str = ""  # "cross_document", "config_validation", "internal_math"


@dataclass
class VerificationReport:
    """Full verification report."""
    client_name: str
    project_name: str
    apartment_number: str
    results: list[VerificationResult] = field(default_factory=list)
    timestamp: str = ""


@dataclass
class CustomPaymentTerms:
    """Custom payment terms for a specific client, overriding project config."""
    registration_fee: float
    surcharge_percentage: float
    payment_lines: list[PaymentLine]


@dataclass
class ProjectCostLine:
    """Expected cost line from project config."""
    name: str
    percentage: float


@dataclass
class ProjectPaymentLine:
    """Expected payment line from project config."""
    name: str
    percentage: float
    destination: str
    timing: str


@dataclass
class ProjectConfig:
    """Per-project financial rules - loaded from projects/<name>.json."""
    project_name: str
    project_name_variants: list[str]
    total_costs_percentage: float
    costs_calculated_on: str  # "price_without_costs" or "total_price"
    expected_cost_lines: list[ProjectCostLine]
    registration_fee: float
    surcharge_percentage: float
    surcharge_clearshift: float
    surcharge_security_buffer: float
    payments_calculated_on: str  # "total_minus_registration"
    expected_payment_lines: list[ProjectPaymentLine]
    rounding_tolerance_eur: float
    area_tolerance_sqm: float
