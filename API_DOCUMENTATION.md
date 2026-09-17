# API RAG Orientation — Documentation pour le frontend

Cette API permet de poser des questions d'orientation étudiante (filières,
débouchés, admissions...) et reçoit des réponses générées à partir d'une base
de connaissances (documents, pages web, base de données de l'université).

## Base URL

| Environnement | URL |
|---|---|
| Local (développement) | `http://localhost:8000` |
| Production | `https://<à compléter après déploiement, étape 10>` |

Toutes les routes métier sont préfixées par `/api/v1`.

## Authentification

Aucune authentification requise pour l'instant (API publique en lecture).
Un rate limiting par adresse IP protège contre les abus (voir plus bas).

## Doc interactive (Swagger)

Une fois le serveur lancé, `GET /docs` affiche une interface interactive où
chaque route peut être testée directement depuis le navigateur — pratique
pour explorer l'API sans écrire de code.

---

## Endpoints

### `GET /api/v1/health`

Vérifie que l'API est en ligne et que la base de connaissances est prête.
À appeler au démarrage du frontend, ou pour un indicateur de statut.

**Réponse `200 OK`**
```json
{
  "status": "ok",
  "environment": "production",
  "vectorstore_ready": true
}
```

- `vectorstore_ready: false` signifie que la base vectorielle est vide —
  l'ingestion/indexation (étapes 2-3 côté backend) n'a pas encore été lancée.
  Dans ce cas, `/ask` répondra mais sans aucune information pertinente.

---

### `POST /api/v1/ask`

Pose une question d'orientation et reçoit une réponse générée à partir de la
base de connaissances.

**Requête**

| Champ | Type | Requis | Description |
|---|---|---|---|
| `question` | string | oui | 3 à 1000 caractères |
| `conversation_id` | string | non | Identifiant optionnel pour lier plusieurs questions d'une session (pas encore exploité côté backend, réservé pour une future gestion de contexte conversationnel) |

```json
{
  "question": "Quelles filières sont accessibles après un bac scientifique ?"
}
```

**Réponse `200 OK`**
```json
{
  "answer": "Après un bac scientifique, plusieurs filières s'offrent à toi : les classes préparatoires (CPGE), la licence de sciences, le BUT, ou encore les écoles d'ingénieurs post-bac...",
  "sources": [
    {
      "content": "Les classes préparatoires aux grandes écoles (CPGE) scientifiques mènent vers les écoles d'ingénieurs...",
      "source": "exemple_filieres_bac_s.txt",
      "score": 0.87
    }
  ],
  "suggested_questions": [
    "Quelles sont les conditions d'admission en CPGE ?",
    "Quels sont les débouchés après une licence de sciences ?",
    "Quelle est la différence entre CPGE et école d'ingénieurs post-bac ?"
  ],
  "model_used": "llama-3.3-70b-versatile",
  "cached": false
}
```

| Champ | Type | Description |
|---|---|---|
| `answer` | string | La réponse générée, prête à afficher |
| `sources` | array | Les extraits de la base de connaissances utilisés pour construire la réponse — utile pour afficher "sources" ou un lien vers le document d'origine |
| `sources[].content` | string | Extrait du document source |
| `sources[].source` | string | Nom du fichier / URL / table d'origine |
| `sources[].score` | float | Score de pertinence (0 à 1, plus c'est proche de 1 plus c'est pertinent) |
| `suggested_questions` | array de string | 0 à 4 questions de suivi suggérées, pensées pour être affichées comme **boutons cliquables** sous la réponse. Cliquer sur un bouton = renvoyer cette chaîne telle quelle comme nouvelle `question` dans un appel `POST /api/v1/ask`. Peut être vide (ex: contexte insuffisant). |
| `model_used` | string | Modèle Groq ayant généré la réponse (utile pour du debug/monitoring) |
| `cached` | boolean | `true` si la réponse vient du cache sémantique (question déjà posée récemment) — instantané dans ce cas |

**Réponses d'erreur**

| Code | Signification | Ce que le frontend doit faire |
|---|---|---|
| `422` | Question invalide (vide, trop courte/longue, champ manquant) | Afficher un message de validation, ne pas réessayer automatiquement |
| `429` | Trop de requêtes envoyées trop vite (rate limit dépassé) | Attendre quelques secondes avant de réessayer, informer l'utilisateur |
| `503` | Le service de génération (Groq) est temporairement indisponible | Proposer de réessayer dans quelques instants |
| `500` | Erreur interne inattendue | Afficher un message d'erreur générique, logguer côté frontend pour investigation |

Exemple de réponse `422` :
```json
{
  "detail": [
    {
      "type": "string_too_short",
      "loc": ["body", "question"],
      "msg": "String should have at least 3 characters"
    }
  ]
}
```

Exemple de réponse `503` :
```json
{
  "detail": "Le service de génération est temporairement indisponible : Les deux modèles Groq ont échoué..."
}
```

---

## Rate limiting

`POST /api/v1/ask` est limité à **20 requêtes par minute par adresse IP**
(valeur par défaut, ajustable côté backend). Au-delà, l'API répond `429`.

Recommandation frontend : désactiver temporairement le bouton d'envoi
pendant qu'une requête est en cours, pour éviter les double-clics qui
consomment le quota inutilement.

---

## CORS

Le backend autorise les requêtes cross-origin depuis le frontend (configuré
via la variable `ALLOWED_ORIGINS` côté backend). En développement, tout est
autorisé (`*`) ; en production, seule l'URL exacte du frontend sera
autorisée — communiquer l'URL de déploiement du frontend à l'équipe backend
pour la configurer.

---

## Exemples d'intégration

### JavaScript / Fetch

```javascript
async function askOrientationQuestion(question) {
  const response = await fetch("http://localhost:8000/api/v1/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });

  if (response.status === 429) {
    throw new Error("Trop de requêtes, réessaie dans quelques secondes.");
  }
  if (response.status === 503) {
    throw new Error("Service temporairement indisponible, réessaie bientôt.");
  }
  if (!response.ok) {
    throw new Error("Une erreur est survenue.");
  }

  const data = await response.json();
  return data; // { answer, sources, model_used, cached }
}
```

### React (exemple minimal avec état de chargement)

```jsx
import { useState } from "react";

function OrientationChat() {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const ask = async (q) => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("http://localhost:8000/api/v1/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: q }),
      });
      if (!res.ok) throw new Error(`Erreur ${res.status}`);
      const data = await res.json();
      setAnswer(data);
      setQuestion("");
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <input value={question} onChange={(e) => setQuestion(e.target.value)} />
      <button onClick={() => ask(question)} disabled={loading || question.length < 3}>
        {loading ? "..." : "Envoyer"}
      </button>
      {error && <p>{error}</p>}

      {answer && (
        <div>
          <p>{answer.answer}</p>

          {/* Boutons cliquables générés à partir des suggestions du LLM */}
          {answer.suggested_questions.length > 0 && (
            <div className="suggestions">
              {answer.suggested_questions.map((q) => (
                <button key={q} onClick={() => ask(q)} disabled={loading}>
                  {q}
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
```

### Python

```python
import requests

response = requests.post(
    "http://localhost:8000/api/v1/ask",
    json={"question": "Quelles filières après un bac scientifique ?"},
)
response.raise_for_status()
data = response.json()
print(data["answer"])
```

---

## Notes pour le frontend

- **Temps de réponse** : une question sans cache prend généralement 1 à 3
  secondes (recherche + génération Groq). Une question en cache (`cached: true`)
  répond quasi instantanément — prévoir un indicateur de chargement adapté.
- **Affichage des sources** : recommandé d'afficher au moins la première
  source (`sources[0].source`) pour donner de la crédibilité à la réponse,
  sans nécessairement montrer le score technique à l'utilisateur final.
- **Historique de conversation** : non géré côté backend pour l'instant
  (chaque question est traitée indépendamment). Si un historique multi-tours
  est nécessaire, il doit être géré côté frontend ou fera l'objet d'une
  évolution backend ultérieure.