---
title: RAG Orientation API
emoji: 🎓
colorFrom: blue
colorTo: green
sdk: docker
app_port: 7860
pinned: false
---

# RAG Orientation API

API de RAG (Retrieval-Augmented Generation) pour l'orientation des étudiants.
Elle répond à des questions (filières, débouchés, conditions d'admission...)
en s'appuyant sur une base de connaissances construite à partir de tes
propres documents, pages web et données SQL, puis génère la réponse avec un
LLM open source (Llama/GPT-OSS) via l'API gratuite **Groq**.

Ce README couvre l'exécution complète du projet, de l'installation jusqu'à
une API qui répond à de vraies questions. Pour le détail de chaque décision
technique, voir aussi `API_DOCUMENTATION.md` (contrat API pour le frontend)
et `DEPLOYMENT.md` (déploiement sur Hugging Face Spaces).

---

## 1. Vue d'ensemble de l'architecture

```
Documents (txt/md/pdf) ─┐
Pages web (scraping)    ├─► Ingestion ─► Chunking ─► Embeddings ─► ChromaDB
Dump SQL / MySQL        ┘                                             │
                                                                       │
Question de l'étudiant ─► Embedding ─► Recherche ChromaDB ────────────┘
                                              │
                                       Contexte pertinent
                                              │
                                              ▼
                                    Groq (LLM open source)
                                              │
                                              ▼
                          Réponse + sources + questions suggérées
```

- **Embeddings** : générés localement avec `sentence-transformers` (gratuit, pas d'API)
- **Base vectorielle** : ChromaDB, stockage local sur disque (gratuit, pas de serveur)
- **LLM** : Groq (API gratuite, modèles open source `openai/gpt-oss-120b` / `openai/gpt-oss-20b`)
- **Cache sémantique** : évite de rappeler Groq pour des questions déjà posées
- **Rate limiting** : protège le quota gratuit contre les abus

---

## 2. Prérequis

- Python 3.11 ou plus récent
- Un compte Groq gratuit (sans carte bancaire) : [console.groq.com](https://console.groq.com) → génère une clé API
- (Optionnel) Docker, si tu veux tester le build avant un déploiement

---

## 3. Installation

```bash
git clone <url-de-ton-repo>
cd rag-orientation-api

python -m venv venv
source venv/bin/activate          # Windows : venv\Scripts\activate

pip install -r requirements-dev.txt   # inclut requirements.txt + pytest
# En production uniquement (pas besoin de pytest) : pip install -r requirements.txt
```

---

## 4. Configuration

```bash
cp .env.example .env
```

Ouvre `.env` et renseigne au minimum :

```env
GROQ_API_KEY=gsk_...   # récupérée sur console.groq.com
```

Les autres variables ont des valeurs par défaut raisonnables (modèles Groq,
seuil du cache, rate limiting...) — voir les commentaires dans `.env.example`
si tu veux les ajuster.

---

## 5. Mettre en place la base de connaissances (le RAG)

C'est l'étape centrale : sans elle, l'API répond mais sans aucune
information réelle sur les filières/universités. Trois sources sont
supportées, combinables librement.

### 5.1 Ajouter des documents locaux (optionnel)

Dépose des fichiers `.txt`, `.md` ou `.pdf` dans :

```bash
data/documents/
```

### 5.2 Ajouter des pages web à scraper (optionnel)

Édite `data/urls.txt` et ajoute une URL par ligne :

```
https://www.exemple-universite.fr/filieres/informatique
https://www.exemple-ministere.gouv/orientation/apres-le-bac
```

### 5.3 Ajouter une base SQL (optionnel)

Dépose un dump `.sql` (MySQL ou SQLite) ou un fichier `.db`/`.sqlite` dans :

```bash
data/database/
```

Un dump MySQL classique (`mysqldump`/phpMyAdmin) est automatiquement
converti au format SQLite (gestion de `ENGINE=`, `AUTO_INCREMENT`, `ENUM`,
apostrophes échappées, etc. — voir `app/ingestion/sql_loader.py`).

Pour exclure certaines tables (comptes utilisateurs, caches internes...),
édite dans `.env` :
```env
SQL_EXCLUDED_TABLES=["ai_cache","users"]
```

### 5.4 Lancer l'ingestion

Charge toutes les sources ci-dessus, les découpe en chunks et génère les
embeddings :

```bash
python -m app.ingestion.ingest
```

Résultat : `data/processed/chunks.json`.

### 5.5 Indexer dans la base vectorielle

```bash
python -m app.ingestion.index_chunks
```

Pour repartir de zéro (après une modification des documents sources) :
```bash
python -m app.ingestion.index_chunks --reset
```

Résultat : `data/vectorstore/` contient la base ChromaDB prête à interroger.

### 5.6 Mettre à jour la base plus tard

Dès que les documents/URLs/dump SQL changent, relance simplement les
étapes 5.4 et 5.5 :
```bash
python -m app.ingestion.ingest
python -m app.ingestion.index_chunks --reset
```

---

## 6. Lancer l'API en local

```bash
uvicorn app.main:app --reload
```

- API disponible sur `http://localhost:8000`
- Documentation interactive Swagger : `http://localhost:8000/docs`

### Vérifier que tout est prêt

```bash
curl http://localhost:8000/api/v1/health
```

`vectorstore_ready` doit être à `true` — sinon, l'étape 5 n'a pas été
complétée (ou `index_chunks` n'a pas été lancé).

### Poser une vraie question

```bash
curl -X POST http://localhost:8000/api/v1/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "Quelles filières après un bac scientifique ?"}'
```

Voir `API_DOCUMENTATION.md` pour le détail complet du contrat API
(schémas, codes d'erreur, exemples JavaScript/React/Python).

---

## 7. Lancer les tests automatisés

```bash
pytest
```

59 tests couvrant l'ingestion, le RAG, le cache, le rate limiting et les
routes API — aucune vraie clé Groq ni téléchargement de modèle requis (tout
est simulé). À relancer après chaque modification du code.

---

## 8. Déploiement

Le projet est prêt pour un déploiement gratuit sur **Hugging Face Spaces**
(SDK Docker). Procédure complète, y compris la particularité du stockage
non persistant en tier gratuit : voir **`DEPLOYMENT.md`**.

Résumé ultra-rapide :
```bash
# 1. Base de connaissances à jour en local (voir section 5)
# 2. Forcer l'ajout malgré le .gitignore (nécessaire pour le tier gratuit)
git add -f data/vectorstore/ data/processed/chunks.json
git add .
git commit -m "Déploiement"
git push space main
```

---

## 9. Structure du projet

```
rag-orientation-api/
├── app/
│   ├── main.py                  # Point d'entrée FastAPI
│   ├── config.py                 # Configuration centralisée (.env)
│   ├── rate_limiter.py            # Instance partagée du rate limiter
│   ├── api/
│   │   └── routes.py               # Routes exposées au frontend
│   ├── services/
│   │   ├── rag_service.py           # Orchestration RAG (retrieval + génération)
│   │   ├── embedding_service.py     # Embeddings (sentence-transformers)
│   │   ├── vector_store.py          # Base vectorielle ChromaDB
│   │   ├── llm_service.py           # Appel Groq (JSON mode, fallback, retry)
│   │   └── cache_service.py         # Cache sémantique des questions/réponses
│   ├── models/
│   │   └── schemas.py                # Contrats de requête/réponse (Pydantic)
│   └── ingestion/
│       ├── loader.py                  # Fichiers locaux (txt/md/pdf)
│       ├── web_loader.py              # Scraping de pages web
│       ├── sql_loader.py              # Dump SQL/MySQL ou SQLite
│       ├── splitter.py                # Découpage en chunks
│       ├── ingest.py                  # Script d'ingestion (section 5.4)
│       └── index_chunks.py             # Script d'indexation (section 5.5)
├── tests/                          # Suite pytest (59 tests)
├── data/
│   ├── documents/                   # Documents sources bruts
│   ├── database/                     # Dumps SQL / bases SQLite sources
│   ├── urls.txt                       # URLs à scraper
│   ├── processed/                     # chunks.json (généré)
│   └── vectorstore/                    # Base ChromaDB (générée)
├── Dockerfile                      # Build pour Hugging Face Spaces
├── API_DOCUMENTATION.md            # Contrat API pour le frontend
├── DEPLOYMENT.md                   # Guide de déploiement HF Spaces
├── requirements.txt                 # Dépendances de production
├── requirements-dev.txt             # + pytest, httpx (dev/tests)
├── pytest.ini
├── .env.example
└── .dockerignore
```

---

## 10. Endpoints principaux

| Méthode | Route | Description |
|---|---|---|
| GET | `/` | Statut général |
| GET | `/api/v1/health` | Health check (inclut l'état de la base vectorielle) |
| POST | `/api/v1/ask` | Question d'orientation — RAG complet (recherche + génération + suggestions + cache) |

Détail complet (schémas, codes d'erreur 422/429/503/500, exemples de code
frontend) : voir **`API_DOCUMENTATION.md`**.

---

## 11. Dépannage rapide

| Symptôme | Cause probable / solution |
|---|---|
| `vectorstore_ready: false` | L'étape 5 (ingestion + indexation) n'a pas été faite. Relance section 5.4 et 5.5. |
| `503` sur `/ask` | `GROQ_API_KEY` manquante/invalide dans `.env`, ou modèle Groq indisponible (vérifie `console.groq.com/docs/deprecations`). |
| Erreur au chargement d'un dump SQL | Regarde le fichier `*.sanitized.sql` généré à côté du dump en cas d'échec — il montre le script après nettoyage automatique, utile pour diagnostiquer une syntaxe MySQL non gérée. |
| `ModuleNotFoundError` (slowapi, chromadb...) | Dépendances non installées : `pip install -r requirements-dev.txt`. Si ça fonctionne en ligne de commande mais que l'éditeur souligne toujours l'erreur, redémarre le serveur de langage (Pylance) ou vérifie l'interpréteur Python sélectionné. |
| `429 Too Many Requests` | Rate limiting déclenché (protection du quota Groq). Ajustable via `RATE_LIMIT_ASK` dans `.env`. |
| Le Space Hugging Face répond avec une base vide | La base vectorielle n'a pas été commitée avec `git add -f` avant le push (voir `DEPLOYMENT.md`, section stockage non persistant). |

---

## 12. Statut du projet

- [x] Structure du projet FastAPI
- [x] Pipeline d'ingestion (fichiers, web, SQL/MySQL)
- [x] Base vectorielle (ChromaDB)
- [x] Service LLM (Groq, avec fallback et suggestions de questions)
- [x] Service RAG complet
- [x] Routes API finales
- [x] Robustesse (cache sémantique, rate limiting, erreurs 503/500)
- [x] Tests (59 tests automatisés, `pytest`)
- [x] Documentation API (`API_DOCUMENTATION.md`)
- [x] Déploiement (Hugging Face Spaces, `DEPLOYMENT.md`)
- [ ] Livraison finale au frontend