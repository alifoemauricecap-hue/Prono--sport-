#!/bin/sh
# PRONO SPORT 3.0 — bootstrap UNIVERSel MONDIAL (Koyeb / Render / HF / VPS / Termux).
# Remplit la base depuis les sources publiques (0 €) :
#   [1/6] backbone MONDIAL TheSportsDB eventsday (TOUS les matchs du monde, 1 requête/jour)
#   [2/6] ESPN catalogue mondial (57 ligues, 6 confédérations, J-3 à J+2)
#   [3/6] fduk (historiques profonds + cotes multi-bookmakers, 22 divisions)
#   [4/6] cohérence + logos réels
#   [5/6] analytics + prédictions + value bets
#   [6/6] recherche approfondie par LIGUE (Wikipedia FR/EN, 0 €)
# Idempotent : relançable sans casse. || true = une source KO n'arrête jamais le tout (§64).
cd "$(dirname "$0")"
export PYTHONIOENCODING=utf-8

echo "[1/6] BACKBONE MONDIAL — TheSportsDB eventsday : TOUS les matchs du monde (J-4 à J)... 1 requête/jour, 0 €"
python -m app.cli ingest-tsdb-day --days 5 || true

echo "[2/6] ESPN — catalogue mondial (57 ligues, 6 confédérations, J-3 à J+2)..."
python -m app.cli ingest-espn --world --days-back 3 --days-ahead 2 || true
python -m app.cli ingest-openligadb --leagues bl1 bl2 bl3 --years 2025 2026 || true

echo "[3/6] fduk — historiques vrais + cotes actuelles (22 divisions)..."
python -m app.cli ingest-fduk --divs E0 E1 E2 E3 EC SC0 SC1 SC2 SC3 D1 D2 I1 I2 SP1 SP2 F1 F2 N1 B1 P1 T1 G1 --seasons 2526 2627 || true
python -m app.cli ingest-fduk-fixtures || true

echo "[4/6] cohérence + logos réels..."
python -m app.cli sweep-stale || true
python -m app.cli verify || true
python -m app.cli espn-media || true

echo "[5/6] analytics + prédictions + value bets..."
python -m app.cli compute-analytics || true
python -m app.cli compute-predictions || true

echo "[6/6] RECHERCHE APPROFONDIE par ligue (Wikipedia FR/EN, CC BY-SA, 0 €)..."
python -m app.cli world-research || true

echo "[6/6] BOOTSTRAP MONDIAL TERMINE — données réelles prêtes."
