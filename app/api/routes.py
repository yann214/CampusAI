"""
Routes exposées au frontend.
"""

from fastapi import APIRouter, HTTPException, Request

from app.models.schemas import AskRequest, AskResponse, HealthResponse
from app.services.rag_service import rag_service
from app.services.vector_store import vector_store_service
from app.config import get_settings
from app.rate_limiter import limiter

router = APIRouter()
settings = get_settings()


@router.get("/health", response_model=HealthResponse, tags=["Système"])
async def health_check():
    """Vérifie que l'API est en ligne. Utile pour le monitoring et le déploiement."""
    return HealthResponse(
        status="ok",
        environment=settings.environment,
        vectorstore_ready=vector_store_service.is_ready(),
    )


@router.post("/ask", response_model=AskResponse, tags=["Orientation"])
@limiter.limit(settings.rate_limit_ask)
async def ask_question(request: Request, payload: AskRequest):
    """
    Reçoit une question d'un étudiant et retourne une réponse
    générée à partir des documents d'orientation indexés.
    """
    try:
        return await rag_service.answer(payload.question)
    except RuntimeError as e:
        # RuntimeError = échec du LLM (Groq indisponible/quota dépassé sur
        # les deux modèles) : problème temporaire côté fournisseur, pas un
        # bug de l'API -> 503 Service Unavailable plutôt que 500.
        raise HTTPException(
            status_code=503,
            detail=f"Le service de génération est temporairement indisponible : {str(e)}",
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Erreur lors du traitement de la question : {str(e)}",
        )