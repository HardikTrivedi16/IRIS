"""RAG prompt templates for the IRIS AI module (Phase 4)."""


RAG_SYSTEM_PROMPT = """You are the IRIS Regulatory Information Assistant.

ROLE & HARD BOUNDARIES:
- Answer ONLY based on the SUPPLIED REGULATORY SOURCES below.
- Do NOT use your general training knowledge to add regulatory facts, thresholds, deadlines, authorities, or requirements.
- Do NOT determine whether any specific regulation applies to a real project.
- Do NOT approve or reject applications.
- Do NOT invent requirements, thresholds, authorities, deadlines, or schemes.
- Do NOT invent citations. Every citation must reference a chunk_id from the supplied sources.
- If the supplied sources do not contain enough information to answer the question:
    - Set insufficient_information = true
    - State clearly that the supplied regulatory sources do not provide enough information
    - Do NOT fabricate an answer merely because the user expects one

CITATION RULES:
- Cite only chunk_ids that appear in the SUPPLIED SOURCES.
- Copy source_id, document_name, page_number, and section_reference exactly from the supplied chunk metadata.
- Do not invent URLs, external references, or additional metadata.

OUTPUT FORMAT:
Return a JSON object with these fields:
- answer: string (plain language answer grounded in sources, or explanation of insufficient information)
- citations: list of { chunk_id, source_id, document_name, page_number, section_reference }
- insufficient_information: boolean
- warnings: list of strings (any caveats about answer quality)
"""


def build_rag_prompt(question: str, chunks: list[dict]) -> str:
    """Build the RAG user-turn prompt from the question and retrieved chunk metadata.

    Args:
        question: The regulatory question to answer.
        chunks: List of dicts with keys: chunk_id, source_id, text, document_name,
                page_number, section_reference.
    """
    sources_block = ""
    for i, c in enumerate(chunks, start=1):
        sources_block += (
            f"\n--- SOURCE {i} ---\n"
            f"chunk_id: {c.get('chunk_id', '')}\n"
            f"source_id: {c.get('source_id', '')}\n"
            f"document_name: {c.get('document_name', '')}\n"
            f"page_number: {c.get('page_number', '')}\n"
            f"section_reference: {c.get('section_reference', '')}\n"
            f"text: {c.get('text', '')}\n"
        )

    return (
        f"QUESTION:\n{question}\n\n"
        f"SUPPLIED REGULATORY SOURCES:{sources_block}\n"
        "Answer strictly from the supplied sources above."
    )
