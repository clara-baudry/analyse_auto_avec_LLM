#!/usr/bin/env python3
"""Multi-turn LLM caller for the two-phase SDC pipeline (Qwen on SSP Cloud).

Only the OpenAI-compatible path is kept — SSP Cloud's endpoint, like Grok and OpenAI,
speaks the OpenAI chat API, and that is where Qwen is served. The model is stateless and
has no memory/skills, so the caller resends the **whole** conversation every call,
starting with the system prompt; nothing is remembered server-side.

Config comes only from the environment, so keys never live in code:

    LLM_MODEL      model name              (default: qwen3-6-35b-moe)
    LLM_BASE_URL   endpoint                (default: SSP Cloud)
    OPENAI_API_KEY the key for the endpoint (blank on this machine; set on the work
                   laptop, or injected as an Onyxia/Vault secret)

A local .env is loaded automatically if python-dotenv is installed.
"""

import os

DEFAULT_BASE_URL = "https://llm.lab.sspcloud.fr/api/v1"  # INSEE SSP Cloud
DEFAULT_MODEL = "qwen3-6-35b-moe"


def _load_dotenv():
    """Best-effort: load a gitignored .env so keys can stay out of the shell history."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv()


def resolve_config(model=None, base_url=None):
    """Resolve model / base_url / api_key from args then env. Raises if no key."""
    _load_dotenv()
    model = model or os.environ.get("LLM_MODEL", DEFAULT_MODEL)
    base_url = base_url or os.environ.get("LLM_BASE_URL", DEFAULT_BASE_URL)
    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("CLE_API_OPENWEBUI")
    if not api_key:
        raise RuntimeError(
            "No API key found. Set OPENAI_API_KEY or CLE_API_OPENWEBUI in your .env."
        )
    return {"model": model, "base_url": base_url, "api_key": api_key}


def chat(messages, *, model=None, base_url=None, temperature=0.0, max_tokens=8000):
    """Send a full `messages` list to the model and return the assistant text.

    `messages` is the OpenAI chat shape, e.g.
        [{"role": "system", "content": <prompt>},
         {"role": "user", "content": <metadata>}, ...]
    Temperature defaults to 0 for the most deterministic output the model allows.
    """
    from openai import OpenAI  # lazy: deterministic stages never import this

    cfg = resolve_config(model, base_url)
    client = OpenAI(base_url=cfg["base_url"], api_key=cfg["api_key"])
    resp = client.chat.completions.create(
        model=cfg["model"],
        temperature=temperature,
        max_tokens=max_tokens,
        messages=messages,
    )
    return resp.choices[0].message.content
