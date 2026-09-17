"""
Instance partagée du rate limiter (slowapi).
Isolée dans son propre module pour éviter un import circulaire entre
app/main.py (qui l'enregistre sur l'app FastAPI) et app/api/routes.py
(qui l'utilise comme décorateur sur les routes).
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import get_settings

settings = get_settings()

limiter = Limiter(key_func=get_remote_address, enabled=settings.rate_limit_enabled)
