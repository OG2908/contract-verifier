"""Tests for data models and parse_hebrew_amount."""
import pytest
from contract_verifier.models import parse_hebrew_amount


def test_parse_simple():
    assert parse_hebrew_amount("122224") == 122224.0


def test_parse_with_commas():
    assert parse_hebrew_amount("122,224") == 122224.0


def test_parse_with_euro():
    assert parse_hebrew_amount("€122,224") == 122224.0


def test_parse_with_hebrew_currency():
    assert parse_hebrew_amount("122,224 אירו") == 122224.0


def test_parse_european_thousands():
    assert parse_hebrew_amount("122.224") == 122224.0


def test_parse_decimal():
    assert parse_hebrew_amount("29.59") == 29.59


def test_parse_with_spaces():
    assert parse_hebrew_amount(" 2,000 ") == 2000.0


def test_parse_empty_raises():
    with pytest.raises(ValueError):
        parse_hebrew_amount("")


def test_parse_garbage_raises():
    with pytest.raises(ValueError):
        parse_hebrew_amount("abc")
