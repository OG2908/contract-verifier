"""Pure computation for pre-contract and mortgage-adjusted payment tables."""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .models import PreContractPaymentLine


@dataclass
class PreContractTable:
    """Result of pre-contract payment table computation."""
    lines: list[PreContractPaymentLine] = field(default_factory=list)
    total: float = 0.0


@dataclass
class MortgageTable:
    """Result of mortgage-adjusted payment table computation."""
    non_mortgage_lines: list[PreContractPaymentLine] = field(default_factory=list)
    mortgage_line: PreContractPaymentLine | None = None
    total: float = 0.0


def _split_payment(line: PreContractPaymentLine, n: int) -> list[PreContractPaymentLine]:
    """Split a payment line into *n* equal parts.

    The last sub-part absorbs any rounding remainder so the sum is exact.
    Names use "(1/N)", "(2/N)" suffixes.
    """
    if n <= 1:
        return [line]
    base = math.floor(line.amount / n)
    remainder = line.amount - base * (n - 1)
    parts: list[PreContractPaymentLine] = []
    for i in range(n):
        amount = remainder if i == n - 1 else base
        parts.append(PreContractPaymentLine(
            name=f"{line.name} ({i + 1}/{n})",
            amount=amount,
        ))
    return parts


def compute_precontract_table(
    contract_payments: list[PreContractPaymentLine],
    purchase_price: float,
    deduct_reservation: bool = False,
    reservation_fee: float = 0.0,
    split_last_payment: int = 0,
) -> PreContractTable:
    """Compute the pre-contract payment table.

    The pre-contract table adjusts contract payments to sum to the purchase price
    (which is less than the contract total because it excludes deal costs).

    Logic:
      - First payment: contract amount minus reservation fee (if deducting)
      - Middle payments (2nd through second-to-last): same as contract
      - Last payment: purchase_price - sum(first + all middle payments)
      - If split_last_payment > 1, the last (balancing) payment is split into
        N equal sub-payments.
    """
    if not contract_payments:
        return PreContractTable(lines=[], total=0.0)

    if len(contract_payments) == 1:
        amount = purchase_price
        if deduct_reservation:
            amount -= reservation_fee
        last_line = PreContractPaymentLine(name=contract_payments[0].name, amount=amount)
        result_lines = _split_payment(last_line, split_last_payment) if split_last_payment > 1 else [last_line]
        return PreContractTable(
            lines=result_lines,
            total=sum(l.amount for l in result_lines),
        )

    lines: list[PreContractPaymentLine] = []

    # First payment
    first_amount = contract_payments[0].amount
    if deduct_reservation:
        first_amount -= reservation_fee
    lines.append(PreContractPaymentLine(
        name=contract_payments[0].name,
        amount=first_amount,
    ))

    # Middle payments (same as contract)
    for cp in contract_payments[1:-1]:
        lines.append(PreContractPaymentLine(name=cp.name, amount=cp.amount))

    # Last payment: balancing line
    running_sum = sum(line.amount for line in lines)
    last_amount = purchase_price - running_sum
    last_line = PreContractPaymentLine(
        name=contract_payments[-1].name,
        amount=last_amount,
    )

    # Optionally split the last payment
    if split_last_payment > 1:
        lines.extend(_split_payment(last_line, split_last_payment))
    else:
        lines.append(last_line)

    total = sum(line.amount for line in lines)
    return PreContractTable(lines=lines, total=total)


def compute_mortgage_table(
    contract_payments: list[PreContractPaymentLine],
    purchase_price: float,
    mortgage_flags: list[bool],
    deduct_reservation: bool = False,
    reservation_fee: float = 0.0,
    split_last_payment: int = 0,
) -> MortgageTable:
    """Compute the mortgage-adjusted payment table.

    Logic:
      1. Split contract payments into non-mortgage and mortgage groups
      2. Mortgage total = sum of mortgage-flagged contract amounts
      3. Non-mortgage: keep all except last in original amounts (with reservation
         deduction on first if applicable)
      4. Last non-mortgage = purchase_price - mortgage_total - sum(other non-mortgage)
      5. If split_last_payment > 1, the last non-mortgage (balancing) line is split
      6. Single mortgage line at bottom
    """
    if not contract_payments:
        return MortgageTable()

    # If no mortgage flags set, fall back to pre-contract table
    if not any(mortgage_flags):
        pc = compute_precontract_table(
            contract_payments, purchase_price, deduct_reservation, reservation_fee,
            split_last_payment=split_last_payment,
        )
        return MortgageTable(
            non_mortgage_lines=pc.lines,
            mortgage_line=None,
            total=pc.total,
        )

    # Calculate mortgage total from CONTRACT amounts
    mortgage_total = sum(
        cp.amount for cp, is_mortgage in zip(contract_payments, mortgage_flags)
        if is_mortgage
    )

    # Collect non-mortgage payments in original order
    non_mortgage_contract = [
        (i, cp) for i, (cp, is_mortgage) in enumerate(zip(contract_payments, mortgage_flags))
        if not is_mortgage
    ]

    if not non_mortgage_contract:
        # All payments are mortgage — single mortgage line
        return MortgageTable(
            non_mortgage_lines=[],
            mortgage_line=PreContractPaymentLine(name="משכנתא", amount=purchase_price),
            total=purchase_price,
        )

    non_mortgage_lines: list[PreContractPaymentLine] = []

    # All non-mortgage except the last: keep original amounts
    for idx, (orig_idx, cp) in enumerate(non_mortgage_contract[:-1]):
        amount = cp.amount
        # Apply reservation deduction to the first contract payment if applicable
        if orig_idx == 0 and deduct_reservation:
            amount -= reservation_fee
        non_mortgage_lines.append(PreContractPaymentLine(name=cp.name, amount=amount))

    # Last non-mortgage: balancing line
    running_sum = sum(line.amount for line in non_mortgage_lines)
    last_orig_idx, last_cp = non_mortgage_contract[-1]
    last_non_mortgage_amount = purchase_price - mortgage_total - running_sum
    last_line = PreContractPaymentLine(
        name=last_cp.name,
        amount=last_non_mortgage_amount,
    )

    # Optionally split the last non-mortgage payment
    if split_last_payment > 1:
        non_mortgage_lines.extend(_split_payment(last_line, split_last_payment))
    else:
        non_mortgage_lines.append(last_line)

    mortgage_line = PreContractPaymentLine(name="משכנתא", amount=mortgage_total)
    total = sum(line.amount for line in non_mortgage_lines) + mortgage_total

    return MortgageTable(
        non_mortgage_lines=non_mortgage_lines,
        mortgage_line=mortgage_line,
        total=total,
    )
