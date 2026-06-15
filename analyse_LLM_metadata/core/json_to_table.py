#!/usr/bin/env python3
"""Deterministic transform: SDC LLM JSON output -> flat table -> .csv AND .rds.

Pipeline position:

    ODS metadata --> LLM + prompt --> JSON --> [THIS SCRIPT] --> .csv + .rds --> rtauargus
                     (probabilistic)         (100% deterministic)

The LLM stage is the only non-deterministic link. From the JSON onward everything
is fixed code: the same JSON in produces byte-identical tables out, so the table
handed to rtauargus is reproducible and auditable.

Every run writes BOTH files from the same JSON:
  * <name>.csv  -- for the human expert to review (NA-vs-blank convention below).
  * <name>.rds  -- for rtauargus to consume (real R NA for every missing cell).

The two files carry the same information; they differ only in how "missing" is
rendered, because they have different readers:

  NA-vs-blank convention (CSV, human-facing). Every value column is paired with
  its hierarchy column -- (field, hrc_field), (indicator, hrc_indicator),
  (spanning_i, hrc_spanning_i). For each pair:
    * value PRESENT -> value cell = the value; hierarchy cell = its hrc code, or
      the literal "NA" when there is no hierarchy (JSON null). Here "NA" means
      "this attribute exists but has no hierarchy".
    * value ABSENT  -> BOTH cells are left blank. A blank means the
      attribute/dimension does not exist at all (e.g. no 2nd spanning dimension).
  table_name has no hierarchy column: the value, or blank if missing.

  RDS convention (rtauargus-facing). Values verbatim; every missing cell (both
  "no hierarchy" and "absent dimension") becomes a real R NA. rtauargus only
  needs the value cells filled and the hierarchy cells to be an hrc reference or
  NA. NOTE: the exact token rtauargus expects for "no hierarchy" is still to be
  confirmed with the supervisor; if it must differ from R NA, change write_rds.

The nested `spanning_variables` array is flattened into spanning_1/hrc_spanning_1,
spanning_2/hrc_spanning_2, ... up to the maximum number of spanning variables
found in the input. There is NO cap.

Usage:
    python3 json_to_table.py input.json                 # -> input.csv + input.rds
    python3 json_to_table.py input.json -o out/table    # -> out/table.csv + out/table.rds
    python3 json_to_table.py input.json --stdout         # preview the CSV table only
"""

import argparse
import csv
import json
import sys
from pathlib import Path

BASE_VALUE_COLS = ["field", "indicator"]  # value cols that carry a paired hrc col

HEADER_BASE = ["table_name", "field", "hrc_field", "indicator", "hrc_indicator"]


def load_records(path):
    """Read the JSON array produced by the LLM (tolerates trailing reflection text).

    The prompt tells the model to print plain-text reflection after the closing
    `]`, so we slice to the outermost array before parsing.
    """
    text = Path(path).read_text(encoding="utf-8")
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1 or end < start:
        raise ValueError(f"No JSON array found in {path}")
    records = json.loads(text[start: end + 1])
    if not isinstance(records, list):
        raise ValueError(f"{path}: expected a JSON array, got {type(records).__name__}")
    return records


def _indicator(rec):
    """Coalesce the indicator across schema variants.

    The committed contract (prompt v4) uses a single `indicator` key. Some model
    runs split it into `indicator_code` / `indicator_label`; tolerate both so a
    one-off deviation does not drop the column.
    """
    for key in ("indicator", "indicator_label", "indicator_code"):
        val = rec.get(key)
        if not _absent(val):
            return val
    return None


def _spanning_pairs(rec):
    """Return the [(code, hrc), ...] list for a record, nested-schema only."""
    return [(sv.get("code"), sv.get("hrc")) for sv in (rec.get("spanning_variables") or [])]


def _absent(value):
    """A value is 'absent' if it is JSON null or an empty/whitespace string."""
    return value is None or (isinstance(value, str) and value.strip() == "")


def max_spanning(records):
    return max((len(_spanning_pairs(r)) for r in records), default=0) or 1


def header(records):
    cols = list(HEADER_BASE)
    for i in range(1, max_spanning(records) + 1):
        cols += [f"spanning_{i}", f"hrc_spanning_{i}"]
    return cols


# --- CSV (human-facing, NA-vs-blank) ---------------------------------------

def _csv_scalar(value):
    return "" if _absent(value) else str(value)


def _csv_pair(value, hrc):
    """(value present -> (value, hrc or 'NA')) ; (value absent -> ('', ''))."""
    if _absent(value):
        return "", ""
    return str(value), ("NA" if _absent(hrc) else str(hrc))


def csv_rows(records):
    n_span = max_spanning(records)
    rows = []
    for rec in records:
        row = [_csv_scalar(rec.get("table_name"))]
        row += _csv_pair(rec.get("field"), rec.get("hrc_field"))
        row += _csv_pair(_indicator(rec), rec.get("hrc_indicator"))
        pairs = _spanning_pairs(rec)
        for i in range(n_span):
            code, hrc = pairs[i] if i < len(pairs) else (None, None)
            row += _csv_pair(code, hrc)
        rows.append(row)
    return rows


def write_csv(records, path):
    cols = header(records)
    rows = csv_rows(records)
    # utf-8-sig so LibreOffice/Excel detect UTF-8 (accents in field names).
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        w.writerows(rows)
    return cols, rows


# --- RDS (rtauargus-facing, real R NA) -------------------------------------

def write_rds(records, path):
    """Write the same table as .rds, with every missing cell as a real R NA.

    Lazy imports so the CSV path stays dependency-free where pandas/pyreadr are
    not installed.
    """
    import pandas as pd
    import pyreadr

    cols = header(records)
    n_span = max_spanning(records)
    data = []
    for rec in records:
        row = {
            "table_name": _none(rec.get("table_name")),
            "field": _none(rec.get("field")),
            "hrc_field": _none_if_value_absent(rec.get("field"), rec.get("hrc_field")),
            "indicator": _none(_indicator(rec)),
            "hrc_indicator": _none_if_value_absent(_indicator(rec), rec.get("hrc_indicator")),
        }
        pairs = _spanning_pairs(rec)
        for i in range(1, n_span + 1):
            code, hrc = pairs[i - 1] if i <= len(pairs) else (None, None)
            row[f"spanning_{i}"] = _none(code)
            row[f"hrc_spanning_{i}"] = _none_if_value_absent(code, hrc)
        data.append(row)

    df = pd.DataFrame(data, columns=cols)
    df = df.where(df.notna(), other=None)  # ensure real None -> R NA
    pyreadr.write_rds(str(path), df)


def _none(value):
    return None if _absent(value) else str(value)


def _none_if_value_absent(value, hrc):
    """Hierarchy cell for the RDS: R NA when the value is absent OR has no hierarchy."""
    if _absent(value) or _absent(hrc):
        return None
    return str(hrc)


# --- CLI -------------------------------------------------------------------

def main(argv=None):
    p = argparse.ArgumentParser(description="Convert SDC LLM JSON to .csv + .rds.")
    p.add_argument("input", help="JSON file from the LLM stage")
    p.add_argument("-o", "--output", help="Output base path (default: alongside input, same stem)")
    p.add_argument("--stdout", action="store_true", help="Print the CSV table and exit")
    args = p.parse_args(argv)

    records = load_records(args.input)

    if args.stdout:
        cols = header(records)
        rows = csv_rows(records)
        widths = [max(len(cols[c]), *(len(r[c]) for r in rows)) if rows else len(cols[c])
                  for c in range(len(cols))]

        def format_line(cells):
            return "  ".join(str(x).ljust(widths[i]) for i, x in enumerate(cells))
        print(format_line(cols))
        for r in rows:
            print(format_line(r))
        print(f"\n[{len(rows)} rows x {len(cols)} columns] spanning pairs: {max_spanning(records)}")
        return 0

    base = Path(args.output) if args.output else Path(args.input).with_suffix("")
    base.parent.mkdir(parents=True, exist_ok=True)
    csv_path = base.with_suffix(".csv")
    rds_path = base.with_suffix(".rds")

    cols, rows = write_csv(records, csv_path)
    print(f"Wrote {csv_path}  ({len(rows)} rows x {len(cols)} columns)")

    try:
        write_rds(records, rds_path)
        print(f"Wrote {rds_path}  -> hand to rtauargus")
    except ImportError:
        print(f"!! Skipped {rds_path}: pyreadr/pandas not installed. "
              f"Produce the .rds on Onyxia (pip install pyreadr) or in R from the CSV.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
