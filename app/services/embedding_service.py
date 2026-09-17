"""
Service d'embedding — transforme du texte en vecteurs numériques
avec un modèle open source, exécuté localement (gratuit, pas d'API).
"""

from app.config import get_settings

settings = get_settings()


class EmbeddingService:
    def __init__(self, model_name: str | None = None):
        self._model_name = model_name or settings.embedding_model_name
        self._model = None  # chargement paresseux (lazy loading)

    def _load_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            print(f"Chargement du modèle d'embedding : {self._model_name} ...")
            self._model = SentenceTransformer(self._model_name)
        return self._model

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Transforme une liste de textes en liste de vecteurs."""
        if not texts:
            return []
        model = self._load_model()
        # normalize_embeddings=True -> facilite la similarité cosinus dans ChromaDB
        embeddings = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return embeddings.tolist()

    def embed_query(self, text: str) -> list[float]:
        """Transforme une seule requête (question de l'étudiant) en vecteur."""
        return self.embed_texts([text])[0]


embedding_service = EmbeddingService()
