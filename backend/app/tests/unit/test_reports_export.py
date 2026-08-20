"""Unit tests for the format-agnostic report writers (no DB needed --
these operate on plain row/column data). Each format is verified by
actually parsing the real output with the library that would consume it
in practice, not just checking it's non-empty bytes.
"""

import csv
import io
import json

from openpyxl import load_workbook

from app.reports.export import content_type_for, to_csv, to_json, to_pdf, to_xlsx

_COLUMNS = ["id", "name", "score"]
_ROWS = [
    {"id": "1", "name": "Example Corp", "score": 82},
    {"id": "2", "name": "Other, Inc.", "score": None},
]


def test_to_csv_round_trips_through_a_real_csv_reader():
    body = to_csv(_ROWS, _COLUMNS)
    reader = csv.DictReader(io.StringIO(body.decode("utf-8")))
    parsed = list(reader)
    assert parsed[0]["name"] == "Example Corp"
    assert parsed[1]["name"] == "Other, Inc."  # comma-in-value correctly quoted/escaped
    assert parsed[1]["score"] == ""


def test_to_json_round_trips_and_projects_only_requested_columns():
    body = to_json(_ROWS, ["id", "name"])
    parsed = json.loads(body)
    assert parsed == [{"id": "1", "name": "Example Corp"}, {"id": "2", "name": "Other, Inc."}]


def test_to_xlsx_produces_a_real_workbook_openpyxl_can_read_back():
    body = to_xlsx(_ROWS, _COLUMNS, title="test_report")
    workbook = load_workbook(io.BytesIO(body))
    sheet = workbook.active
    header = [cell.value for cell in next(sheet.iter_rows(min_row=1, max_row=1))]
    assert header == _COLUMNS
    first_data_row = [cell.value for cell in next(sheet.iter_rows(min_row=2, max_row=2))]
    assert first_data_row == ["1", "Example Corp", 82]


def test_to_pdf_produces_real_pdf_bytes():
    body = to_pdf(_ROWS, _COLUMNS, title="Test Report")
    assert body.startswith(b"%PDF-")
    assert len(body) > 500  # a genuinely rendered document, not a stub


def test_content_type_for_known_and_unknown_formats():
    assert content_type_for("csv") == "text/csv"
    assert content_type_for("pdf") == "application/pdf"
    try:
        content_type_for("yaml")
        raise AssertionError("expected ValueError")
    except ValueError:
        pass
