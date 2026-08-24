#!/bin/sh
# PRONO SPORT 2.0 — démarrage universel 24/7 (Koyeb / HF Spaces / VPS / Termux).
# §1 honnêteté : base vide -> on NE SIMULE RIEN. L'API répond tout de suite
# ("DONNÉE NON DISPONIBLE") pendant que le bootstrap remplit les VRAIES données en fond.
set -e
cd "$(dirname "$0")"
mkdir -p ../data
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
echo "PRONO SPORT 2.0 en ligne sur le port $PORT"
exec uvicorn app.api:app --host 0.0.0.0 --port "$PORT"
