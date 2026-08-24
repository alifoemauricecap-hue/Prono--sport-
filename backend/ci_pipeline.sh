#!/usr/bin/env bash
# PRONO SPORT 2.0 — pipeline CI (GitHub Actions) : régénère le site statique complet.
# 100 % gratuit : sources publiques sans clé, SQLite éphémère, aucune donnée inventée.
set -euo pipefail
cd "$(dirname "$0")"
export PYTHONIOENCODING=utf-8
export DATABASE_URL="sqlite:///$(pwd)/../data/ci.db"
mkdir -p ../data
rm -f ../data/ci.db

echo "=== [1/6] init + ingestion fduk (historiques + cotes actuelles) ==="
python -m app.cli init-db
python -m app.cli ingest-fduk --divs E0 E1 E2 E3 EC SC0 SC1 SC2 SC3 D1 D2 I1 I2 SP1 SP2 F1 F2 N1 B1 P1 T1 G1 --seasons 2526 2627 || true
python -m app.cli ingest-fduk-fixtures || true

echo "=== [2/6] ESPN (34 ligues, J-2 → J+2) + OpenLigaDB ==="
python -m app.cli ingest-espn --leagues eng.1 eng.2 eng.3 eng.4 eng.5 eng.fa eng.league_cup esp.1 esp.2 ger.1 ger.2 ita.1 ita.2 fra.1 fra.2 por.1 ned.1 tur.1 bel.1 sco.1 gre.1 aut.1 den.1 nor.1 swe.1 usa.1 ksa.1 jpn.1 aus.1 bra.1 arg.1 col.1 mex.1 --days-back 2 --days-ahead 2 || true
python -m app.cli ingest-openligadb --leagues bl1 bl2 || true

echo "=== [3/6] cohérence + logos ==="
python -m app.cli sweep-stale
python -m app.cli verify
python -m app.cli espn-media || true

echo "=== [4/6] analytics + prédictions + value bets ==="
python -m app.cli compute-analytics
python -m app.cli compute-predictions

echo "=== [5/6] serveur éphémère + instantané autonome ==="
uvicorn app.api:app --host 127.0.0.1 --port 8010 &
UVI=$!
for i in $(seq 1 30); do curl -sf http://127.0.0.1:8010/v1/stats >/dev/null && break; sleep 1; done
SNAPSHOT_BASE=http://127.0.0.1:8010 python make_snapshot.py
kill $UVI || true

echo "=== [6/6] publication ==="
mkdir -p ../dist
cp app/static/snapshot.html ../dist/index.html
ls -la ../dist/index.html
echo "=== pipeline CI terminé ==="
