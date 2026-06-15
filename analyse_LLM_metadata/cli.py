#!/usr/bin/env python3
"""Terminal driver for the preliminary SDC pipeline (and offline test harness).

Modes
-----
  python cli.py meta.ods -o out/run1      Full two-phase run. Needs Qwen creds in .env
                                          (LLM_MODEL / LLM_BASE_URL / OPENAI_API_KEY).
  python cli.py meta.ods --serialize-only Print the serialized Markdown and exit (no model).
  python cli.py --reply saved.txt -o out  Offline: a saved JSON reply -> CSV (no model).

The two offline modes need no API key, so the deterministic half (serialize, validate,
CSV) is testable on any machine — e.g. this Mac, which has no access to the model.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from core import pipeline, extract_json, json_to_table  # noqa: E402


def _records_from_reply(path: Path) -> list:
    """Slice + validate a JSON array out of a saved model reply (offline path)."""
    text = path.read_text(encoding="utf-8")
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1 or end < start:
        raise ValueError(f"No JSON array found in {path}")
    records = json.loads(text[start: end + 1])
    errors = extract_json.validate(records)
    if errors:
        raise ValueError("Schema validation failed:\n" + "\n".join(errors))
    return records


def _read_multiline() -> str:
    """Read the producer's answers from stdin until a blank line (or EOF)."""
    lines = []
    try:
        while True:
            line = input()
            if line == "":
                break
            lines.append(line)
    except EOFError:
        pass
    return "\n".join(lines)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Preliminary SDC metadata pipeline driver.")
    p.add_argument("input", nargs="?", help="metadata workbook (.ods/.xlsx/.csv)")
    p.add_argument("--reply", help="offline: a saved LLM reply (JSON array) -> CSV")
    p.add_argument("-o", "--output", help="output base path (default: alongside the input)")
    p.add_argument("--serialize-only", action="store_true", help="print the Markdown and exit")
    args = p.parse_args(argv)

    # --- offline: saved reply -> CSV (no model, no key) ---
    if args.reply:
        reply_path = Path(args.reply)
        if not reply_path.exists():
            print(f"Reply not found: {reply_path}", file=sys.stderr)
            return 2
        records = _records_from_reply(reply_path)
        base = Path(args.output) if args.output else reply_path.with_suffix("")
        base.parent.mkdir(parents=True, exist_ok=True)
        cols, rows = json_to_table.write_csv(records, base.with_suffix(".csv"))
        print(f"Wrote {base.with_suffix('.csv')}  ({len(rows)} rows x {len(cols)} cols)")
        return 0

    if not args.input:
        p.error("provide a metadata workbook, or --reply for the offline path")
    in_path = Path(args.input)
    if not in_path.exists():
        print(f"Input not found: {in_path}", file=sys.stderr)
        return 2

    md = pipeline.serialize(in_path)
    if args.serialize_only:
        sys.stdout.write(md)
        return 0

    base = Path(args.output) if args.output else in_path.with_suffix("")

    print("Phase 1 — envoi des métadonnées au modèle...")
    try:
        r = pipeline.start(md)
    except RuntimeError as exc:  # missing key, etc.
        print(f"FAIL: {exc}", file=sys.stderr)
        return 2

    if r.auto_continued:
        print("Aucune question — le modèle a produit le JSON directement.")
        records = r.records
    else:
        print("\n--- Questions du modèle ---\n")
        print(r.questions)
        print("\n--- Vos réponses (terminez par une ligne vide) ---")
        answers = _read_multiline()
        records = pipeline.answer(r.history, answers)

    cols, rows = pipeline.to_csv(records, base)
    print(f"\nWrote {base.with_suffix('.csv')}  ({len(rows)} rows x {len(cols)} cols)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
