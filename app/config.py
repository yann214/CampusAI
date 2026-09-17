"""
Configuration centralisée de l'application.
Toutes les valeurs sensibles ou variables selon l'environnement
(clé API Groq, chemins, paramètres du modèle) passent par ici.
"""

from functools import lru_cache
import os

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # --- Général ---
    app_name: str = "RAG Orientation API"
    environment: str = "development"  # development | production
    api_prefix: str = "/api/v1"

    # --- Groq (LLM) ---
    # ⚠️ Ne jamais committer de vraie clé ici : mets-la uniquement dans ton .env
    # (fichier ignoré par git). Récupérable sur https://console.groq.com
    groq_api_key: str = Field(default_factory=lambda: os.getenv("GROQ_API_KEY", ""))
    groq_model: str = "openai/gpt-oss-120b"
    groq_model_fallback: str = "openai/gpt-oss-20b"
    llm_temperature: float = 0.3
    llm_max_tokens: int = 1024

    # --- Recherche de documents (route /documents/chat, indépendante du RAG) ---
    # Modèle utilisé pour l'appel d'outil (tool calling). Doit supporter les
    # tools côté Groq (llama-3.3-70b-versatile les supporte).
    document_chat_model: str = "openai/gpt-oss-120b"
    document_chat_max_tokens: int = 1024
    # Nombre de résultats maximum renvoyés par une recherche de document
    document_search_limit: int = 5

    # --- MySQL (table `documents` : métadonnées + chemin des fichiers) ---
    mysql_host: str = "localhost"
    mysql_port: int = 3306
    mysql_user: str = "root"
    mysql_password: str = ""
    mysql_database: str = "univ_douala_fs"

    # --- Fichiers téléchargeables (PDF/Word rangés par sous-dossier) ---
    # Racine sous laquelle tous les chemins enregistrés en base doivent rester
    # (vérifié à chaque téléchargement pour empêcher toute sortie de ce dossier).
    files_root_dir: str = "./data/files"

    # --- Embeddings ---
    embedding_model_name: str = "intfloat/multilingual-e5-small"

    # --- Vector store (ChromaDB) ---
    vectorstore_path: str = "./data/vectorstore"
    collection_name: str = "orientation_docs"

    # --- Ingestion SQL : filtrage des tables ---
    # Si sql_included_tables est renseigné, SEULES ces tables sont ingérées
    # (prioritaire sur sql_excluded_tables). Sinon, toutes les tables sont
    # ingérées SAUF celles listées dans sql_excluded_tables.
    # Exemple .env : SQL_EXCLUDED_TABLES=["ai_cache","users"]
    sql_included_tables: list[str] = []
    sql_excluded_tables: list[str] = ["ai_cache", "users", "documents"]

    # --- Retrieval ---
    retrieval_top_k: int = 4

    # --- Cache sémantique ---
    cache_enabled: bool = True
    cache_collection_name: str = "qa_cache"
    # Seuil de similarité cosinus au-delà duquel on considère 2 questions "identiques"
    # (0.92 = assez proche pour capter les reformulations, sans trop de faux positifs)
    cache_similarity_threshold: float = 0.92

    # --- Rate limiting (protège le quota Groq gratuit contre les abus) ---
    rate_limit_enabled: bool = True
    rate_limit_ask: str = "20/minute"

    # --- CORS (à restreindre en production avec l'URL du frontend) ---
    allowed_origins: list[str] = ["*"]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    """Permet d'injecter les settings sans les relire à chaque appel."""
    return Settings()