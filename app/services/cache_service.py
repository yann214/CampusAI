"""
Cache sémantique — évite de rappeler Groq quand une question très proche
d'une question déjà posée arrive. Utilise sa propre collection ChromaDB
(distincte de la base de connaissances) pour stocker question -> réponse.

Pourquoi c'est utile ici :
- Réduit la consommation du quota gratuit Groq
- Réponse quasi instantanée sur les questions fréquentes
  ("quelles filières après un bac scientifique ?" revient souvent)
"""

from pathlib import Path

import chromadb

from app.config import get_settings

settings = get_settings()


class CacheService:
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
            self._collection = client.get_or_create_collection(
                name=settings.cache_collection_name,
                metadata={"hnsw:space": "cosine"},
            )
        return self._collection

    def lookup(self, query_embedding: list[float]) -> dict | None:
        """
        Cherche une question déjà en cache suffisamment proche.
        Retourne {"answer": str, "model_used": str, "sources": list} ou None.
        """
        if not settings.cache_enabled:
            return None

        collection = self._get_collection()
        if collection.count() == 0:
            return None

        results = collection.query(query_embeddings=[query_embedding], n_results=1)

        distances = results.get("distances", [[]])[0]
        if not distances:
            return None

        similarity = 1 - distances[0]
        if similarity < settings.cache_similarity_threshold:
            return None

        metadata = results["metadatas"][0][0]
        import json

        return {
            "answer": metadata["answer"],
            "model_used": metadata["model_used"],
            "sources": json.loads(metadata["sources"]),
            "suggested_questions": json.loads(metadata.get("suggested_questions", "[]")),
            "similarity": round(similarity, 4),
        }

    def store(
        self,
        question: str,
        question_embedding: list[float],
        answer: str,
        model_used: str,
        sources: list[dict],
        suggested_questions: list[str] | None = None,
    ):
        """Sauvegarde une question/réponse pour réutilisation future."""
        if not settings.cache_enabled:
            return

        import json
        import hashlib

        collection = self._get_collection()
        cache_id = hashlib.sha256(question.encode("utf-8")).hexdigest()[:16]

        collection.add(
            ids=[cache_id],
            embeddings=[question_embedding],
            documents=[question],
            metadatas=[
                {
                    "answer": answer,
                    "model_used": model_used,
                    "sources": json.dumps(sources),
                    "suggested_questions": json.dumps(suggested_questions or []),
                }
            ],
        )

    def clear(self):
        """Vide le cache — utile après une réingestion des documents."""
        client = self._get_client()
        try:
            client.delete_collection(settings.cache_collection_name)
        except Exception:
            pass
        self._collection = None


cache_service = CacheService()