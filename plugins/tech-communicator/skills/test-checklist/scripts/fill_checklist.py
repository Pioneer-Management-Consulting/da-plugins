"""Fill the test-checklist Excel template from a JSON file.

Usage: python fill_checklist.py <data.json> <output.xlsx>

The template's Checklist sheet keeps a sample section row (row 3) and item row (row 4).
Their styles are copied to every generated row, so edit the look in template.xlsx, not here.
The Test roles sheet keeps a sample row (row 2) for the same purpose.
"""
import json
import sys
from copy import copy
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.worksheet.datavalidation import DataValidation

TEMPLATE = Path(__file__).resolve().parent.parent / "template.xlsx"
COLS = 6  # # | What | How | Criteria | Status | Notes
STATUSES = "Not run,Pass,Fail,Blocked"


def row_styles(ws, row, ncols):
    return [copy(ws.cell(row=row, column=c)._style) for c in range(1, ncols + 1)]


def write_row(ws, row, values, styles):
    for c, (value, style) in enumerate(zip(values, styles), start=1):
        cell = ws.cell(row=row, column=c, value=value)
        cell._style = copy(style)


def main(data_path, out_path):
    data = json.loads(Path(data_path).read_text(encoding="utf-8"))
    for key in ("title", "roles", "sections"):
        if key not in data:
            sys.exit(f"Missing required JSON key: '{key}'")

    wb = load_workbook(TEMPLATE)

    ws = wb["Checklist"]
    section_style = row_styles(ws, 3, COLS)
    item_style = row_styles(ws, 4, COLS)
    ws.delete_rows(3, 2)
    ws["A1"] = data["title"]

    status_dv = DataValidation(type="list", formula1=f'"{STATUSES}"', allow_blank=True)
    ws.add_data_validation(status_dv)

    row = 3
    prereqs = data.get("prerequisites") or []
    if prereqs:
        write_row(ws, row, ["Prerequisites"] + [None] * (COLS - 1), section_style)
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=COLS)
        row += 1
        for text in prereqs:
            write_row(ws, row, [f"• {text}"] + [None] * (COLS - 1), item_style)
            ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=COLS)
            row += 1

    for s_num, section in enumerate(data["sections"], start=1):
        write_row(ws, row, [f"{s_num}. {section['name']}"] + [None] * (COLS - 1), section_style)
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=COLS)
        row += 1
        for i_num, item in enumerate(section["items"], start=1):
            values = [f"{s_num}.{i_num}", item["test"], item["how"], item["criteria"], "Not run", None]
            write_row(ws, row, values, item_style)
            status_dv.add(ws.cell(row=row, column=5))
            row += 1
    ws.auto_filter.ref = f"A2:F{row - 1}"

    roles = wb["Test roles"]
    role_style = row_styles(roles, 2, 4)
    roles.delete_rows(2)
    for r, role in enumerate(data["roles"], start=2):
        values = [role.get("role"), role.get("account"), role.get("access"), role.get("setup")]
        write_row(roles, r, values, role_style)

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    wb.save(out_path)
    print(f"Saved {out_path}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("Usage: python fill_checklist.py <data.json> <output.xlsx>")
    main(sys.argv[1], sys.argv[2])
