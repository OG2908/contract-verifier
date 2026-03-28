"""CLI entry point for contract verification."""
from __future__ import annotations

import argparse
import logging
import sys

from .extract_contract import extract as extract_contract
from .extract_reservation import extract as extract_reservation
from .project_config import list_projects, load_config
from .report import print_report, report_to_json
from .verify import verify


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify real estate purchase contracts against reservation agreements"
    )
    parser.add_argument("--project", help="Project name (e.g., 'קריופיגי')")
    parser.add_argument("--client", help="Client name (for Google Drive lookup)")
    parser.add_argument("--contract", help="Path to contract .docx file")
    parser.add_argument("--reservation", help="Path to reservation .pdf file (local mode)")
    parser.add_argument("--local", action="store_true", help="Use local files only (skip Google Drive)")
    parser.add_argument("--verbose", action="store_true", help="Show extracted values and loaded config")
    parser.add_argument("--json", action="store_true", help="Output report as JSON")
    parser.add_argument("--list-projects", action="store_true", help="List available project configs")

    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s: %(message)s",
    )

    if args.list_projects:
        projects = list_projects()
        print("Available projects:")
        for p in projects:
            print(f"  - {p}")
        return

    # Validate required args
    if not args.project:
        parser.error("--project is required")
    if not args.contract:
        parser.error("--contract is required")

    # Step 1: Load project config
    config = load_config(args.project)
    if args.verbose:
        print(f"Loaded config for project: {config.project_name}")
        print(f"  Total costs: {config.total_costs_percentage}%")
        print(f"  Costs calculated on: {config.costs_calculated_on}")
        print(f"  Registration fee: €{config.registration_fee:,.0f}")
        print(f"  Surcharge: {config.surcharge_percentage}%")
        print()

    # Step 2: Get reservation PDF
    if args.local:
        if not args.reservation:
            parser.error("--reservation is required in local mode")
        reservation_path = args.reservation
    else:
        if not args.client:
            parser.error("--client is required when not in local mode")
        from .drive_fetch import fetch_reservation
        reservation_path = fetch_reservation(args.project, args.client)

    # Step 3: Extract reservation data
    reservation_data = extract_reservation(reservation_path)
    if args.verbose:
        print("=== Reservation Data ===")
        print(f"  Client: {reservation_data.client_name}")
        print(f"  Apartment: {reservation_data.apartment_number}")
        print(f"  Floor: {reservation_data.floor}")
        print(f"  Area: {reservation_data.area_gross_sqm} sqm")
        print(f"  Price without costs: €{reservation_data.price_without_costs:,.0f}")
        print(f"  Price with costs: €{reservation_data.price_with_costs:,.0f}")
        print(f"  Registration fee: €{reservation_data.registration_fee:,.0f}")
        print()

    # Step 4: Extract contract data
    contract_data = extract_contract(args.contract)
    if args.verbose:
        print("=== Contract Data ===")
        print(f"  Client: {contract_data.client_name}")
        print(f"  Apartment: {contract_data.apartment_number}")
        print(f"  Floor: {contract_data.floor}")
        print(f"  Area: {contract_data.area_gross_sqm} sqm (balcony: {contract_data.balcony_sqm})")
        print(f"  Total price: €{contract_data.total_purchase_price:,.0f}")
        print(f"  Costs: {contract_data.total_costs_percentage}%")
        print(f"  Registration fee: €{contract_data.registration_fee:,.0f}")
        print(f"  Remaining: €{contract_data.remaining_after_registration:,.0f}")
        print(f"  Surcharge: {contract_data.surcharge_percentage}%")
        print(f"  Payments: {len(contract_data.payment_lines)} lines")
        for pl in contract_data.payment_lines:
            print(f"    {pl.name}: {pl.percentage}% = €{pl.base_amount:,.0f} → €{pl.amount_with_surcharge:,.0f}")
        print()

    # Step 5: Run verification
    report = verify(reservation_data, contract_data, config)

    # Step 6: Output report
    if args.json:
        print(report_to_json(report))
    else:
        print_report(report, verbose=args.verbose)

    # Step 7: Exit code
    has_failures = any(not r.passed for r in report.results)
    sys.exit(1 if has_failures else 0)


if __name__ == "__main__":
    main()
