#!/bin/sh
# PRONO SPORT 3.0 — bootstrap mondial REPRENABLE (marqueurs par étape, 0 €).
# Chaque étape terminée pose un marqueur dans le répertoire de la base
# (disque persistant Render /data). Veille Free / redémarrage = perte de RIEN :
# au démarrage suivant, les étapes faites sont sautées, reprise à l'inachevé.
cd "$(dirname "$0")"
export PYTHONIOENCODING=utf-8

DBDIR=$(python - <<'PY'
from pathlib import Path
from app.config import DATABASE_URL
print(Path(DATABASE_URL.replace("sqlite:///", "", 1)).parent
      if DATABASE_URL.startswith("sqlite:///") else ".")
PY
)
DONE() { [ -f "$DBDIR/.bs_$1" ]; }
MARK() { touch "$DBDIR/.bs_$1" 2>/dev/null || true; }

if ! DONE s1; then
  echo "[1/8] BACKBONE MONDIAL — TheSportsDB eventsday (5 jours)"
  python -m app.cli ingest-tsdb-day --days 5 || true
  MARK s1
fi
if ! DONE s2a; then
  echo "[2/8] ESPN monde A — Europe + internationaux (J-3 à J+2)"
  python -m app.cli ingest-espn --world --conf UEFA --days-back 3 --days-ahead 2 || true
  python -m app.cli ingest-espn --world --conf INTERNATIONAL --days-back 3 --days-ahead 2 || true
  MARK s2a
fi
if ! DONE s2b; then
  echo "[2/8] ESPN monde B — Amériques + Asie + Afrique (J-3 à J+2)"
  python -m app.cli ingest-espn --world --conf CONMEBOL --days-back 3 --days-ahead 2 || true
  python -m app.cli ingest-espn --world --conf CONCACAF --days-back 3 --days-ahead 2 || true
  python -m app.cli ingest-espn --world --conf AFC --days-back 3 --days-ahead 2 || true
  python -m app.cli ingest-espn --world --conf CAF --days-back 3 --days-ahead 2 || true
  python -m app.cli ingest-openligadb --leagues bl1 bl2 bl3 --years 2025 2026 || true
  MARK s2b
fi
if ! DONE s3a; then
  echo "[3/8] fduk historiques 2526 A — E0 E1 E2 E3 EC D1 D2 I1 I2"
  python -m app.cli ingest-fduk --divs E0 E1 E2 E3 EC D1 D2 I1 I2 --seasons 2526 || true
  MARK s3a
fi
if ! DONE s3b; then
  echo "[3/8] fduk historiques 2526 B — SC0-3 SP1 SP2 F1 F2 N1 B1 P1 T1 G1"
  python -m app.cli ingest-fduk --divs SC0 SC1 SC2 SC3 SP1 SP2 F1 F2 N1 B1 P1 T1 G1 --seasons 2526 || true
  MARK s3b
fi
if ! DONE s3c; then
  echo "[3/8] fduk saison 2627 (22 divisions) + cotes actuelles"
  python -m app.cli ingest-fduk --divs E0 E1 E2 E3 EC SC0 SC1 SC2 SC3 D1 D2 I1 I2 SP1 SP2 F1 F2 N1 B1 P1 T1 G1 --seasons 2627 || true
  python -m app.cli ingest-fduk-fixtures || true
  MARK s3c
fi
if ! DONE s4; then
  echo "[4/8] vérification croisée (≥2 sources) + logos réels"
  python -m app.cli sweep-stale || true
  python -m app.cli verify || true
  python -m app.cli espn-media || true
  MARK s4
fi
if ! DONE s5; then
  echo "[5/8] MOTEURS — Elo/formes + prédictions + value bets"
  python -m app.cli compute-analytics || true
  python -m app.cli compute-predictions || true
  MARK s5
fi
if ! DONE s6; then
  echo "[6/8] RECHERCHE APPROFONDIE par ligue (Wikipedia FR/EN, 0 €)"
  python -m app.cli world-research || true
  MARK s6
fi
touch "$DBDIR/.bootstrap_done" 2>/dev/null || true
echo "[OK] BOOTSTRAP MONDIAL TERMINE — marqueurs posés, reprise garantie."
