"""
Charge du contenu texte depuis des pages web.
Vient compléter loader.py (fichiers locaux) avec une source distante.
"""

import re
import time
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from app.ingestion.loader import RawDocument

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; RAGOrientationBot/1.0; "
        "+usage éducatif non commercial)"
    )
}

# Balises qui ne contiennent jamais de contenu utile pour le RAG
TAGS_TO_REMOVE = ["script", "style", "nav", "footer", "header", "noscript", "form", "aside"]


def _clean_html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(TAGS_TO_REMOVE):
        tag.decompose()

    text = soup.get_text(separator="\n")
    # Compresse les lignes vides multiples et les espaces superflus
    lines = [line.strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    return "\n".join(lines)


def _source_name_from_url(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.netloc}{parsed.path}".rstrip("/")


def load_url(url: str, timeout: int = 15) -> RawDocument | None:
    """Récupère et nettoie le contenu d'une seule page web."""
    try:
        response = requests.get(url, headers=HEADERS, timeout=timeout)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"⚠️  Impossible de récupérer {url} : {e}")
        return None

    content = _clean_html_to_text(response.text)

    if not content or len(content) < 50:
        print(f"⚠️  Contenu trop court ou vide pour {url}, ignoré.")
        return None

    return RawDocument(content=content, source=_source_name_from_url(url))


def load_urls(urls: list[str], delay_seconds: float = 1.0) -> list[RawDocument]:
    """
    Récupère plusieurs pages web séquentiellement.
    `delay_seconds` évite de surcharger les sites ciblés (politesse basique).
    """
    documents = []
    for url in urls:
        doc = load_url(url)
        if doc:
            documents.append(doc)
        time.sleep(delay_seconds)
    return documents


def load_urls_from_file(path: str) -> list[RawDocument]:
    """
    Lit une liste d'URLs depuis un fichier texte (une URL par ligne,
    les lignes vides ou commençant par # sont ignorées).
    """
    urls = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                urls.append(line)

    if not urls:
        return []

    print(f"🌐 {len(urls)} URL(s) à scraper depuis {path}")
    return load_urls(urls)
