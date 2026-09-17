"""
Scanne data/files/ (sous-dossiers inclus) et synchronise la table MySQL
`documents` : insère les nouveaux fichiers, laisse les autres intacts.

Usage :
    python -m scripts.sync_documents

⚠️ Ce script ne renseigne PAS automatiquement `description`/`tags` (ce champ
sert à la recherche par mots-clés) : après un premier lancement, complète-les
manuellement en base pour les documents importants, sinon la recherche ne se
basera que sur le nom de fichier.
"""

from pathlib import Path

import pymysql

from app.config import get_settings
from app.db import get_db_cursor

settings = get_settings()

SUPPORTED_EXTENSIONS = {".pdf": "pdf", ".doc": "doc", ".docx": "docx"}


def sync_documents():
    files_root = Path(settings.files_root_dir)
    if not files_root.exists():
        print(f"❌ Le dossier {files_root} n'existe pas.")
        return

    inserted, skipped = 0, 0

    with get_db_cursor() as cursor:
        for path in sorted(files_root.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue

            chemin_relatif = str(path.relative_to(files_root)).replace("\\", "/")
            sous_dossier = str(path.parent.relative_to(files_root)).replace("\\", "/")
            if sous_dossier == ".":
                sous_dossier = None

            try:
                cursor.execute(
                    """
                    INSERT INTO documents
                        (nom_original, nom_fichier, sous_dossier, chemin_relatif, type_fichier)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        path.name,
                        path.name,
                        sous_dossier,
                        chemin_relatif,
                        SUPPORTED_EXTENSIONS[path.suffix.lower()],
                    ),
                )
                inserted += 1
                print(f"✅ Ajouté : {chemin_relatif}")
            except pymysql.err.IntegrityError:
                # chemin_relatif déjà en base (contrainte UNIQUE) -> on ignore
                skipped += 1

    print(f"\n{inserted} document(s) ajouté(s), {skipped} déjà présent(s) en base.")
    print(
        "💡 Pense à compléter la colonne `description` (et `tags`) en base pour "
        "les documents importants, pour améliorer la pertinence de la recherche."
    )


if __name__ == "__main__":
    sync_documents()
