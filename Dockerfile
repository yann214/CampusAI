# syntax=docker/dockerfile:1
# Image unique pour l'API complète : RAG orientation (/ask) + chat documents (/documents/chat)
# Les deux modules vivent dans le même package `app/`, donc un seul Dockerfile suffit.

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Dépendances système :
# - build-essential : compilation de certaines roues (tokenizers, etc.)
# - libgomp1        : requis par onnxruntime (dépendance transitive de chromadb)
# - curl            : utilisé par le HEALTHCHECK
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Utilisateur non-root, bonne pratique générale (et requis par certaines
# plateformes comme Hugging Face Spaces, qui s'attendent à l'UID 1000).
RUN useradd -m -u 1000 user

WORKDIR /app

# Étape séparée pour profiter du cache Docker : les dépendances ne sont
# réinstallées que si requirements.txt change.
# IMPORTANT : requirements.txt doit épingler torch en version CPU-only
# (--extra-index-url https://download.pytorch.org/whl/cpu) tout en haut du
# fichier, sinon pip installe par défaut la version CUDA de torch, ce qui
# fait exploser la taille de l'image (observé à 8 Go+ sans ce correctif).
COPY --chown=user requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copie du code applicatif (app/, scripts/, data/urls.txt, .env.example, etc.)
# Assure-toi qu'un .dockerignore exclut .git/, venv/, __pycache__/ et
# data/vectorstore/ pour ne pas gonfler le contexte de build inutilement.
COPY --chown=user . .

# Dossiers nécessaires aux deux modules, créés même s'ils sont vides côté
# dépôt (data/vectorstore et data/processed sont générés par l'ingestion ;
# data/files est la racine des documents téléchargeables du module chat).
RUN mkdir -p data/vectorstore data/processed data/files data/documents data/database

USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

# Port par défaut 7860 (convention Hugging Face Spaces). Render et Fly.io
# injectent leur propre port via $PORT ou fly.toml (internal_port) :
# - Render : lit automatiquement $PORT, pas de configuration supplémentaire.
# - Fly.io : ne définit PAS $PORT — fixe internal_port dans fly.toml à la
#   même valeur que celle utilisée ici (7860 par défaut).
EXPOSE 7860
ENV PORT=7860

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:${PORT}/api/v1/health || exit 1

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-7860}"]
