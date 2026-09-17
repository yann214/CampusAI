"""
Service de chat "documents" — INDÉPENDANT du pipeline RAG.

Ici on ne fait pas de recherche sémantique sur le contenu des documents :
on laisse le modèle appeler un outil (tool calling) qui interroge les
métadonnées en base (nom, description, tags) pour retrouver un ou plusieurs
fichiers, puis on renvoie les liens de téléchargement construits côté
backend (jamais générés par le modèle lui-même).

Le client Groq est compatible OpenAI, le tool calling suit donc exactement
le même format que l'API OpenAI (tools / tool_calls / role="tool").
"""

import json

from groq import Groq

from app.config import get_settings
from app.services.document_service import search_documents

settings = get_settings()

SYSTEM_PROMPT = """Tu aides un étudiant à retrouver un document précis (PDF ou Word) \
parmi ceux disponibles sur la plateforme de la faculté.

Règles à respecter strictement :
- Utilise TOUJOURS l'outil search_documents pour chercher, ne réponds jamais de mémoire.
- Ne prétends jamais avoir trouvé un document que l'outil n'a pas renvoyé.
- Si l'outil ne renvoie aucun résultat, dis-le clairement à l'étudiant et propose-lui \
de reformuler (autre mot-clé, nom exact du document, etc.).
- Si plusieurs documents correspondent, décris-les brièvement (nom, sous-dossier) et \
demande à l'étudiant de préciser lequel il veut, plutôt que d'en choisir un au hasard.
- Si un seul document correspond clairement à la demande, confirme-le simplement en \
une phrase courte (le lien de téléchargement sera affiché séparément par l'interface, \
ne l'invente pas et ne l'inclus pas toi-même dans ta réponse).
- Réponds en français, de façon brève et directe.
- Ne donne pas l'arborescence du fichier, où se trouve le document.

en cas de message hors-sujet (ex: question d'orientation, salutation, small talk), réponds poliment mais ne fais pas de recherche et ne propose pas de document.
"""

DOCUMENT_SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "search_documents",
        "description": (
            "Recherche des documents (PDF, Word) disponibles au téléchargement, "
            "par mots-clés sur leur nom, description ou tags."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Mots-clés de recherche (ex: 'guide étudiant 2025', 'emploi du temps informatique')",
                },
                "sous_dossier": {
                    "type": "string",
                    "description": "Filtre optionnel sur le sous-dossier si l'étudiant le précise explicitement",
                },
            },
            "required": ["query"],
        },
    },
}


class DocumentChatService:
    def __init__(self):
        self._client = None

    def _get_client(self) -> Groq:
        if self._client is None:
            if not settings.groq_api_key:
                raise RuntimeError(
                    "GROQ_API_KEY n'est pas configurée. Ajoute ta clé dans le fichier .env."
                )
            self._client = Groq(api_key=settings.groq_api_key)
        return self._client

    def _execute_tool_call(self, tool_call) -> tuple[str, list[dict]]:
        """Exécute un appel d'outil et renvoie (contenu JSON pour le modèle, documents trouvés bruts)."""
        args = json.loads(tool_call.function.arguments or "{}")
        results = search_documents(
            query=args.get("query", ""),
            sous_dossier=args.get("sous_dossier"),
        )
        # Le modèle ne reçoit que des infos descriptives, jamais le chemin disque.
        return json.dumps(results, default=str, ensure_ascii=False), results

    def answer(self, message: str, max_tool_rounds: int = 3) -> dict:
        """
        Retourne {"answer": str, "sources": list[dict]} où chaque document
        contient {id, nom_original, sous_dossier, type_fichier}.
        """
        client = self._get_client()
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": message},
        ]

        found_documents: list[dict] = []

        for _ in range(max_tool_rounds):
            response = client.chat.completions.create(
                model=settings.document_chat_model,
                messages=messages,
                tools=[DOCUMENT_SEARCH_TOOL],
                tool_choice="auto",
                max_tokens=settings.document_chat_max_tokens,
                temperature=0.2,
            )
            choice = response.choices[0]
            tool_calls = choice.message.tool_calls

            if not tool_calls:
                # Le modèle a fini de raisonner et répond directement.
                reply_text = choice.message.content or ""
                unique_docs = {d["id"]: d for d in found_documents}.values()
                return {"answer": reply_text.strip(), "sources": list(unique_docs)}

            # On ajoute le message assistant (avec ses tool_calls) puis un
            # message "tool" par appel, comme l'exige le format OpenAI/Groq.
            messages.append(
                {
                    "role": "assistant",
                    "content": choice.message.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                        }
                        for tc in tool_calls
                    ],
                }
            )

            for tool_call in tool_calls:
                if tool_call.function.name == "search_documents":
                    tool_content, results = self._execute_tool_call(tool_call)
                    found_documents.extend(results)
                else:
                    tool_content = json.dumps({"error": "Outil inconnu"})

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": tool_content,
                    }
                )

        # Sécurité anti-boucle infinie : trop d'allers-retours d'outils.
        unique_docs = {d["id"]: d for d in found_documents}.values()
        return {
            "answer": "J'ai trouvé plusieurs résultats possibles, peux-tu préciser ta demande ?",
            "sources": list(unique_docs),
        }


document_chat_service = DocumentChatService()
