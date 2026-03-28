"""Report output for verification results."""
from __future__ import annotations

import json
from .models import VerificationReport, VerificationResult


def print_report(report: VerificationReport, verbose: bool = False) -> None:
    """Print a rich terminal report."""
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel

    console = Console()

    # Header
    console.print()
    console.print(Panel(
        f"[bold]Client:[/bold] {report.client_name}\n"
        f"[bold]Project:[/bold] {report.project_name}\n"
        f"[bold]Apartment:[/bold] {report.apartment_number}\n"
        f"[bold]Timestamp:[/bold] {report.timestamp}",
        title="[bold blue]Contract Verification Report[/bold blue]",
    ))

    # Group results by category
    categories = {
        "cross_document": "Cross-Document Checks (Reservation vs Contract)",
        "config_validation": "Config Validation (Contract vs Project Config)",
        "custom_terms": "Custom Terms Validation (Contract vs Custom Payment Terms)",
        "internal_math": "Internal Math Checks",
    }

    total_pass = 0
    total_fail = 0

    for cat_key, cat_title in categories.items():
        cat_results = [r for r in report.results if r.category == cat_key]
        if not cat_results:
            continue

        table = Table(title=cat_title, show_header=True)
        table.add_column("Status", width=6)
        table.add_column("Check", min_width=30)
        table.add_column("Expected", min_width=15)
        table.add_column("Actual", min_width=15)

        for r in cat_results:
            if r.passed:
                status = "[green]PASS[/green]"
                total_pass += 1
            else:
                status = "[red]FAIL[/red]"
                total_fail += 1
            table.add_row(status, r.check_name, r.expected, r.actual)

        console.print()
        console.print(table)

    # Summary
    console.print()
    total = total_pass + total_fail
    if total_fail == 0:
        console.print(Panel(
            f"[bold green]ALL {total} CHECKS PASSED[/bold green]",
            border_style="green",
        ))
    else:
        console.print(Panel(
            f"[bold red]{total_fail} CHECK(S) FAILED[/bold red] out of {total}",
            border_style="red",
        ))
    console.print()


def report_to_json(report: VerificationReport) -> str:
    """Serialize report to JSON."""
    return json.dumps({
        "client_name": report.client_name,
        "project_name": report.project_name,
        "apartment_number": report.apartment_number,
        "timestamp": report.timestamp,
        "summary": {
            "total": len(report.results),
            "passed": sum(1 for r in report.results if r.passed),
            "failed": sum(1 for r in report.results if not r.passed),
            "all_passed": all(r.passed for r in report.results),
        },
        "results": [
            {
                "check_name": r.check_name,
                "passed": r.passed,
                "expected": r.expected,
                "actual": r.actual,
                "severity": r.severity,
                "category": r.category,
            }
            for r in report.results
        ],
    }, ensure_ascii=False, indent=2)
