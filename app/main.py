"""
Point d'entrée de l'application.
Lancement en local : uvicorn app.main:app --reload
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.config import get_settings
from app.rate_limiter import limiter
from app.api.routes import router
from app.api.documents_routes import router as documents_router

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    description=(
        "API RAG pour l'orientation des étudiants, propulsée par Groq (Llama open source).\n\n"
        "Voir aussi API_DOCUMENTATION.md à la racine du projet pour la documentation "
        "complète destinée à l'équipe frontend (exemples de code, gestion des erreurs, etc.)."
    ),
    version="0.1.0",
    openapi_tags=[
        {"name": "Système", "description": "Statut et supervision de l'API."},
        {"name": "Orientation", "description": "Questions d'orientation étudiante (RAG)."},
        {"name": "Documents", "description": "Recherche et téléchargement de documents (PDF/Word)."},
    ],
)

# Rate limiting : protège le quota Groq gratuit contre les abus/bugs côté client.
# Limite définie par route dans app/api/routes.py (settings.rate_limit_ask).
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS : autorise le frontend à appeler l'API depuis un autre domaine.
# ⚠️ À restreindre à l'URL exacte du frontend en production (voir config.py).
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix=settings.api_prefix)
app.include_router(documents_router, prefix=settings.api_prefix)


@app.get("/", tags=["Système"])
async def root():
    return {
        "message": f"{settings.app_name} en ligne",
        "docs": "/docs",
    }