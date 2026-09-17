"""
Charge des données structurées depuis un fichier SQL.

Deux cas supportés :
1. Un dump SQL (.sql) contenant CREATE TABLE + INSERT -> exécuté dans une
   base SQLite temporaire en mémoire.
2. Une base SQLite déjà prête (.db / .sqlite / .sqlite3) -> ouverte directement.

⚠️ Limite importante : l'exécution se fait avec le moteur SQLite. Un dump
généré depuis MySQL ou PostgreSQL contient souvent une syntaxe non
compatible (ENGINE=InnoDB, AUTO_INCREMENT, types spécifiques...).
Dans ce cas, il faut d'abord convertir le dump vers un format compatible
SQLite (ex. outils comme `mysql2sqlite`), ou exporter directement les
tables voulues au format SQLite/CSV.
"""

import re
import sqlite3
from pathlib import Path

from app.ingestion.loader import RawDocument


def _sanitize_mysql_dump(sql_text: str) -> str:
    """
    Convertit un dump mysqldump/phpMyAdmin en script compatible SQLite.
    Ne modifie pas les dumps déjà compatibles SQLite (les remplacements
    ne trouvent simplement rien à faire dans ce cas).
    """
    text = sql_text

    # 0. Convertit l'échappement de chaînes façon MySQL (\', \n, \r, \t, \\)
    #    vers ce que SQLite comprend. SQLite n'interprète PAS le backslash
    #    comme caractère d'échappement : \'Université casse le parsing
    #    (la chaîne se termine au \, puis "Université" devient un token
    #    invalide). SQLite attend un doublement du guillemet : ''.
    #    L'ordre est important : \\ doit être neutralisé AVANT de traiter \'.
    text = text.replace("\\\\", "\x00BACKSLASH\x00")
    text = text.replace("\\'", "''")
    text = text.replace('\\"', '"')
    text = text.replace("\\n", "\n")
    text = text.replace("\\r", "\r")
    text = text.replace("\\t", "\t")
    text = text.replace("\\0", "\0")
    text = text.replace("\x00BACKSLASH\x00", "\\")

    # 1. Retire les commentaires conditionnels MySQL : /*!40101 ... */;
    text = re.sub(r"/\*!.*?\*/;?", "", text, flags=re.DOTALL)

    # 2. Retire les commentaires multi-lignes classiques /* ... */
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)

    # 3. Retire LOCK TABLES / UNLOCK TABLES
    text = re.sub(r"^\s*(LOCK|UNLOCK)\s+TABLES.*?;\s*$", "", text, flags=re.MULTILINE | re.IGNORECASE)

    # 4. Retire les instructions SET isolées (SET NAMES, SET FOREIGN_KEY_CHECKS, ...)
    text = re.sub(r"^\s*SET\s+.*?;\s*$", "", text, flags=re.MULTILINE | re.IGNORECASE)

    # 5. Retire START TRANSACTION / COMMIT (non supportés tels quels par executescript)
    text = re.sub(r"^\s*(START TRANSACTION|COMMIT|BEGIN)\s*;\s*$", "", text, flags=re.MULTILINE | re.IGNORECASE)

    # 6. Retire les options de table après le CREATE TABLE : ) ENGINE=... DEFAULT CHARSET=...;
    text = re.sub(r"\)\s*ENGINE\s*=.*?;", ");", text, flags=re.IGNORECASE | re.DOTALL)

    # 7. Retire les mots-clés spécifiques MySQL sans équivalent SQLite nécessaire
    text = re.sub(r"\bAUTO_INCREMENT\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\bUNSIGNED\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\bZEROFILL\b", "", text, flags=re.IGNORECASE)

    # 8. Convertit ENUM(...) en TEXT (SQLite n'a pas de type ENUM)
    text = re.sub(r"ENUM\([^)]*\)", "TEXT", text, flags=re.IGNORECASE)

    # 9. Retire CHARACTER SET xxx [COLLATE yyy] sur les colonnes
    text = re.sub(r"CHARACTER SET \w+(\s+COLLATE\s+\w+)?", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\bCOLLATE\s+\w+", "", text, flags=re.IGNORECASE)

    # 9bis. Retire "ON UPDATE CURRENT_TIMESTAMP" (clause MySQL sur les colonnes
    #       timestamp, ex: updated_at) — non supportée par SQLite.
    text = re.sub(r"\bON UPDATE CURRENT_TIMESTAMP(\(\))?", "", text, flags=re.IGNORECASE)

    # 9quinquies. Retire les commentaires de colonne COMMENT '...' — non
    #             supportés par SQLite dans un CREATE TABLE. Le contenu peut
    #             contenir des guillemets doublés ('') suite à la conversion
    #             de l'étape 0, d'où le motif (?:[^']|'')*.
    text = re.sub(r"COMMENT\s+'(?:[^']|'')*'", "", text, flags=re.IGNORECASE)

    # 9ter. Retire "ON DUPLICATE KEY UPDATE ..." en fin d'INSERT — non supporté
    #       par SQLite (équivalent : ON CONFLICT, syntaxe différente).
    text = re.sub(r"\bON DUPLICATE KEY UPDATE\b.*?;", ";", text, flags=re.IGNORECASE | re.DOTALL)

    # 9quater. Retire les instructions ALTER TABLE entièrement : mysqldump les
    #          utilise pour fixer AUTO_INCREMENT (MODIFY) ou ajouter des clés
    #          étrangères après coup (ADD CONSTRAINT ... FOREIGN KEY ... ON
    #          DELETE/UPDATE ...). SQLite ne supporte ni MODIFY ni l'ajout de
    #          contraintes via ALTER TABLE — ces informations ne sont pas
    #          nécessaires pour l'ingestion RAG (pas besoin d'intégrité
    #          référentielle stricte ici).
    text = re.sub(r"^\s*ALTER TABLE\b.*?;\s*$", "", text, flags=re.MULTILINE | re.IGNORECASE | re.DOTALL)

    # 10. Retire les déclarations d'index simples (KEY / UNIQUE KEY), gardées
    #     uniquement pour MySQL — SQLite ne les accepte pas dans un CREATE TABLE.
    #     PRIMARY KEY est préservé (ne matche pas ce motif).
    text = re.sub(r"^\s*(UNIQUE\s+)?KEY\s+`?\w+`?\s*\([^)]*\),?\s*$", "", text, flags=re.MULTILINE | re.IGNORECASE)

    # 11. Nettoie les virgules laissées orphelines avant une parenthèse fermante
    text = re.sub(r",\s*\)", ")", text)

    return text


def _rows_to_documents(
    conn: sqlite3.Connection,
    source_name: str,
    included_tables: list[str] | None = None,
    excluded_tables: list[str] | None = None,
) -> list[RawDocument]:
    """
    Transforme chaque ligne de chaque table en un RawDocument lisible.

    - Si `included_tables` est fourni (non vide), SEULES ces tables sont traitées.
    - Sinon, toutes les tables sont traitées SAUF celles dans `excluded_tables`.
    """
    included_tables = included_tables or []
    excluded_tables = excluded_tables or []

    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    tables = [row[0] for row in cursor.fetchall()]

    if included_tables:
        tables = [t for t in tables if t in included_tables]
    elif excluded_tables:
        tables = [t for t in tables if t not in excluded_tables]

    documents = []
    for table in tables:
        cursor.execute(f"SELECT * FROM {table}")
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()

        for i, row in enumerate(rows):
            parts = [f"{col} : {val}" for col, val in zip(columns, row) if val not in (None, "")]
            content = ", ".join(parts)
            if content:
                documents.append(RawDocument(content=content, source=f"{source_name}#{table}#{i}"))

        print(f"   • table '{table}' : {len(rows)} ligne(s) transformée(s) en documents")

    skipped = set(_ for _ in _all_table_names(conn)) - set(tables)
    if skipped:
        print(f"   • table(s) ignorée(s) (filtrage) : {', '.join(sorted(skipped))}")

    return documents


def _all_table_names(conn: sqlite3.Connection) -> list[str]:
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    return [row[0] for row in cursor.fetchall()]


def load_sql_dump(
    path: str | Path,
    included_tables: list[str] | None = None,
    excluded_tables: list[str] | None = None,
) -> list[RawDocument]:
    """Exécute un fichier .sql (CREATE TABLE + INSERT) dans une base SQLite temporaire."""
    path = Path(path)
    conn = sqlite3.connect(":memory:")

    raw_script = path.read_text(encoding="utf-8")
    sanitized_script = _sanitize_mysql_dump(raw_script)

    try:
        conn.executescript(sanitized_script)
    except sqlite3.Error as e:
        # Sauvegarde la version nettoyée pour permettre un diagnostic rapide
        debug_path = path.with_suffix(".sanitized.sql")
        debug_path.write_text(sanitized_script, encoding="utf-8")
        print(
            f"⚠️  Impossible d'exécuter {path.name} même après conversion : {e}\n"
            f"   -> Script nettoyé sauvegardé dans {debug_path.name} pour inspection.\n"
            f"   -> Fichier ignoré pour cette ingestion."
        )
        conn.close()
        return []

    documents = _rows_to_documents(conn, path.name, included_tables, excluded_tables)
    conn.close()
    return documents


def load_sqlite_db(
    path: str | Path,
    included_tables: list[str] | None = None,
    excluded_tables: list[str] | None = None,
) -> list[RawDocument]:
    """Ouvre directement une base SQLite existante."""
    path = Path(path)
    conn = sqlite3.connect(str(path))
    documents = _rows_to_documents(conn, path.name, included_tables, excluded_tables)
    conn.close()
    return documents


def load_sql_source(
    path: str | Path,
    included_tables: list[str] | None = None,
    excluded_tables: list[str] | None = None,
) -> list[RawDocument]:
    """Point d'entrée unique : détecte le type de fichier et route vers le bon loader."""
    path = Path(path)
    suffix = path.suffix.lower()

    if suffix == ".sql":
        return load_sql_dump(path, included_tables, excluded_tables)
    elif suffix in (".db", ".sqlite", ".sqlite3"):
        return load_sqlite_db(path, included_tables, excluded_tables)
    else:
        print(f"⚠️  Format non supporté pour {path.name}, ignoré.")
        return []


def load_all_sql_sources(
    directory: str | Path,
    included_tables: list[str] | None = None,
    excluded_tables: list[str] | None = None,
) -> list[RawDocument]:
    """Charge tous les fichiers SQL/SQLite trouvés dans un dossier."""
    directory = Path(directory)
    if not directory.exists():
        return []

    documents = []
    for path in sorted(directory.glob("*")):
        if path.suffix.lower() in (".sql", ".db", ".sqlite", ".sqlite3"):
            print(f"🗄️  Traitement de {path.name} ...")
            documents.extend(load_sql_source(path, included_tables, excluded_tables))

    return documents