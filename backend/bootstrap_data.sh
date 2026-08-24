#!/bin/sh
# PRONO SPORT 2.0 — bootstrap universel (Koyeb / HF Spaces / VPS / Termux).
# Remplit la base depuis les sources publiques (0 €), calcule analytics + pronos.
# Idempotent : relançable sans casse. || true = une source KO n'arrête jamais le tout (§64).
cd "$(dirname "$0")"
export PYTHONIOENCODING=utf-8

echo "[1/5] fduk : historiques vrais + cotes actuelles (22 divisions)..."
python -m app.cli ingest-fduk --divs E0 E1 E2 E3 EC SC0 SC1 SC2 SC3 D1 D2 I1 I2 SP1 SP2 F1 F2 N1 B1 P1 T1 G1 --seasons 2526 2627 || true
python -m app.cli ingest-fduk-fixtures || true

echo "[2/5] ESPN (32 ligues, J-3 a J+2) + OpenLigaDB..."
python -m app.cli ingest-espn --leagues eng.1 eng.2 eng.3 eng.4 eng.5 eng.fa eng.league_cup esp.1 esp.2 ger.1 ger.2 ita.1 ita.2 fra.1 fra.2 por.1 ned.1 tur.1 bel.1 sco.1 gre.1 aut.1 den.1 nor.1 swe.1 usa.1 ksa.1 jpn.1 aus.1 bra.1 arg.1 col.1 mex.1 --days-back 3 --days-ahead 2 || true
python -m app.cli ingest-openligadb --leagues bl1 bl2 bl3 --years 2025 2026 || true

echo "[3/5] coherence + logos reels..."
python -m app.cli sweep-stale || true
python -m app.cli verify || true
python -m app.cli espn-media || true

echo "[4/5] analytics + predictions + value bets..."
python -m app.cli compute-analytics || true
python -m app.cli compute-predictions || true

echo "[5/5] BOOTSTRAP TERMINE — donnees reelles pretes."
