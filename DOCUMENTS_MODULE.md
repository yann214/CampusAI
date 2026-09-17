# Module `/documents/chat` — Recherche et téléchargement de documents

## Objectif

Permettre à un étudiant de demander un document en langage naturel
(« je veux le guide de l'étudiant », « donne-moi l'emploi du temps de L1 info »)
et recevoir en retour une réponse texte accompagnée d'un ou plusieurs liens
de téléchargement.

**Ce module est totalement indépendant du pipeline RAG existant** (`/api/v1/ask`).
Il ne fait pas de recherche sémantique dans le contenu des documents : il
interroge les **métadonnées** (nom, description, tags) stockées dans une
table MySQL, via un appel d'outil (*tool calling*) du modèle Groq.

| | RAG (`/ask`) | Documents (`/documents/chat`) |
|---|---|---|
| Recherche dans | le **contenu** des documents (chunks + embeddings) | les **métadonnées** des documents (nom, description, tags) |
| Stockage | ChromaDB (vecteurs) | MySQL (table `documents`) |
| But | répondre à une question | retrouver et télécharger un fichier précis |
| Sortie | une réponse rédigée | une réponse courte + liens de téléchargement |

---

## Architecture

```
Étudiant : "je veux le guide de l'étudiant"
        │
        ▼
POST /api/v1/documents/chat
        │
        ▼
DocumentChatService (app/services/document_chat_service.py)
        │  appelle Groq avec l'outil "search_documents"
        ▼
DocumentService.search_documents() (app/services/document_service.py)
        │  requête MySQL (FULLTEXT, repli en LIKE)
        ▼
Table `documents` (MySQL)
        │
        ▼
Le modèle formule une réponse courte, le backend construit les URLs
        │
        ▼
{ "reply": "...", "documents": [{ "id", "nom", "url", ... }] }
        │
        ▼
Frontend : affiche la réponse + boutons de téléchargement
        │
        ▼
GET /api/v1/documents/{id}/download
        │
        ▼
Fichier servi depuis data/files/<sous_dossier>/<fichier>
```

Le modèle **ne voit jamais** le chemin disque des fichiers, seulement leurs
métadonnées (id, nom, sous-dossier, type). Le lien de téléchargement est
toujours construit côté backend, jamais halluciné par le LLM.

---

## Fichiers ajoutés

| Fichier | Rôle |
|---|---|
| `app/db.py` | Pool de connexion MySQL (PyMySQL + DBUtils) |
| `app/services/document_service.py` | Requêtes SQL de recherche (FULLTEXT + repli LIKE) et de récupération par id |
| `app/services/document_chat_service.py` | Boucle de tool calling avec Groq, formulation de la réponse |
| `app/api/documents_routes.py` | Routes `POST /documents/chat` et `GET /documents/{id}/download` |
| `app/models/schemas.py` *(complété)* | `DocumentChatRequest`, `DocumentChatResponse`, `DocumentInfo` |
| `app/config.py` *(complété)* | Paramètres MySQL, `files_root_dir`, modèle/tokens dédiés |
| `data/database/create_table_documents.sql` | Script de création de la table `documents` |
| `scripts/sync_documents.py` | Scanne `data/files/` et insère les nouveaux fichiers en base |
| `data/files/` | Dossier racine des fichiers téléchargeables (avec sous-dossiers) |

---

## Mise en place

### 1. Créer la table MySQL

```bash
mysql -u root -p univ_douala_fs < data/database/create_table_documents.sql
```

Structure de la table :

```sql
documents (
  id, nom_original, nom_fichier, sous_dossier,
  chemin_relatif, type_fichier, description, tags, date_ajout
)
```

> `description` et `tags` sont ce qui rend la recherche pertinente. Un
> fichier ajouté sans description ne sera trouvable que par son nom exact.

### 2. Configurer l'environnement

Copier `.env.example` → `.env` et renseigner :

```env
GROQ_API_KEY=...
DOCUMENT_CHAT_MODEL=llama-3.3-70b-versatile
DOCUMENT_SEARCH_LIMIT=5

MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=...
MYSQL_DATABASE=univ_douala_fs

FILES_ROOT_DIR=./data/files
```

### 3. Installer les dépendances

```bash
pip install -r requirements.txt
```

(ajoute `PyMySQL` et `DBUtils` par rapport à l'existant)

### 4. Déposer les fichiers et synchroniser la base

```
data/files/
├── guides/
│   └── Guide-Etudiant-FS-25.pdf
├── emplois_du_temps/
│   └── EDT-L1-Informatique-S1.pdf
└── conventions/
    └── Convention-Stage-2026.docx
```

```bash
python -m scripts.sync_documents
```

Le script insère chaque nouveau fichier trouvé (le sous-dossier devient la
colonne `sous_dossier`). Les fichiers déjà en base sont ignorés (pas de
doublon, contrainte `UNIQUE` sur `chemin_relatif`).

**Étape manuelle recommandée** : après la synchro, remplir `description`
(et éventuellement `tags`) pour les documents importants directement en
base, par exemple :

```sql
UPDATE documents
SET description = 'Guide officiel de rentrée pour tous les étudiants de la Faculté des Sciences, année 2025',
    tags = 'guide, rentrée, étudiant, 2025'
WHERE nom_original = 'Guide-Etudiant-FS-25.pdf';
```

### 5. Lancer l'API

```bash
uvicorn app.main:app --reload
```

---

## Utilisation par le frontend

### Rechercher / demander un document

```
POST /api/v1/documents/chat
Content-Type: application/json

{ "message": "je veux le guide de l'étudiant" }
```

Réponse :

```json
{
  "reply": "Voici le guide de l'étudiant que vous cherchiez.",
  "documents": [
    {
      "id": 1,
      "nom": "Guide-Etudiant-FS-25.pdf",
      "sous_dossier": "guides",
      "type_fichier": "pdf",
      "url": "/api/v1/documents/1/download"
    }
  ]
}
```

- `documents` peut contenir **0** élément (rien trouvé — `reply` l'explique),
  **1** élément (correspondance claire), ou **plusieurs** (le modèle demande
  à l'étudiant de préciser — afficher les options, pas de téléchargement
  automatique).
- Le frontend affiche `reply` en texte, puis un bouton/lien de téléchargement
  par élément de `documents`, pointant directement vers `url`.

### Télécharger un document

```
GET /api/v1/documents/{id}/download
```

Renvoie le fichier en pièce jointe (`Content-Disposition: attachment`), ou :
- `404` si l'id n'existe pas en base
- `410` si l'entrée existe en base mais le fichier a disparu du disque
- `400` si le chemin résolu sort de `FILES_ROOT_DIR` (protection anti path-traversal)

---

## Points d'attention

- **Rate limiting** : la route `/documents/chat` réutilise `rate_limit_ask`
  (même limite que `/ask`). Ajuste `RATE_LIMIT_ASK` dans `.env` si besoin
  d'une limite dédiée (créer `RATE_LIMIT_DOCUMENTS` dans `config.py` le cas échéant).
- **Sécurité** : si les documents sont sensibles (dossiers étudiants,
  documents administratifs internes), ajouter une dépendance
  d'authentification sur les deux routes avant mise en production — ce
  module ne gère aucun contrôle d'accès par défaut.
- **Recherche pauvre sur peu de données** : MySQL `FULLTEXT` en mode
  `NATURAL LANGUAGE` peut renvoyer 0 résultat sur une petite table (< ~50
  lignes) ou avec des descriptions très courtes. Le service bascule
  automatiquement sur une recherche `LIKE` dans ce cas, mais pour de
  meilleurs résultats, mieux vaut soigner les champs `description`/`tags`.
- **`ai_cache`, `users`, `documents` exclues du RAG** : ces trois tables ont
  été ajoutées à `sql_excluded_tables` dans `config.py` pour ne pas être
  ré-ingérées comme contenu RAG lors du prochain `python -m app.ingestion.ingest`.
- **Le modèle ne génère jamais d'URL lui-même** : toujours vérifier en revue
  de code que `DOCUMENT_SEARCH_TOOL`/`SYSTEM_PROMPT` restent inchangés côté
  génération d'URL — c'est `documents_routes.py` seul qui construit les
  liens, à partir des `id` retournés par l'outil.

---

## Tester rapidement (sans frontend)

```bash
curl -X POST http://localhost:8000/api/v1/documents/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "je veux le guide de l'\''étudiant"}'
```

```bash
curl -OJ http://localhost:8000/api/v1/documents/1/download
```

Documentation interactive : `http://localhost:8000/docs` (section **Documents**).
