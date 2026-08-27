#!/usr/bin/env bash
# ============================================================
# PRONO SPORT 3.0 — Installation 1-commande, 100 % GRATUITE
# Aucune clé API payante, aucun abonnement : uniquement des
# sources publiques gratuites (ESPN public, football-data.co.uk,
# OpenLigaDB, TheSportsDB key "3", Open-Meteo).
# Testé : Linux / macOS (Python 3.11+). Windows : voir docs/03.
# ============================================================
set -euo pipefail
cd "$(dirname "$0")/backend"

echo "▶ 1/4  Environnement Python…"
python3 -m venv .venv 2>/dev/null || python -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

echo "▶ 2/4  Base de données (SQLite par défaut, GRATUIT — PostgreSQL optionnel)…"
export DATABASE_URL="${DATABASE_URL:-sqlite:///$(pwd)/../data/prono_sport.db}"
mkdir -p ../data
python -m app.cli init-db

echo "▶ 3/4  Ingestion initiale des données réelles (peut prendre 10-20 min)…"
python -m app.cli ingest-fduk --divs E0 E1 E2 E3 EC SC0 SC1 SC2 SC3 D1 D2 I1 I2 SP1 SP2 F1 F2 N1 B1 P1 T1 G1 --seasons 2526 2627 || true
python -m app.cli ingest-fduk-fixtures || true
python -m app.cli ingest-openligadb --leagues bl1 bl2 || true
python -m app.cli ingest-espn --leagues eng.1 eng.2 esp.1 ger.1 ita.1 fra.1 fra.2 por.1 ned.1 tur.1 bel.1 sco.1 --days-back 4 --days-ahead 3 || true
python -m app.cli espn-media || true

echo "▶ 4/4  Moteurs : cohérence, analytics, prédictions…"
python -m app.cli verify
python -m app.cli compute-analytics
python -m app.cli compute-predictions

cat << 'DONE'

✅ PRONO SPORT 3.0 installé.

Lancer l'application :
  cd backend && source .venv/bin/activate
  AUTO_INGEST=1 uvicorn app.api:app --host 0.0.0.0 --port 8000

  → Interface : http://localhost:8000
  → API       : http://localhost:8000/v1/stats

Mise à jour quotidienne (cron conseillé, ex. 6h45) :
  45 6 * * *  /chemin/vers/prono-sport/update_daily.sh >> /tmp/prono.log 2>&1

Optionnel mais GRATUIT : crée une clé sur https://www.football-data.org (10 req/min)
puis exporte FOOTBALL_DATA_ORG_TOKEN=ta_clé pour activer la 6e source.
DONE
