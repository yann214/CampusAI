"""
Connexion MySQL — utilisée uniquement par la route /documents/chat pour
interroger la table `documents` (métadonnées des fichiers téléchargeables).

Le reste du projet (RAG) n'a pas besoin de connexion MySQL live : il ingère
un dump .sql statique via app/ingestion/sql_loader.py. Ce module est
indépendant de ça.
"""

from contextlib import contextmanager

import pymysql
import pymysql.cursors
from dbutils.pooled_db import PooledDB

from app.config import get_settings

settings = get_settings()

_pool: PooledDB | None = None


def _get_pool() -> PooledDB:
    global _pool
    if _pool is None:
        _pool = PooledDB(
            creator=pymysql,
            maxconnections=10,
            mincached=1,
            host=settings.mysql_host,
            port=settings.mysql_port,
            user=settings.mysql_user,
            password=settings.mysql_password,
            database=settings.mysql_database,
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=True,
        )
    return _pool


@contextmanager
def get_db_cursor():
    """
    Fournit un curseur MySQL prêt à l'emploi (dictionnaires en sortie).
    Usage :
        with get_db_cursor() as cursor:
            cursor.execute("SELECT * FROM documents WHERE id = %s", (doc_id,))
            row = cursor.fetchone()
    """
    pool = _get_pool()
    conn = pool.connection()
    try:
        with conn.cursor() as cursor:
            yield cursor
    finally:
        conn.close()  # rend la connexion au pool, ne la ferme pas vraiment
