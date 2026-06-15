#!/usr/bin/env python3
"""Slice the JSON array out of an LLM reply and validate it against the contract.

Pipeline position:

    LLM reply --> [THIS SCRIPT] --> validated JSON array --> json_to_table.py

The model is told to print the JSON array first (starting `[`, ending `]`) and
then a plain-text reflection ending with `WAITING FOR CORRECTION`. This script
slices to the outermost array, parses it, and validates it against
schema/sdc_output.schema.json. It FAILS LOUD: any malformed output (missing
keys, wrong types, the token "NA" where null is required, unexpected keys) is
reported and the script exits non-zero, so a bad LLM reply never reaches the
deterministic transform.

Usage:
    python3 extract_json.py reply.txt                 # validate, print summary
    python3 extract_json.py reply.txt -o clean.json   # also write the clean array
"""

import argparse
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

SCHEMA_PATH = Path(__file__).parent / "schema" / "sdc_output.schema.json"


def slice_array(text):
    """Return the substring from the first '[' to the last ']' (inclusive)."""
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1 or end < start:
        raise ValueError("No JSON array found in the reply (no '[' ... ']').")
    return text[start: end + 1]


def load_schema():
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def validate(records, schema=None):
    """Return a list of human-readable validation error strings ([] if valid)."""
    validator = Draft202012Validator(schema or load_schema())
    errors = []
    for err in sorted(validator.iter_errors(records), key=lambda e: list(e.path)):
        loc = "/".join(str(p) for p in err.path) or "(root)"
        errors.append(f"  at {loc}: {err.message}")
    return errors


def load_and_validate(path):
    """Parse + validate a reply file. Raises ValueError on any problem.

    Returns the list of record dicts. Used by run_pipeline.py.
    """
    text = Path(path).read_text(encoding="utf-8")
    records = json.loads(slice_array(text))
    if not isinstance(records, list):
        raise ValueError(f"Expected a JSON array, got {type(records).__name__}.")
    errors = validate(records)
    if errors:
        raise ValueError("Schema validation failed:\n" + "\n".join(errors))
    return records


def main(argv=None):
    p = argparse.ArgumentParser(description="Extract + validate the LLM JSON array.")
    p.add_argument("input", help="LLM reply file (JSON array + optional reflection)")
    p.add_argument("-o", "--output", help="Write the clean JSON array to this path")
    args = p.parse_args(argv)

    text = Path(args.input).read_text(encoding="utf-8")
    try:
        records = json.loads(slice_array(text))
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"FAIL: could not parse a JSON array from {args.input}\n  {exc}")
        return 1

    if not isinstance(records, list):
        print(f"FAIL: expected a JSON array, got {type(records).__name__}.")
        return 1

    errors = validate(records)
    if errors:
        print(f"FAIL: {len(errors)} schema violation(s) in {args.input}:")
        print("\n".join(errors))
        return 1

    print(f"OK: {len(records)} record(s) valid against {SCHEMA_PATH.name}")
    if args.output:
        Path(args.output).write_text(
            json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"Wrote clean array to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
