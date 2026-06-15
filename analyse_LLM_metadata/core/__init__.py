"""Core of the preliminary SDC metadata pipeline.

UI-agnostic building blocks:
  read_input     workbook (.ods/.xlsx/.csv) -> Markdown            (deterministic)
  llm_client     multi-turn caller for Qwen on SSP Cloud           (the only model link)
  extract_json   slice + schema-validate the model's JSON array    (deterministic)
  json_to_table  validated JSON -> CSV for the producer            (deterministic)
  pipeline       the two-phase flow that wires the above together

Convention: every JSON value is a string; the literal "NA" marks an absent value or a
missing hierarchy (see core/schema/sdc_output.schema.json).
"""
