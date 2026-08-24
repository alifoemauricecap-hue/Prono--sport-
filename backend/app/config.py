"""Configuration centrale. Aucune clé/secret en dur — tout vient de l'environnement."""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

# Dev atelier : SQLite (0 €). Prod : DATABASE_URL=postgresql+psycopg://user:pass@db:5432/pronosport
DATABASE_URL: str = os.environ.get(
    "DATABASE_URL", f"sqlite:///{DATA_DIR / 'prono_sport.db'}"
)

HTTP_TIMEOUT_SECONDS: float = float(os.environ.get("HTTP_TIMEOUT_SECONDS", "30"))
HTTP_USER_AGENT = "PRONO-SPORT/0.1 (analyse football - sources publiques)"
