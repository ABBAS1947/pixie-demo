"""Smart note generation — creates structured, age-appropriate study notes
from extracted file content.

The note is NOT a raw transcript. It's a properly formatted study note
with clear headings, key terms, concise explanations, and a summary.
Complexity adapts to the student's grade level.
"""

from app.services.llm_registry import get_provider
from app.services.untrusted_document import DOCUMENT_GUARD, untrusted_document_text


# Grade-band instructions for the generation prompt.
# Each band adjusts language complexity, depth, and formatting.
_GRADE_BANDS = {
    "early": {  # grades 1-5
        "label": "a young student (grades 1-5)",
        "instructions": (
            "Use very simple language and short sentences. "
            "Explain everything like you're talking to a curious 8-year-old. "
            "Use bullet points heavily. Avoid technical jargon — if you must "
            "use a technical term, explain it in parentheses immediately. "
            "Use analogies the student would understand (school, pets, food, games). "
            "Keep the total length under 400 words."
        ),
    },
    "middle": {  # grades 6-8
        "label": "a middle school student (grades 6-8)",
        "instructions": (
            "Use clear, direct language. Define technical terms the first time "
            "they appear. Use a mix of short paragraphs and bullet points. "
            "Include 'Key Terms' as a section with brief definitions. "
            "Can use slightly longer explanations but keep paragraphs under "
            "4 sentences. Keep the total length under 600 words."
        ),
    },
    "high": {  # grades 9-12
        "label": "a high school student (grades 9-12)",
        "instructions": (
            "Use precise, academic language. Technical terms are expected but "
            "should still be clearly defined. Use structured sections with "
            "headings. Can include formulas, processes, and multi-step "
            "explanations. Keep paragraphs concise. Include a 'Key Terms' "
            "section and a 'Summary' section. Keep the total length under "
            "800 words."
        ),
    },
}


def _grade_band(grade_level: str | None) -> str:
    """Map a grade_level string to a band: 'early', 'middle', or 'high'."""
    if not grade_level:
        return "middle"  # safe default
    # Extract the number from strings like "9", "Grade 9", "9th", etc.
    import re
    nums = re.findall(r"\d+", str(grade_level))
    if not nums:
        return "middle"
    grade = int(nums[0])
    if grade <= 5:
        return "early"
    elif grade <= 8:
        return "middle"
    else:
        return "high"


async def generate_smart_note(
    raw_text: str,
    grade_level: str | None = None,
    title_hint: str | None = None,
    *,
    require_generated: bool = False,
) -> str:
    """Generate a structured study note from raw extracted text.

    Returns formatted markdown suitable for the notebook.
    If the AI call fails, returns the raw text as a fallback.
    """
    band = _grade_band(grade_level)
    band_config = _GRADE_BANDS[band]

    title_line = ""
    if title_hint:
        title_line = f'The note title should be: "{title_hint}"\n'

    prompt = f"""You are creating a study note for {band_config['label']}.

{title_line}{untrusted_document_text(raw_text, limit=15000)}

Your task: Transform this material into a clean, well-structured study note.

FORMATTING RULES:
- Start with a clear, descriptive title as a heading (# Title)
- Organize content under topic headings (## Section)
- Use bullet points for lists of facts or steps
- Define key terms in bold on first use: **Term**: definition
- End with a **Summary** section (3-5 bullet points covering the essentials)
- {band_config['instructions']}

QUALITY RULES:
- Do NOT invent information not present in the source material
- Do NOT include an introduction like "Here are your notes" — start directly with the title
- Every section heading should be specific (not "Section 1" but "How Photosynthesis Works")
- The note should feel like it was written by a helpful tutor, not a textbook"""

    try:
        provider = get_provider("extraction")
        result = await provider.complete(
            [
                {"role": "system", "content": f"{DOCUMENT_GUARD} You are a study note generator. Output clean markdown only — no preamble, no commentary."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
        )
        note = (result["content"] or "").strip()
        # Basic validation: the note should have at least a heading
        if note and len(note) > 100 and note.startswith("#"):
            return note
        if require_generated:
            raise RuntimeError("The summary could not be generated from this file.")
        # If the response looks malformed, fall back to raw text
        return _fallback_note(raw_text, title_hint)
    except Exception:
        if require_generated:
            raise
        return _fallback_note(raw_text, title_hint)


def _fallback_note(raw_text: str, title_hint: str | None = None) -> str:
    """Create a minimal structured note from raw text when AI generation fails."""
    title = title_hint or "Untitled Note"
    # Truncate to a reasonable length
    content = raw_text[:5000].strip()
    return f"# {title}\n\n{content}\n\n---\n*Note: This is the original text. The formatted version could not be generated right now.*"
