"""Post-session AI summary: an on-demand recap of a saved transcript.

Deliberately manual, never automatic — an LLM call fired at the end of every
session, free tier included, would grow cost with no user intent behind it
(the same pressure documented for the 2026-08-12 engine-routing cost-policy
change). One click, one call.

Text-only, one-shot `generate_content` against a standard Gemini text model —
NOT the realtime translate-preview model, which is built for streaming
simultaneous interpretation and is the wrong tool for single-shot
summarization of already-translated text.
"""
from __future__ import annotations

# A general-purpose text model, distinct from the realtime translate-preview
# model used for live sessions (see module docstring). Verify against current
# google-genai docs before changing.
SUMMARY_MODEL = "gemini-3.5-flash"

# Keeps the prompt bounded regardless of session length; the tail is kept
# (most recent content) rather than the head when a transcript overflows it.
MAX_TRANSCRIPT_CHARS = 24000


class SummaryUnavailable(Exception):
    """No usable key, an empty transcript, or the model call itself failed."""


def _transcript_text(record: dict) -> str:
    lines = []
    for turn in record.get("turns", []) or []:
        if not isinstance(turn, dict):
            continue
        text = (turn.get("text") or "").strip()
        if text:
            lines.append(text)
    joined = "\n".join(lines)
    if len(joined) > MAX_TRANSCRIPT_CHARS:
        joined = joined[-MAX_TRANSCRIPT_CHARS:]
    return joined


def build_prompt(record: dict) -> str:
    body = _transcript_text(record)
    if not body:
        raise SummaryUnavailable("empty transcript")
    return (
        "Summarize the following translated conversation transcript. Write a "
        "short summary (3-6 sentences), then a bulleted list of concrete "
        "action items or key points if any are present. Respond in the same "
        "language as the transcript. Do not invent content that is not in "
        "the transcript.\n\n---\n" + body
    )


def generate(api_key: str | None, record: dict) -> str:
    """Blocking call — run off the UI thread. Raises SummaryUnavailable on any
    failure (no key, empty transcript, or a model/network error)."""
    if not api_key:
        raise SummaryUnavailable("no key")
    prompt = build_prompt(record)
    from google import genai
    client = genai.Client(api_key=api_key)
    try:
        resp = client.models.generate_content(model=SUMMARY_MODEL, contents=prompt)
    except Exception as exc:
        raise SummaryUnavailable(str(exc)) from exc
    text = (getattr(resp, "text", "") or "").strip()
    if not text:
        raise SummaryUnavailable("empty response")
    return text
