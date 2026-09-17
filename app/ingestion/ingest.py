"""
Script d'ingestion — à lancer chaque fois que les documents sources changent.

Usage :
    python -m app.ingestion.ingest

Ce script :
1. Charge tous les documents dans data/documents/
2. Les découpe en chunks
3. Génère les embeddings de chaque chunk
4. Sauvegarde le résultat dans data/processed/chunks.json
   (sera injecté dans ChromaDB à l'étape 3 de la roadmap)
"""

import json
from pathlib import Path
from datetime import datetime, timezone

from app.config import get_settings
from app.ingestion.loader import load_documents
from app.ingestion.web_loader import load_urls_from_file
from app.ingestion.sql_loader import load_all_sql_sources
from app.ingestion.splitter import chunk_text
from app.services.embedding_service import embedding_service

settings = get_settings()

DOCUMENTS_DIR = Path("data/documents")
URLS_FILE = Path("data/urls.txt")
DATABASE_DIR = Path("data/database")
PROCESSED_DIR = Path("data/processed")
OUTPUT_FILE = PROCESSED_DIR / "chunks.json"


def run_ingestion():
    print(f"📂 Lecture des documents depuis {DOCUMENTS_DIR}/ ...")
    documents = load_documents(DOCUMENTS_DIR)
    print(f"✅ {len(documents)} document(s) local(aux) chargé(s) : {[d.source for d in documents]}")

    if URLS_FILE.exists():
        web_documents = load_urls_from_file(str(URLS_FILE))
        print(f"✅ {len(web_documents)} page(s) web chargée(s) avec succès.")
        documents.extend(web_documents)

    sql_documents = load_all_sql_sources(
        DATABASE_DIR,
        included_tables=settings.sql_included_tables,
        excluded_tables=settings.sql_excluded_tables,
    )
    if sql_documents:
        print(f"✅ {len(sql_documents)} enregistrement(s) chargé(s) depuis {DATABASE_DIR}/")
        documents.extend(sql_documents)

    if not documents:
        print(
            "❌ Aucun document trouvé. Ajoute des fichiers .txt/.md/.pdf dans "
            "data/documents/, des URLs dans data/urls.txt, et/ou un dump SQL "
            "dans data/database/"
        )
        return

    all_chunks = []
    for doc in documents:
        pieces = chunk_text(doc.content)
        for i, piece in enumerate(pieces):
            all_chunks.append(
                {
                    "id": f"{doc.source}-{i}",
                    "content": piece,
                    "source": doc.source,
                }
            )

    print(f"✂️  {len(all_chunks)} chunk(s) généré(s) au total.")

    print(f"🧠 Génération des embeddings avec '{settings.embedding_model_name}' ...")
    texts = [c["content"] for c in all_chunks]
    embeddings = embedding_service.embed_texts(texts)

    for chunk, embedding in zip(all_chunks, embeddings):
        chunk["embedding"] = embedding

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "embedding_model": settings.embedding_model_name,
                "chunk_count": len(all_chunks),
                "chunks": all_chunks,
            },
            f,
            ensure_ascii=False,
        )

    print(f"💾 Résultat sauvegardé dans {OUTPUT_FILE}")
    print("✅ Ingestion terminée. Prêt pour l'étape 3 (indexation dans ChromaDB).")


if __name__ == "__main__":
    run_ingestion()