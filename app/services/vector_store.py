"""
Service de base vectorielle — ChromaDB en mode persistant (fichiers locaux,
pas de serveur à héberger, 100% gratuit).

Deux usages :
1. Indexation (appelée par le script d'indexation, une fois après l'ingestion)
2. Recherche par similarité (appelée par le RAGService à chaque question)
"""

from pathlib import Path

import chromadb

from app.config import get_settings

settings = get_settings()


class VectorStoreService:
    def __init__(self):
        self._client = None
        self._collection = None

    def _get_client(self):
        if self._client is None:
            Path(settings.vectorstore_path).mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(path=settings.vectorstore_path)
        return self._client

    def _get_collection(self):
        if self._collection is None:
            client = self._get_client()
            # get_or_create_collection : ne casse rien si la collection existe déjà
            self._collection = client.get_or_create_collection(
                name=settings.collection_name,
                metadata={"hnsw:space": "cosine"},  # cohérent avec normalize_embeddings=True
            )
        return self._collection

    def is_ready(self) -> bool:
        """Utilisé par /health pour vérifier que la base contient des données."""
        try:
            collection = self._get_collection()
            return collection.count() > 0
        except Exception:
            return False

    def count(self) -> int:
        return self._get_collection().count()

    def reset(self):
        """Supprime la collection existante (utile avant une réindexation complète)."""
        client = self._get_client()
        try:
            client.delete_collection(settings.collection_name)
        except Exception:
            pass
        self._collection = None  # forcera une recréation propre au prochain appel

    def add_chunks(self, chunks: list[dict], batch_size: int = 500):
        """
        Insère des chunks déjà embeddés dans la collection.
        Chaque chunk doit avoir : id, content, embedding, source.
        Traité par lots pour rester robuste sur de gros volumes.
        """
        collection = self._get_collection()

        for i in range(0, len(chunks), batch_size):
            batch = chunks[i : i + batch_size]
            collection.add(
                ids=[c["id"] for c in batch],
                embeddings=[c["embedding"] for c in batch],
                documents=[c["content"] for c in batch],
                metadatas=[{"source": c["source"]} for c in batch],
            )

    def search(self, query_embedding: list[float], top_k: int | None = None) -> list[dict]:
        """
        Recherche par similarité. Retourne une liste de dicts :
        {content, source, score} triés du plus au moins pertinent.
        """
        collection = self._get_collection()
        top_k = top_k or settings.retrieval_top_k

        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
        )

        matches = []
        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        for content, metadata, distance in zip(documents, metadatas, distances):
            matches.append(
                {
                    "content": content,
                    "source": metadata.get("source", "inconnu"),
                    # distance cosinus -> score de similarité (1 = identique, 0 = opposé)
                    "score": round(1 - distance, 4),
                }
            )

        return matches


vector_store_service = VectorStoreService()
