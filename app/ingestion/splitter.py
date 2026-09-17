"""
Découpe un texte long en chunks exploitables par le RAG.

Stratégie : découpage par phrases, regroupées jusqu'à atteindre
~chunk_size caractères, avec un chevauchement (overlap) entre chunks
consécutifs pour ne pas perdre le contexte à la frontière.
"""

import re


def _split_into_sentences(text: str) -> list[str]:
    # Découpage simple par ponctuation forte, suffisant pour du texte
    # structuré (fiches filières, descriptions de métiers, etc.)
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    return [s.strip() for s in sentences if s.strip()]


def chunk_text(
    text: str,
    chunk_size: int = 800,
    overlap: int = 150,
) -> list[str]:
    """
    Regroupe les phrases en chunks d'environ `chunk_size` caractères,
    avec `overlap` caractères de chevauchement entre chunks successifs.
    """
    sentences = _split_into_sentences(text)
    if not sentences:
        return []

    chunks = []
    current = ""

    for sentence in sentences:
        if len(current) + len(sentence) + 1 <= chunk_size:
            current = f"{current} {sentence}".strip()
        else:
            if current:
                chunks.append(current)
            # démarre le chunk suivant avec la fin du précédent (overlap)
            overlap_text = current[-overlap:] if current else ""
            current = f"{overlap_text} {sentence}".strip()

    if current:
        chunks.append(current)

    return chunks
