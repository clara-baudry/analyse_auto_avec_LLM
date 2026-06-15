#!/usr/bin/env python3
"""UI-agnostic orchestration of the two-phase SDC metadata pipeline.

This is "the pieces put together": any front end (CLI, Streamlit, Gradio, …) drives the
flow through these four functions and never needs to know the model or schema details.

    serialize(path)            workbook -> Markdown
    start(markdown)            Phase 1: returns either the model's QUESTIONS,
                               or — when there are none — the JSON it auto-produced
    answer(history, answers)   Phase 2: producer's answers -> validated JSON records
    to_csv(records, out_base)  validated JSON -> CSV for the producer

The prompt (prompts/prompt_questions.md) is the system message on every model call,
because the model has no memory. Phase 1 vs Phase 2 routing is decided by whether the
reply already contains a valid JSON array (the prompt's "Aucune question." auto-continue).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from . import read_input, extract_json, json_to_table, llm_client

PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "prompt_questions.md"


def load_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


# --- input -----------------------------------------------------------------

def serialize(path) -> str:
    """Workbook (.ods/.xlsx/.csv) -> Markdown (deterministic)."""
    return read_input.serialize(path)


def wrap(markdown: str) -> str:
    """Wrap the serialized metadata in the prompt's instruction/data delimiter."""
    return f"<metadonnees>\n{markdown}\n</metadonnees>"


# --- reply classification --------------------------------------------------

def _records_if_valid(reply: str):
    """Return validated records if `reply` carries a valid JSON array, else None.

    Used to tell apart the two Phase-1 outcomes: a valid array means the model found no
    questions and auto-continued to the JSON; anything else means it asked questions.
    """
    start, end = reply.find("["), reply.rfind("]")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        records = json.loads(reply[start: end + 1])
    except json.JSONDecodeError:
        return None
    if not isinstance(records, list) or extract_json.validate(records):
        return None
    return records


def _questions_text(reply: str) -> str:
    """The final question list — everything after the first '---' separator."""
    parts = reply.split("\n---", 1)
    return (parts[1] if len(parts) > 1 else reply).strip()


# --- phases ----------------------------------------------------------------

@dataclass
class Phase1Result:
    raw: str                 # the model's full Phase-1 reply
    history: list            # running message list (system, user, assistant)
    records: list | None     # set when the model auto-continued (no questions)
    questions: str | None    # set when the model asked questions

    @property
    def auto_continued(self) -> bool:
        return self.records is not None


def start(metadata_md: str, **llm_kwargs) -> Phase1Result:
    """Phase 1: send the metadata, get questions (or the auto-continued JSON)."""
    history = [
        {"role": "system", "content": load_prompt()},
        {"role": "user", "content": wrap(metadata_md)},
    ]
    reply = llm_client.chat(history, **llm_kwargs)
    history.append({"role": "assistant", "content": reply})

    records = _records_if_valid(reply)
    if records is not None:
        return Phase1Result(raw=reply, history=history, records=records, questions=None)
    return Phase1Result(raw=reply, history=history, records=None,
                        questions=_questions_text(reply))


def answer(history: list, answers_text: str, **llm_kwargs) -> list:
    """Phase 2: append the producer's answers and return the validated JSON records."""
    history = history + [{"role": "user", "content": answers_text}]
    reply = llm_client.chat(history, **llm_kwargs)
    history.append({"role": "assistant", "content": reply})

    records = _records_if_valid(reply)
    if records is None:
        raise ValueError("Phase 2 reply did not contain a valid JSON array:\n\n" + reply)
    return records


# --- output ----------------------------------------------------------------

def to_csv(records: list, out_base) -> tuple:
    """Validate the records and write the producer-facing CSV. Returns (cols, rows)."""
    errors = extract_json.validate(records)
    if errors:
        raise ValueError("Schema validation failed:\n" + "\n".join(errors))
    out = Path(out_base).with_suffix(".csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    return json_to_table.write_csv(records, out)
