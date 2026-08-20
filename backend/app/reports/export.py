"""Format-agnostic report writers. Take the same `rows`/`columns` shape
regardless of report type (see app/reports/rows.py) and produce real
bytes in one of four formats -- CSV and JSON via the stdlib, XLSX via
openpyxl, PDF via reportlab. No format is faked as another (e.g. no
"PDF" that's secretly a text file with a .pdf extension) -- each writer
produces a file real spreadsheet/PDF software can open.
"""

import csv
import io
import json

from openpyxl import Workbook
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Table, TableStyle

_CONTENT_TYPES = {
    "csv": "text/csv",
    "json": "application/json",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pdf": "application/pdf",
}


def content_type_for(export_format: str) -> str:
    try:
        return _CONTENT_TYPES[export_format]
    except KeyError:
        raise ValueError(f"unsupported export format: {export_format}") from None


def to_csv(rows: list[dict], columns: list[str]) -> bytes:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def to_json(rows: list[dict], columns: list[str]) -> bytes:
    projected = [{col: row.get(col) for col in columns} for row in rows]
    return json.dumps(projected, indent=2, default=str).encode("utf-8")


def to_xlsx(rows: list[dict], columns: list[str], *, title: str) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = title[:31] or "Report"  # Excel sheet-name length limit
    sheet.append(columns)
    for row in rows:
        sheet.append([row.get(col) for col in columns])

    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def to_pdf(rows: list[dict], columns: list[str], *, title: str) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(letter))
    styles = getSampleStyleSheet()

    table_data = [columns] + [[_pdf_cell(row.get(col)) for col in columns] for row in rows]
    table = Table(table_data, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#333333")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    doc.build([Paragraph(title, styles["Heading1"]), table])
    return buffer.getvalue()


def _pdf_cell(value) -> str:
    if value is None:
        return ""
    text = str(value)
    return text[:200]  # keep cells from blowing up page layout on long evidence strings
