#!/bin/sh
# PRONO SPORT 3.0 — démarrage universel 24/7 (Koyeb / HF Spaces / VPS / Termux).
# §1 honnêteté : base vide -> on NE SIMULE RIEN. L'API répond tout de suite
# ("DONNÉE NON DISPONIBLE") pendant que le bootstrap remplit les VRAIES données en fond.
set -e
cd "$(dirname "$0")"
mkdir -p ../data
# S'assurer que le répertoire du fichier de base existe (ex. /data monté sur Render).
# §90 Render : si DATABASE_URL pointe vers un répertoire non accessible en écriture
# (ex. /data sans disque persistant sur une instance non-root), on bascule
# automatiquement vers une base située dans le répertoire de l'application, qui est
# toujours accessible en écriture. Aucune donnée n'est jamais inventée pour autant :
# seule la localisation du fichier change ; le bootstrap reste idempotent.
DB_FIX=$(DATABASE_URL="${DATABASE_URL:-}" python - <<'PY'
import os
from pathlib import Path
url = os.environ.get("DATABASE_URL", "")
if url.startswith("sqlite:///"):
    db_path = Path(url.replace("sqlite:///", "", 1))
    parent = db_path.parent
    try:
        parent.mkdir(parents=True, exist_ok=True)
        probe = parent / ".write_test"
        probe.write_text("ok")
        probe.unlink()
    except OSError:
        fallback = Path(os.getcwd()).resolve().parent / "data" / "prono_sport.db"
        fallback.parent.mkdir(parents=True, exist_ok=True)
        print(f"sqlite:///{fallback}")
PY
)
if [ -n "$DB_FIX" ]; then
  echo "[startup] DATABASE_URL inaccessible en écriture -> bascule sur $DB_FIX"
  export DATABASE_URL="$DB_FIX"
fi
python -m app.cli init-db

NEED=$(python - <<'PY'
from sqlalchemy import create_engine, text
from app.config import DATABASE_URL
eng = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
n = eng.connect().execute(text("SELECT COUNT(*) FROM fixtures")).scalar()
print("yes" if n == 0 else "no")
PY
)

if [ "$NEED" = "yes" ]; then
  echo "[bootstrap] base vide -> 1re compilation des donnees reelles (~20-40 min) en arriere-plan..."
  ./bootstrap_data.sh > /tmp/bootstrap.log 2>&1 &
fi

PORT="${PORT:-8000}"
echo "PRONO SPORT 3.0 en ligne sur le port $PORT"
exec uvicorn app.api:app --host 0.0.0.0 --port "$PORT"
