# RAG Orientation API

API de RAG (Retrieval-Augmented Generation) pour l'orientation des étudiants,
propulsée par des documents indexés (filières, débouchés, admissions) et
le LLM open source Llama via l'API gratuite Groq.

📘 **Pour l'équipe frontend** : voir [`API_DOCUMENTATION.md`](./API_DOCUMENTATION.md)
pour la documentation complète des endpoints, avec exemples de code
(JavaScript, React, Python) et gestion des erreurs.

## Statut du projet

- [x] Étape 1 — Structure du projet FastAPI
- [x] Étape 2 — Pipeline d'ingestion des documents (fichiers, web, SQL/MySQL)
- [x] Étape 3 — Base vectorielle (ChromaDB)
- [x] Étape 4 — Service LLM (Groq)
- [x] Étape 5 — Service RAG complet
- [x] Étape 6 — Routes API finales
- [x] Étape 7 — Robustesse (cache sémantique, rate limiting, erreurs 503/500)
- [x] Étape 8 — Tests (54 tests automatisés, `pytest`)
- [x] Étape 9 — Documentation API
- [ ] Étape 10 — Déploiement
- [ ] Étape 11 — Livraison au frontend

## Installation

```bash
python -m venv venv
source venv/bin/activate  # Windows : venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env
# Remplir GROQ_API_KEY dans .env
```

## Lancer le serveur en local

```bash
uvicorn app.main:app --reload
```

L'API est alors disponible sur `http://localhost:8000`, avec la doc
interactive Swagger sur `http://localhost:8000/docs`.

## Structure du projet

```
rag-orientation-api/
├── app/
│   ├── main.py               # Point d'entrée FastAPI
│   ├── config.py              # Configuration centralisée (.env)
│   ├── rate_limiter.py         # Instance partagée du rate limiter
│   ├── api/
│   │   └── routes.py           # Routes exposées au frontend
│   ├── services/
│   │   ├── rag_service.py       # Orchestration RAG (retrieval + génération)
│   │   ├── embedding_service.py # Génération des embeddings (sentence-transformers)
│   │   ├── vector_store.py      # Base vectorielle ChromaDB
│   │   ├── llm_service.py       # Appel Groq (avec fallback + retry)
│   │   └── cache_service.py     # Cache sémantique des questions/réponses
│   ├── models/
│   │   └── schemas.py            # Contrats de requête/réponse (Pydantic)
│   └── ingestion/
│       ├── loader.py              # Chargement fichiers locaux (txt/md/pdf)
│       ├── web_loader.py          # Scraping de pages web
│       ├── sql_loader.py          # Ingestion depuis dump SQL/MySQL ou SQLite
│       ├── splitter.py            # Découpage en chunks
│       ├── ingest.py              # Script orchestrateur (étape 2)
│       └── index_chunks.py         # Script d'indexation dans ChromaDB (étape 3)
├── tests/                      # Suite de tests pytest (54 tests)
├── data/
│   ├── documents/               # Documents sources bruts
│   ├── database/                 # Dumps SQL / bases SQLite sources
│   ├── urls.txt                   # Liste des pages web à scraper
│   ├── processed/                 # chunks.json généré par l'ingestion
│   └── vectorstore/                # Base vectorielle ChromaDB (générée)
├── API_DOCUMENTATION.md         # Documentation API pour le frontend
├── requirements.txt
├── pytest.ini
└── .env.example
```

## Endpoints actuels

| Méthode | Route | Description |
|---|---|---|
| GET | `/` | Statut général |
| GET | `/api/v1/health` | Health check (inclut l'état de la base vectorielle) |
| POST | `/api/v1/ask` | Poser une question d'orientation — RAG complet (recherche + génération + cache) |

Voir [`API_DOCUMENTATION.md`](./API_DOCUMENTATION.md) pour le détail complet
(schémas de requête/réponse, codes d'erreur, exemples de code).

## Lancer les tests

```bash
pytest
```
