"""
Service RAG — orchestre le retrieval (base vectorielle) et la génération (LLM).

Flux complet :
1. La question de l'étudiant est transformée en vecteur (embedding)
2. On cherche les chunks les plus proches dans ChromaDB
3. Ces chunks forment le contexte envoyé au LLM
4. Groq génère la réponse à partir de ce contexte
5. On renvoie la réponse + les sources utilisées (traçabilité)
"""

import asyncio

from app.models.schemas import AskResponse, SourceChunk
from app.services.embedding_service import embedding_service
from app.services.vector_store import vector_store_service
from app.services.llm_service import llm_service
from app.services.cache_service import cache_service
from app.config import get_settings

settings = get_settings()


class RAGService:
    async def answer(self, question: str) -> AskResponse:
        # Les appels aux modèles/à la base sont bloquants (CPU ou réseau) :
        # on les pousse dans un thread pour ne pas geler le event loop FastAPI.
        query_embedding = await asyncio.to_thread(embedding_service.embed_query, question)

        # 1. Vérifie le cache sémantique avant tout appel coûteux
        cached = await asyncio.to_thread(cache_service.lookup, query_embedding)
        if cached:
            print(f"⚡ Réponse servie depuis le cache (similarité : {cached['similarity']})")
            sources = [SourceChunk(**s) for s in cached["sources"]]
            return AskResponse(
                answer=cached["answer"],
                sources=sources,
                suggested_questions=cached.get("suggested_questions", []),
                model_used=cached["model_used"],
                cached=True,
            )

        # 2. Sinon, flux RAG classique
        matches = await asyncio.to_thread(vector_store_service.search, query_embedding)
        context = self._build_context(matches)
        result = await asyncio.to_thread(llm_service.generate, question, context)

        sources = [
            SourceChunk(content=m["content"], source=m["source"], score=m["score"])
            for m in matches
        ]

        # 3. Sauvegarde pour les prochaines questions similaires
        await asyncio.to_thread(
            cache_service.store,
            question,
            query_embedding,
            result["answer"],
            result["model_used"],
            [s.model_dump() for s in sources],
            result.get("suggested_questions", []),
        )

        return AskResponse(
            answer=result["answer"],
            sources=sources,
            suggested_questions=result.get("suggested_questions", []),
            model_used=result["model_used"],
            cached=False,
        )

    def _build_context(self, matches: list[dict]) -> str:
        """Assemble les chunks trouvés en un contexte lisible pour le prompt."""
        if not matches:
            return ""

        parts = [
            f"[Extrait {i} — source : {m['source']}]\n{m['content']}"
            for i, m in enumerate(matches, start=1)
        ]
        return "\n\n".join(parts)


rag_service = RAGService()