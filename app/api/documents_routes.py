"""
Routes de recherche/téléchargement de documents — indépendantes du RAG.

- POST /documents/chat : l'étudiant demande un document en langage naturel,
  le modèle appelle l'outil de recherche et on renvoie les documents trouvés
  avec un lien de téléchargement pour chacun.
- GET /documents/{id}/download : télécharge le fichier correspondant.
"""

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from app.config import get_settings
from app.models.schemas import DocumentChatRequest, DocumentChatResponse, DocumentInfo
from app.rate_limiter import limiter
from app.services.document_chat_service import document_chat_service
from app.services.document_service import get_document_by_id

router = APIRouter()
settings = get_settings()


@router.post("/documents/chat", response_model=DocumentChatResponse, tags=["Documents"])
@limiter.limit(settings.rate_limit_ask)
async def chat_documents(request: Request, payload: DocumentChatRequest):
    """
    Reçoit un message du type "je veux tel document" et renvoie une réponse
    textuelle courte accompagnée des documents trouvés (avec lien de
    téléchargement), ou une liste vide si rien n'a été trouvé.
    """
    try:
        result = document_chat_service.answer(payload.message)
    except RuntimeError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Le service de recherche de documents est temporairement indisponible : {str(e)}",
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Erreur lors de la recherche du document : {str(e)}",
        )

    documents = [
        DocumentInfo(
            id=doc["id"],
            nom=doc["nom_original"],
            sous_dossier=doc.get("sous_dossier"),
            type_fichier=doc.get("type_fichier"),
            url=f"{settings.api_prefix}/documents/{doc['id']}/download",
        )
        for doc in result["sources"]
    ]

    return DocumentChatResponse(answer=result["answer"], sources=documents)


@router.get("/documents/{doc_id}/download", tags=["Documents"])
async def download_document(doc_id: int):
    """Télécharge le fichier correspondant à l'id donné."""
    doc = get_document_by_id(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document introuvable")

    files_root = Path(settings.files_root_dir).resolve()
    file_path = (files_root / doc["chemin_relatif"]).resolve()

    # Empêche toute sortie du dossier autorisé (path traversal), même si
    # chemin_relatif contenait un ".." malencontreux en base.
    if files_root not in file_path.parents and file_path != files_root:
        raise HTTPException(status_code=400, detail="Chemin de fichier invalide")

    if not file_path.exists():
        raise HTTPException(status_code=410, detail="Le fichier n'existe plus sur le serveur")

    media_type = "application/pdf" if doc["type_fichier"] == "pdf" else (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )

    return FileResponse(
        path=file_path,
        filename=doc["nom_original"],
        media_type=media_type,
    )
