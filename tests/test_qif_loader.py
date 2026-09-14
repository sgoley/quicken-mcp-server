"""Tests for QIF loader date parsing, including Quicken's apostrophe format."""

import pytest
from app.qif_loader import QIFParser


@pytest.fixture
def parser():
    return QIFParser()


class TestParseDateApostropheFormat:
    """Tests for Quicken's apostrophe date format (M/ D'YY)."""

    def test_single_digit_month_padded_day(self, parser):
        assert parser._parse_date("1/ 1'24") == "2024-01-01"

    def test_single_digit_month_double_digit_day(self, parser):
        assert parser._parse_date("11/ 6'23") == "2023-11-06"

    def test_double_digit_month_double_digit_day(self, parser):
        assert parser._parse_date("12/31'24") == "2024-12-31"

    def test_no_space_before_day(self, parser):
        assert parser._parse_date("1/1'24") == "2024-01-01"

    def test_leading_trailing_whitespace_stripped(self, parser):
        assert parser._parse_date("  12/31'24  ") == "2024-12-31"


class TestParseDateExistingFormats:
    """Ensure existing date formats still parse correctly after the change."""

    def test_mmddyy(self, parser):
        assert parser._parse_date("12/31/23") == "2023-12-31"

    def test_mmddyyyy(self, parser):
        assert parser._parse_date("12/31/2023") == "2023-12-31"

    def test_iso_format(self, parser):
        assert parser._parse_date("2023-12-31") == "2023-12-31"

    def test_empty_returns_none(self, parser):
        assert parser._parse_date("") is None

    def test_none_input_returns_none(self, parser):
        assert parser._parse_date(None) is None

    def test_unparseable_returns_none(self, parser):
        assert parser._parse_date("not-a-date") is None


class TestLooksLikeDateApostropheFormat:
    """Tests that _looks_like_date recognises the apostrophe format."""

    def test_padded_day(self, parser):
        assert parser._looks_like_date("1/ 1'24") is True

    def test_no_space(self, parser):
        assert parser._looks_like_date("12/31'24") is True

    def test_two_digit_month_padded_day(self, parser):
        assert parser._looks_like_date("11/ 6'23") is True


class TestParseTransactionLinesNullDate:
    """Transactions with an unparseable date must be dropped (not stored with NULL)."""

    def test_unparseable_date_returns_none(self, parser):
        lines = ["Dnot-a-date", "T-50.00", "PTest Payee"]
        result = parser._parse_transaction_lines(lines)
        assert result is None

    def test_apostrophe_date_is_accepted(self, parser):
        lines = ["D1/ 1'24", "T-50.00", "PTest Payee"]
        result = parser._parse_transaction_lines(lines)
        assert result is not None
        assert result["date"] == "2024-01-01"
        assert result["amount"] == -50.0


class TestParseContentApostropheFormat:
    """Integration test: full QIF content with apostrophe dates parses correctly."""

    def test_full_qif_with_apostrophe_dates(self, parser):
        qif_content = """!Type:Bank
D1/ 1'24
T-100.00
PGrocery Store
^
D12/31'23
T-250.50
PRent
^
"""
        data = parser._parse_content(qif_content)
        txns = data["transactions"]
        assert len(txns) == 2
        assert txns[0]["date"] == "2024-01-01"
        assert txns[1]["date"] == "2023-12-31"
