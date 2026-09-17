"""
Schémas Pydantic — définissent le contrat de l'API.
C'est ce que l'équipe frontend doit connaître pour consommer l'API.
"""

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(
        ...,
        min_length=3,
        max_length=1000,
        description="Question posée par l'étudiant",
        examples=["Quelles filières sont accessibles après un bac scientifique ?"],
    )
    conversation_id: str | None = Field(
        default=None,
        description="Identifiant optionnel pour lier plusieurs questions d'une même session",
    )


class SourceChunk(BaseModel):
    content: str
    source: str | None = None
    score: float | None = None


class AskResponse(BaseModel):
    answer: str
    sources: list[SourceChunk] = []
    suggested_questions: list[str] = Field(
        default=[],
        description="Questions de suivi suggérées, pensées pour être affichées "
        "comme boutons cliquables côté frontend.",
    )
    model_used: str
    cached: bool = False


class HealthResponse(BaseModel):
    status: str
    environment: str
    vectorstore_ready: bool


# --- Route /documents/chat (indépendante du RAG) ---


class DocumentChatRequest(BaseModel):
    message: str = Field(
        ...,
        min_length=2,
        max_length=500,
        description="Message de l'étudiant, ex: 'je veux le guide de l'étudiant 2025'",
        examples=["je veux le guide de l'étudiant"],
    )


class DocumentInfo(BaseModel):
    id: int
    nom: str
    sous_dossier: str | None = None
    type_fichier: str | None = None
    url: str = Field(description="URL relative à appeler pour télécharger le fichier")


class DocumentChatResponse(BaseModel):
    answer: str
    sources: list[DocumentInfo] = []