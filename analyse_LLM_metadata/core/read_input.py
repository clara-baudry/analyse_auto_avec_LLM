#!/usr/bin/env python3
"""Serialize a metadata workbook (.ods/.xlsx/.csv) into clean Markdown text.

Pipeline position:

    metadata workbook --> [THIS SCRIPT] --> Markdown text --> prompt_v4 + call_llm.py

Why this stage exists. The production model is undecided and may be a weaker
self-hosted one. In testing, some models (e.g. Gemini) could not parse a *binary*
.ods attachment at all. So we never hand the binary file to the LLM: we serialize
the workbook to plain UTF-8 Markdown here, deterministically, and feed that text.

What it preserves. Every sheet becomes its own Markdown table (sheet name as a
heading), so the "table-definition" inputs (one requested table per row) and the
"narrative-metadata" inputs (wide headers + long prose cells + a CEFF/legend
sheet) both survive intact. Ragged rows are padded; trailing empty cells/rows and
spreadsheet repeat-fillers are dropped; cell text is sanitized for Markdown.

This is 100% deterministic: same workbook in -> identical Markdown out.

Usage:
    python3 read_input.py metadata.ods                  # print Markdown to stdout
    python3 read_input.py metadata.xlsx -o meta.md      # also write to a file
"""

import argparse
import csv
import io
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

# ODF (OpenDocument) namespaces. ODS stores the grid in content.xml.
_NS = {
    "table": "urn:oasis:names:tc:opendocument:xmlns:table:1.0",
    "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0",
}
_T = "{urn:oasis:names:tc:opendocument:xmlns:table:1.0}"

# Cap on how far a `number-*-repeated` run is expanded. Spreadsheets pad sheets
# with huge empty repeat runs (e.g. 1000+ trailing columns); without a cap a
# single attribute could balloon a row to thousands of cells.
_MAX_REPEAT = 1024


def _clean(text):
    """Sanitize a cell for a Markdown table cell: no pipes, no newlines, no NBSP."""
    if text is None:
        return ""
    s = str(text).replace("\xa0", " ")
    s = s.replace("\r", " ").replace("\n", " ")
    s = s.replace("|", "\\|")
    return " ".join(s.split())  # collapse runs of whitespace


def _strip_trailing_empty(seq):
    """Drop trailing '' from a list (in place semantics, returns a new list)."""
    out = list(seq)
    while out and out[-1] == "":
        out.pop()
    return out


# --- readers: workbook -> [(sheet_name, rows)] where rows is list[list[str]] ---

def read_ods(path):
    """Read every sheet of an .ods as a list of (sheet_name, rows)."""
    with zipfile.ZipFile(path) as zf:
        root = ET.parse(zf.open("content.xml")).getroot()

    sheets = []
    for table in root.findall(".//table:table", _NS):
        name = table.get(_T + "name") or f"Sheet{len(sheets) + 1}"
        rows = []
        for row in table.findall("table:table-row", _NS):
            cells = []
            # Both real cells and covered (merged-away) cells hold column slots.
            for cell in row:
                tag = cell.tag
                if tag not in (_T + "table-cell", _T + "covered-table-cell"):
                    continue
                ps = cell.findall(".//text:p", _NS)
                txt = _clean(" ".join("".join(p.itertext()) for p in ps))
                rep = min(int(cell.get(_T + "number-columns-repeated", 1)), _MAX_REPEAT)
                cells.extend([txt] * rep)
            cells = _strip_trailing_empty(cells)
            row_rep = min(int(row.get(_T + "number-rows-repeated", 1)), _MAX_REPEAT)
            if not cells:
                rows.append([])  # one empty row; trailing ones get stripped below
            else:
                rows.extend([list(cells) for _ in range(row_rep)])
        while rows and not rows[-1]:
            rows.pop()
        if any(any(c for c in r) for r in rows):  # keep only non-empty sheets
            sheets.append((name, rows))
    return sheets


def read_xlsx(path):
    """Read every sheet of an .xlsx (lazy import: openpyxl only needed here)."""
    import openpyxl  # noqa: F401  (lazy: keeps .ods/.csv paths dependency-free)

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    sheets = []
    for ws in wb.worksheets:
        rows = []
        for raw in ws.iter_rows(values_only=True):
            cells = _strip_trailing_empty([_clean("" if v is None else v) for v in raw])
            rows.append(cells)
        while rows and not rows[-1]:
            rows.pop()
        if any(any(c for c in r) for r in rows):
            sheets.append((ws.title, rows))
    return sheets


def read_csv(path):
    """Read a .csv as a single sheet named after the file stem."""
    text = Path(path).read_text(encoding="utf-8-sig")
    rows = [
        _strip_trailing_empty([_clean(c) for c in r])
        for r in csv.reader(io.StringIO(text))
    ]
    while rows and not rows[-1]:
        rows.pop()
    return [(Path(path).stem, rows)] if rows else []


def read_workbook(path):
    """Dispatch on file extension. Returns [(sheet_name, rows), ...]."""
    low = str(path).lower()
    if low.endswith(".ods"):
        return read_ods(path)
    if low.endswith(".xlsx"):
        return read_xlsx(path)
    if low.endswith(".csv"):
        return read_csv(path)
    raise ValueError(f"Unsupported input type: {path} (expected .ods/.xlsx/.csv)")


# --- Markdown rendering -----------------------------------------------------

def _table_md(rows):
    """Render one sheet's rows as a GitHub-flavored Markdown table.

    Row 0 is treated as the header (the table-definition inputs put a real header
    there; for narrative inputs the title row reads fine as a header too). All
    rows are padded to the sheet's widest row so the table stays rectangular.
    """
    width = max((len(r) for r in rows), default=0)
    if width == 0:
        return ""
    padded = [r + [""] * (width - len(r)) for r in rows]
    header = padded[0]
    body = padded[1:]
    lines = ["| " + " | ".join(header) + " |",
             "| " + " | ".join(["---"] * width) + " |"]
    for r in body:
        lines.append("| " + " | ".join(r) + " |")
    return "\n".join(lines)


def to_markdown(sheets, title=None):
    """Render [(sheet_name, rows), ...] as a single Markdown document."""
    parts = []
    if title:
        parts.append(f"# {title}\n")
    for name, rows in sheets:
        table = _table_md(rows)
        if table:
            parts.append(f"## {name}\n\n{table}")
    return "\n\n".join(parts) + "\n"


def serialize(path):
    """Importable helper for run_pipeline: workbook path -> Markdown string."""
    sheets = read_workbook(path)
    return to_markdown(sheets, title=Path(path).name)


# --- CLI --------------------------------------------------------------------

def main(argv=None):
    p = argparse.ArgumentParser(description="Serialize an .ods/.xlsx/.csv workbook to Markdown.")
    p.add_argument("input", help="Metadata workbook (.ods/.xlsx/.csv)")
    p.add_argument("-o", "--output", help="Write Markdown here (default: stdout)")
    args = p.parse_args(argv)

    if not Path(args.input).exists():
        print(f"Input not found: {args.input}", file=sys.stderr)
        return 2

    try:
        md = serialize(args.input)
    except ImportError:
        print("!! .xlsx needs openpyxl: pip install openpyxl", file=sys.stderr)
        return 2

    if args.output:
        Path(args.output).write_text(md, encoding="utf-8")
        print(f"Wrote {args.output}  ({len(md)} chars)")
    else:
        sys.stdout.write(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
