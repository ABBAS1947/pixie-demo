"""Failure classifier — diagnose WHY the student is stuck before rewriting.

Four modes:
- words: terminology is the blocker ("what does X mean", "too many hard words").
- analogy: the example did not connect ("that example is weird", "bad comparison").
- logic: the steps did not follow ("how did you get from A to B", "lost in the steps").
- idea: the core concept did not land (everything else, the default).

Layer 1 is regex (microseconds, no LLM). Layer 2 is one cheap JSON call,
only when regex is inconclusive. Cap: MAX_RE_CHUNKS alts per chunk index,
then the caller escalates to a teacher.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

MAX_RE_CHUNKS = 2

MODES = ("words", "analogy", "logic", "idea")

_WORDS_RE = re.compile(
    r"(what does .* mean|meaning of|define|definition|hard word|difficult word|"
    r"too many .*word|simple.*word|easier word|don't know .*word|vocab)",
    re.IGNORECASE,
)

_ANALOGY_RE = re.compile(
    r"(example|analogy|comparison|compare|like what|weird example|bad example|"
    r"doesn't make sense.*example|example.*confus)",
    re.IGNORECASE,
)

_LOGIC_RE = re.compile(
    r"(how did you get|steps?|first.*then|order|sequence|lost me|jump|"
    r"too fast|slow down|step by step|confusing order)",
    re.IGNORECASE,
)


def regex_mode(student_message: str) -> str | None:
    """Return a mode if the student names the problem, else None."""
    msg = student_message.strip()
    if _WORDS_RE.search(msg):
        return "words"
    if _ANALOGY_RE.search(msg):
        return "analogy"
    if _LOGIC_RE.search(msg):
        return "logic"
    return None


CLASSIFY_SYSTEM = """You classify why a student is stuck. Reply ONLY with strict JSON: {"mode": "words"|"analogy"|"logic"|"idea"}.
- words: blocked by vocabulary or terminology.
- analogy: the example or comparison did not connect.
- logic: the steps or order did not follow.
- idea: the underlying concept itself did not land."""

# Hard ceilings so no turn can ever hang past the client. The turn engine
# serves a safe fallback when these hit instead of a dropped request.
CLASSIFY_TIMEOUT_S = 15.0


async def classify_failure_mode(
    last_item_body: str,
    student_message: str,
    call_llm_json,
) -> str:
    """Regex first, one cheap LLM call only when inconclusive. Never raises."""
    hit = regex_mode(student_message)
    if hit:
        return hit
    try:
        import asyncio as _aio

        out = await _aio.wait_for(
            call_llm_json(
                CLASSIFY_SYSTEM,
                f"Teacher said: {last_item_body[:400]}\nStudent said: {student_message.strip()[:400]}",
            ),
            timeout=CLASSIFY_TIMEOUT_S,
        )
        mode = str(out.get("mode", "idea")).lower().strip()
        return mode if mode in MODES else "idea"
    except Exception as e:
        logger.warning("failure classification failed, defaulting to idea: %s", e)
        return "idea"


MODE_GUIDE = {
    "words": "Use the simplest words you know. Define every term inline before using it.",
    "analogy": "Drop the old example entirely. Use a completely different domain the student knows.",
    "logic": "Slow down. Numbered steps, one fact per step, no jumps.",
    "idea": "Lead with a question from the student's own world, then build the idea up from their answer.",
}
