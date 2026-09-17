"""
Script d'indexation — à lancer après chaque ingestion (étape 2) pour
mettre à jour la base vectorielle ChromaDB.

Usage :
    python -m app.ingestion.index_chunks
    python -m app.ingestion.index_chunks --reset   # réindexation complète
"""

import json
import sys
from pathlib import Path

from app.services.vector_store import vector_store_service

CHUNKS_FILE = Path("data/processed/chunks.json")


def run_indexing(reset: bool = False):
    if not CHUNKS_FILE.exists():
        print(
            f"❌ {CHUNKS_FILE} introuvable. Lance d'abord l'ingestion :\n"
            f"   python -m app.ingestion.ingest"
        )
        return

    with open(CHUNKS_FILE, encoding="utf-8") as f:
        data = json.load(f)

    chunks = data.get("chunks", [])
    if not chunks:
        print("❌ Aucun chunk trouvé dans le fichier. Rien à indexer.")
        return

    print(f"📦 {len(chunks)} chunk(s) trouvé(s) dans {CHUNKS_FILE}")
    print(f"   (générés avec le modèle : {data.get('embedding_model', 'inconnu')})")

    if reset:
        print("🗑️  Suppression de la collection existante (réindexation complète)...")
        vector_store_service.reset()

    print("🧠 Indexation dans ChromaDB en cours...")
    vector_store_service.add_chunks(chunks)

    total = vector_store_service.count()
    print(f"✅ Indexation terminée. La collection contient maintenant {total} chunk(s) au total.")
    print("✅ Prêt pour l'étape 4 (intégration du LLM Groq).")


if __name__ == "__main__":
    reset_flag = "--reset" in sys.argv
    run_indexing(reset=reset_flag)
