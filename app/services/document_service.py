"""
Service de recherche de documents — interroge la table MySQL `documents`
(métadonnées des fichiers PDF/Word rangés dans data/files/).

Recherche en deux temps :
1. FULLTEXT (MATCH ... AGAINST) — pertinent dès que la table contient
   suffisamment de lignes et de texte dans description/tags.
2. Repli en LIKE si la recherche FULLTEXT ne renvoie rien (utile tant que la
   table est petite ou que les descriptions sont courtes : le mode NATURAL
   LANGUAGE de MySQL ignore les mots très fréquents et peut renvoyer 0
   résultat sur une table de quelques dizaines de lignes seulement).
"""

import pymysql

from app.config import get_settings
from app.db import get_db_cursor

settings = get_settings()


def _row_to_dict(row: dict) -> dict:
    return {
        "id": row["id"],
        "nom_original": row["nom_original"],
        "sous_dossier": row["sous_dossier"],
        "type_fichier": row["type_fichier"],
        "description": row["description"],
    }


def search_documents(query: str, sous_dossier: str | None = None, limit: int | None = None) -> list[dict]:
    """
    Recherche des documents par mots-clés dans nom_original, description, tags.
    Ne renvoie JAMAIS `chemin_relatif` (le modèle n'a pas besoin du chemin
    disque, seulement de l'id — le lien de téléchargement est construit
    par le backend, jamais par le LLM).
    """
    limit = limit or settings.document_search_limit

    with get_db_cursor() as cursor:
        sql = """
            SELECT id, nom_original, sous_dossier, type_fichier, description,
                   MATCH(nom_original, description, tags) AGAINST (%s IN NATURAL LANGUAGE MODE) AS score
            FROM documents
            WHERE MATCH(nom_original, description, tags) AGAINST (%s IN NATURAL LANGUAGE MODE)
        """
        params: list = [query, query]

        if sous_dossier:
            sql += " AND sous_dossier = %s"
            params.append(sous_dossier)

        sql += " ORDER BY score DESC LIMIT %s"
        params.append(limit)

        try:
            cursor.execute(sql, params)
            rows = cursor.fetchall()
        except pymysql.err.OperationalError:
            # Pas d'index FULLTEXT (table pas encore créée avec le bon script,
            # ou moteur non-InnoDB) -> on retente sans MATCH plus bas.
            rows = []

        if rows:
            return [_row_to_dict(r) for r in rows]

        # Repli LIKE : découpe la requête en mots, chaque mot doit matcher
        # au moins une des colonnes.
        words = [w for w in query.split() if len(w) >= 2][:6] or [query]
        like_conditions = []
        like_params: list = []
        for w in words:
            like_conditions.append(
                "(nom_original LIKE %s OR description LIKE %s OR tags LIKE %s)"
            )
            like_params.extend([f"%{w}%"] * 3)

        sql = f"""
            SELECT id, nom_original, sous_dossier, type_fichier, description
            FROM documents
            WHERE ({" OR ".join(like_conditions)})
        """
        if sous_dossier:
            sql += " AND sous_dossier = %s"
            like_params.append(sous_dossier)

        sql += " LIMIT %s"
        like_params.append(limit)

        cursor.execute(sql, like_params)
        rows = cursor.fetchall()
        return [_row_to_dict(r) for r in rows]


def get_document_by_id(doc_id: int) -> dict | None:
    with get_db_cursor() as cursor:
        cursor.execute(
            "SELECT id, nom_original, chemin_relatif, type_fichier FROM documents WHERE id = %s",
            (doc_id,),
        )
        return cursor.fetchone()


def list_sous_dossiers() -> list[str]:
    """Utile pour debug/administration : liste les sous-dossiers connus."""
    with get_db_cursor() as cursor:
        cursor.execute(
            "SELECT DISTINCT sous_dossier FROM documents WHERE sous_dossier IS NOT NULL ORDER BY sous_dossier"
        )
        return [r["sous_dossier"] for r in cursor.fetchall()]
