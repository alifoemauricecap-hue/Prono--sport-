#!/bin/sh
# PRONO SPORT 3.0 — démarrage universel 24/7 (Render / Koyeb / HF / VPS / Termux).
# §1 honnêteté : base vide → on NE SIMULE RIEN. L'API répond tout de suite
# (« DONNÉE INDISPONIBLE ») pendant que le bootstrap remplit les VRAIES données.
# REPRISE : si le bootstrap n'est pas terminé (marqueur .bootstrap_done absent —
# ex. après une veille du plan Free qui tue le processus de fond), il est relancé
# au démarrage suivant ; les étapes déjà faites sont sautées (marqueurs).
set -e
cd "$(dirname "$0")"
python - <<'PY'
from pathlib import Path
from app.config import DATABASE_URL
if DATABASE_URL.startswith("sqlite:///"):
    Path(DATABASE_URL.replace("sqlite:///", "", 1)).parent.mkdir(parents=True, exist_ok=True)
PY
python -m app.cli init-db

DBDIR=$(python - <<'PY'
from pathlib import Path
from app.config import DATABASE_URL
print(Path(DATABASE_URL.replace("sqlite:///", "", 1)).parent
      if DATABASE_URL.startswith("sqlite:///") else ".")
PY
)

if [ ! -f "$DBDIR/.bootstrap_done" ]; then
  echo "[bootstrap] 1er démarrage ou incomplet → bootstrap mondial (reprise idempotente) en arrière-plan…"
  ./bootstrap_data.sh > /tmp/bootstrap.log 2>&1 &
fi

PORT="${PORT:-8000}"
echo "PRONO SPORT 3.0 en ligne sur le port $PORT"
exec uvicorn app.api:app --host 0.0.0.0 --port "$PORT"
