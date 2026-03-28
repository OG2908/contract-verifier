"""Load per-project financial configuration from JSON files."""
from __future__ import annotations

import json
import math
from pathlib import Path

from .models import ProjectConfig, ProjectCostLine, ProjectPaymentLine

# projects/ directory is at repo root, two levels up from this file
PROJECTS_DIR = Path(__file__).resolve().parent.parent.parent / "projects"


def load_config(project_name: str) -> ProjectConfig:
    """
    Load project configuration by name.
    Scans all .json files in projects/ (skips _template.json).
    Matches project_name or any variant (case-insensitive, whitespace-normalized).
    """
    normalized = _normalize(project_name)

    for json_path in PROJECTS_DIR.glob("*.json"):
        if json_path.name.startswith("_"):
            continue

        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        variants = [data.get("project_name", "")] + data.get("project_name_variants", [])
        if any(_normalize(v) == normalized for v in variants if v):
            return _parse_config(data, json_path)

    available = list_projects()
    raise ValueError(
        f"Project '{project_name}' not found. Available projects: {', '.join(available)}"
    )


def list_projects() -> list[str]:
    """List available project names from projects/ directory."""
    projects = []
    for json_path in sorted(PROJECTS_DIR.glob("*.json")):
        if json_path.name.startswith("_"):
            continue
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        name = data.get("project_name", json_path.stem)
        if name:
            projects.append(name)
    return projects


def _normalize(s: str) -> str:
    """Normalize for comparison: lowercase, collapse whitespace."""
    return " ".join(s.lower().split())


def _parse_config(data: dict, source_path: Path) -> ProjectConfig:
    """Parse a JSON dict into a ProjectConfig, validating constraints."""
    cost = data["cost_structure"]
    payment = data["payment_structure"]

    cost_lines = [
        ProjectCostLine(name=cl["name"], percentage=cl["percentage"])
        for cl in cost["cost_lines"]
    ]
    payment_lines = [
        ProjectPaymentLine(
            name=pl["name"],
            percentage=pl["percentage"],
            destination=pl["destination"],
            timing=pl["timing"],
        )
        for pl in payment["payment_lines"]
    ]

    config = ProjectConfig(
        project_name=data["project_name"],
        project_name_variants=data.get("project_name_variants", []),
        total_costs_percentage=cost["total_costs_percentage"],
        costs_calculated_on=cost["costs_calculated_on"],
        expected_cost_lines=cost_lines,
        registration_fee=payment["registration_fee"],
        surcharge_percentage=payment["surcharge_percentage"],
        surcharge_clearshift=payment["surcharge_breakdown"]["clearshift_fee"],
        surcharge_security_buffer=payment["surcharge_breakdown"]["security_buffer"],
        payments_calculated_on=payment["payments_calculated_on"],
        expected_payment_lines=payment_lines,
        rounding_tolerance_eur=data.get("rounding_tolerance_eur", 1.0),
        area_tolerance_sqm=data.get("area_tolerance_sqm", 0.01),
    )

    _validate(config, source_path)
    return config


def _validate(config: ProjectConfig, source_path: Path) -> None:
    """Validate config constraints."""
    # Cost line percentages must sum to total_costs_percentage
    cost_sum = sum(cl.percentage for cl in config.expected_cost_lines)
    if not math.isclose(cost_sum, config.total_costs_percentage, abs_tol=0.01):
        raise ValueError(
            f"{source_path.name}: cost line percentages sum to {cost_sum}, "
            f"expected {config.total_costs_percentage}"
        )

    # Payment line percentages must sum to 100
    payment_sum = sum(pl.percentage for pl in config.expected_payment_lines)
    if not math.isclose(payment_sum, 100.0, abs_tol=0.01):
        raise ValueError(
            f"{source_path.name}: payment line percentages sum to {payment_sum}, expected 100"
        )

    # No negative values
    if config.registration_fee < 0:
        raise ValueError(f"{source_path.name}: negative registration fee")
    if config.rounding_tolerance_eur < 0:
        raise ValueError(f"{source_path.name}: negative rounding tolerance")
