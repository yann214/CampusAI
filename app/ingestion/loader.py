"""
Charge les documents bruts depuis data/documents/.
Formats supportés pour l'instant : .txt, .md, .pdf
"""

from pathlib import Path
from dataclasses import dataclass


@dataclass
class RawDocument:
    content: str
    source: str  # nom du fichier, utile pour citer les sources dans les réponses


def _load_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _load_pdf_file(path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    pages_text = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(pages_text)


LOADERS = {
    ".txt": _load_text_file,
    ".md": _load_text_file,
    ".pdf": _load_pdf_file,
}


def load_documents(directory: str | Path) -> list[RawDocument]:
    """Parcourt le dossier et charge tous les fichiers supportés."""
    directory = Path(directory)
    documents = []

    for path in sorted(directory.glob("*")):
        if path.suffix.lower() not in LOADERS:
            continue

        loader = LOADERS[path.suffix.lower()]
        try:
            content = loader(path).strip()
        except Exception as e:
            print(f"⚠️  Impossible de charger {path.name} : {e}")
            continue

        if not content:
            print(f"⚠️  {path.name} est vide, ignoré.")
            continue

        documents.append(RawDocument(content=content, source=path.name))

    return documents
