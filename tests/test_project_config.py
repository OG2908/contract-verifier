"""Tests for project configuration loader."""
import pytest
from contract_verifier.project_config import load_config, list_projects


def test_load_kriopigi():
    config = load_config("קריופיגי")
    assert config.project_name == "קריופיגי"
    assert config.total_costs_percentage == 8.5
    assert config.costs_calculated_on == "price_without_costs"
    assert config.registration_fee == 2000
    assert config.surcharge_percentage == 2.0
    assert config.surcharge_clearshift == 0.5
    assert config.surcharge_security_buffer == 1.5
    assert len(config.expected_cost_lines) == 6
    assert len(config.expected_payment_lines) == 4
    assert config.rounding_tolerance_eur == 1.0


def test_load_by_variant():
    config = load_config("Kriopigi")
    assert config.project_name == "קריופיגי"


def test_load_case_insensitive():
    config = load_config("kriopigi")
    assert config.project_name == "קריופיגי"


def test_unknown_project():
    with pytest.raises(ValueError, match="not found"):
        load_config("nonexistent_project")


def test_list_projects():
    projects = list_projects()
    assert "קריופיגי" in projects


def test_cost_lines_sum():
    config = load_config("קריופיגי")
    total = sum(cl.percentage for cl in config.expected_cost_lines)
    assert abs(total - config.total_costs_percentage) < 0.01


def test_payment_lines_sum():
    config = load_config("קריופיגי")
    total = sum(pl.percentage for pl in config.expected_payment_lines)
    assert abs(total - 100.0) < 0.01
