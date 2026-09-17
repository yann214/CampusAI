"""
Service LLM — interface avec l'API Groq (modèles open source Llama, gratuit).

Stratégie de robustesse :
- Retry avec backoff exponentiel sur le modèle principal (erreurs transitoires :
  timeout, rate limit ponctuel)
- Si le modèle principal échoue malgré les retries, bascule automatique sur
  le modèle de secours (plus petit, donc moins concerné par les limites)

Format de sortie :
- Le modèle répond en JSON structuré (réponse + questions de suivi
  suggérées) en un seul appel, pour ne pas doubler la consommation du
  quota gratuit avec un second appel dédié aux suggestions.
"""

import json
import time

from groq import Groq

from app.config import get_settings

settings = get_settings()

SYSTEM_PROMPT = """Tu es un assistant d'orientation qui aide les étudiants à choisir leur \
filière, comprendre les conditions d'admission et connaître les débouchés.

Règles à respecter strictement :
- soit precis dans tes réponses, en donnant des informations fiables et vérifiables.
- donne ce que veux demande la question, sans inventer de détails.
- consulte d'abord le contexte fourni (extraits de documents pertinents) pour répondre à la question.
- quand tu peux repondre avec des items ou tiret fais le c'est plus lisible et facile à comprendre.
- si le contexte ne contient pas d'information pertinente, vas sur le web pour trouver une réponse fiable et vérifiable, en citant tes sources.

- Réponds en français, de façon claire et structurée, avec un ton bienveillant adapté à un \
jeune étudiant qui cherche à s'orienter.
- Si plusieurs informations du contexte sont pertinentes, organise ta réponse (liste, étapes) \
plutôt qu'un unique paragraphe dense.

Tu dois répondre UNIQUEMENT avec un objet JSON valide, sans aucun texte avant ou après, au \
format exact suivant :
{
  "answer": "ta réponse complète en français ici",
  "suggested_questions": ["question de suivi 1", "question de suivi 2", "question de suivi 3"]
}

Règles pour "suggested_questions" :
- Propose 2 à 3 questions de suivi courtes et pertinentes UNIQUEMENT quand cela a du sens : \
une vraie question d'orientation (filière, admission, débouché, durée d'études...) à laquelle \
tu as pu apporter une réponse utile, et pour laquelle il existe naturellement des questions \
de suivi liées au même sujet.
- Ne suggère AUCUNE question (liste vide []) dans les cas suivants :
  - Message de politesse ou social sans contenu informatif : salutation ("bonjour"), \
remerciement ("merci"), au revoir, small talk.
  - Question hors-sujet (rien à voir avec l'orientation étudiante).
  - Le contexte fourni est vide ou insuffisant pour répondre à la question initiale.
  - Ta réponse épuise déjà complètement le sujet et il n'y a pas de suite logique évidente.
- En résumé : suggère des questions seulement quand ça aide vraiment l'étudiant à continuer \
sa réflexion sur son orientation — pas par réflexe à chaque réponse. Dans le doute, mieux \
vaut une liste vide que des suggestions artificielles ou hors sujet.

NB : si tu n'as pas une information fait une recherche sur le web pour trouver la bonne reponse. Tu peux utiliser des sources fiables comme les sites officiels des universités, \
les sites gouvernementaux, ou des articles de presse reconnus. Cite tes sources si possible.
"""


class LLMService:
    def __init__(self):
        self._client = None

    def _get_client(self) -> Groq:
        if self._client is None:
            if not settings.groq_api_key:
                raise RuntimeError(
                    "GROQ_API_KEY n'est pas configurée. Ajoute ta clé dans le fichier .env "
                    "(récupérable sur https://console.groq.com)."
                )
            self._client = Groq(api_key=settings.groq_api_key)
        return self._client

    def _call_model(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        max_retries: int = 2,
    ) -> str:
        client = self._get_client()
        last_error: Exception | None = None

        for attempt in range(max_retries + 1):
            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=settings.llm_temperature,
                    max_tokens=settings.llm_max_tokens,
                    response_format={"type": "json_object"},
                )
                return response.choices[0].message.content

            except Exception as e:
                last_error = e
                if attempt < max_retries:
                    wait_seconds = 2**attempt  # 1s, puis 2s
                    print(
                        f"⚠️  Erreur Groq (modèle {model}, tentative {attempt + 1}/{max_retries + 1}) : "
                        f"{e} — nouvelle tentative dans {wait_seconds}s"
                    )
                    time.sleep(wait_seconds)

        raise last_error

    def _parse_response(self, raw_content: str) -> dict:
        """
        Parse la sortie JSON du modèle. En cas de JSON invalide (ça arrive,
        même en mode JSON forcé, sur certains modèles), on utilise le texte
        brut comme réponse plutôt que de faire planter toute la requête —
        l'étudiant aura sa réponse, juste sans suggestions cette fois-ci.
        """
        try:
            data = json.loads(raw_content)
            answer = str(data.get("answer", "")).strip()
            raw_suggestions = data.get("suggested_questions", [])

            if not isinstance(raw_suggestions, list):
                raw_suggestions = []

            suggestions = [str(s).strip() for s in raw_suggestions if str(s).strip()][:4]

            if not answer:
                answer = raw_content

            return {"answer": answer, "suggested_questions": suggestions}

        except (json.JSONDecodeError, TypeError):
            print("⚠️  Réponse du modèle non-JSON malgré le mode structuré, utilisée telle quelle.")
            return {"answer": raw_content, "suggested_questions": []}

    def generate(self, question: str, context: str, system_prompt: str | None = None) -> dict:
        """
        Génère une réponse à partir de la question et du contexte récupéré
        (chunks pertinents renvoyés par la base vectorielle).
        Retourne {"answer": str, "suggested_questions": list[str], "model_used": str}.
        """
        system_prompt = system_prompt or SYSTEM_PROMPT

        if context.strip():
            user_prompt = f"Contexte disponible :\n{context}\n\nQuestion de l'étudiant : {question}"
        else:
            user_prompt = (
                f"Aucun contexte pertinent n'a été trouvé dans la base de connaissances "
                f"pour cette question : {question}\n"
                f"Indique-le clairement à l'étudiant."
            )

        try:
            raw = self._call_model(settings.groq_model, system_prompt, user_prompt)
            parsed = self._parse_response(raw)
            return {**parsed, "model_used": settings.groq_model}

        except Exception as primary_error:
            print(f"⚠️  Échec du modèle principal ({settings.groq_model}) : {primary_error}")
            print(f"↪️  Bascule sur le modèle de secours ({settings.groq_model_fallback})...")

            try:
                raw = self._call_model(settings.groq_model_fallback, system_prompt, user_prompt)
                parsed = self._parse_response(raw)
                return {**parsed, "model_used": settings.groq_model_fallback}

            except Exception as fallback_error:
                raise RuntimeError(
                    f"Les deux modèles Groq ont échoué.\n"
                    f"  Principal ({settings.groq_model}) : {primary_error}\n"
                    f"  Secours ({settings.groq_model_fallback}) : {fallback_error}"
                )


llm_service = LLMService()