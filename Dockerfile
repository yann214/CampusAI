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

# Hugging Face Spaces exécute le conteneur avec l'UID 1000 : on crée cet
# utilisateur dès maintenant pour éviter les soucis de permissions au runtime.
RUN useradd -m -u 1000 user

WORKDIR /app

# Étape séparée pour profiter du cache Docker : les dépendances ne sont
# réinstallées que si requirements.txt change.
COPY --chown=user requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copie du code applicatif (app/, scripts/, data/urls.txt, .env.example, etc.)
COPY --chown=user . .

# Dossiers nécessaires aux deux modules, créés même s'ils sont vides côté
# dépôt (data/vectorstore et data/processed sont générés par l'ingestion ;
# data/files est la racine des documents téléchargeables du module chat).
RUN mkdir -p data/vectorstore data/processed data/files data/documents data/database

USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

EXPOSE 7860

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:7860/api/v1/health || exit 1

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-7860}"]
