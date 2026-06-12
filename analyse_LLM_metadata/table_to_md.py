#!/usr/bin/env python3
"""
table_to_md.py — Deterministic converter: ODS / XLSX / XLS / CSV / MD → Markdown

Rules (no explanations added, only cell values and sheet names):
  1. Fully-empty rows are dropped.
  2. A row is a TEXT ROW if its non-empty cell count < max(2, max_filled * 0.5),
     where max_filled is the highest non-empty count seen in the sheet.
     Text rows are rendered as plain lines (title, annotation, merged-cell labels).
  3. The first non-text row becomes the table header.
  4. Subsequent non-text rows are table data rows.
  5. Sheets are separated by a horizontal rule.
  6. Integer-valued floats (1.0, 2.0 …) are rendered without the decimal part.
  7. Pipe characters inside cells are escaped so the Markdown table stays valid.
  8. Inline newlines inside cells are collapsed to a single space.
"""

import sys
import pandas as pd
from pathlib import Path


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def _fmt(v) -> str:
    """Format a single cell value as a clean string."""
    if pd.isna(v):
        return ""
    if isinstance(v, float) and v == int(v):
        return str(int(v))
    return str(v).strip().replace("\n", " ").replace("\r", " ")


def _md_row(cells: list[str]) -> str:
    escaped = [c.replace("|", "\\|") for c in cells]
    return "| " + " | ".join(escaped) + " |"


def _md_sep(n: int) -> str:
    return "| " + " | ".join(["---"] * n) + " |"


# ---------------------------------------------------------------------------
# Sheet → Markdown
# ---------------------------------------------------------------------------

def sheet_to_markdown(df: pd.DataFrame) -> str:
    n_cols = df.shape[1]

    # Drop fully-empty rows
    rows = [row for _, row in df.iterrows() if not row.isna().all()]
    if not rows:
        return ""

    filled_counts = [
        sum(1 for v in row if not pd.isna(v) and str(v).strip())
        for row in rows
    ]
    max_filled = max(filled_counts)

    # Threshold: below this → text row (title, annotation, merged label)
    threshold = max(2, max_filled * 0.5)

    lines: list[str] = []
    header_done = False

    for row, count in zip(rows, filled_counts):
        cells = [_fmt(v) for v in row][:n_cols]

        if count < threshold:
            text = " ".join(c for c in cells if c)
            if text:
                lines.append(text)
        else:
            if not header_done:
                lines.append(_md_row(cells))
                lines.append(_md_sep(n_cols))
                header_done = True
            else:
                lines.append(_md_row(cells))

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# File → Markdown (all sheets)
# ---------------------------------------------------------------------------

def convert(input_path: Path) -> str:
    suffix = input_path.suffix.lower()

    if suffix == ".ods":
        sheets = pd.read_excel(input_path, sheet_name=None, engine="odf", header=None)
    elif suffix in (".xlsx", ".xls"):
        sheets = pd.read_excel(input_path, sheet_name=None, header=None)
    elif suffix == ".csv":
        sheets = {"Sheet1": pd.read_csv(input_path, header=None)}
    elif suffix == ".md":
        return input_path.read_text(encoding="utf-8")
    else:
        raise ValueError(f"Unsupported format: {suffix}")

    parts = []
    for name, df in sheets.items():
        md = sheet_to_markdown(df)
        if md:
            parts.append(f"## {name}\n\n{md}")

    return "\n\n---\n\n".join(parts)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("Usage: python table_to_md.py <input_file> [output.md]")

    src = Path(sys.argv[1])
    if not src.exists():
        sys.exit(f"File not found: {src}")

    dst = Path(sys.argv[2]) if len(sys.argv) >= 3 else src.with_suffix(".md")
    dst.write_text(convert(src), encoding="utf-8")
    print(f"→ {dst}")
