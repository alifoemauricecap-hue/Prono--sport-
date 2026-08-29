#!/bin/sh
# PRONO SPORT 3.0 — bootstrap MONDIAL par ÉTAPES (Render free / Koyeb / HF / VPS / Termux).
# Principe §88 "qualité avant quantité" + robustesse instance free (512 Mo) :
#   ÉTAPE A (quelques minutes) : matchs du jour/à venir + Big 5 historiques + modèles
#        -> l'application devient UTILE tout de suite (live, pronostics, value bets).
#   ÉTAPE B (arrière-plan, après)   : profondeur (reste des ligues, médias, recherche).
# Toutes les étapes sont idempotentes et `|| true` : une source KO n'arrête jamais le
# tout (§64 failover). Jamais de données inventées : seules des sources publiques réelles.
cd "$(dirname "$0")"
export PYTHONIOENCODING=utf-8

echo "[A1] BACKBONE MONDIAL — TheSportsDB eventsday : matchs du jour/du monde (1 requête, 0 €)..."
python -m app.cli ingest-tsdb-day --days 2 || true

echo "[A2] ESPN — ligues majeures J-2 à J+2 (live + à venir + logos)..."
python -m app.cli ingest-espn --world --conf UEFA --days-back 2 --days-ahead 2 || true

echo "[A3] fduk — Big 5 historiques + cotes multi-bookmakers (base modèles, 0 €)..."
python -m app.cli ingest-fduk --divs E0 D1 I1 SP1 F1 --seasons 2526 2627 || true
python -m app.cli ingest-fduk-fixtures || true

echo "[A4] logos RÉELS des équipes (ESPN media, 1 appel/ligue)..."
python -m app.cli espn-media || true

echo "[A5] cohérence + modèles + value bets (la valeur arrive vite)..."
python -m app.cli sweep-stale || true
python -m app.cli verify || true
python -m app.cli compute-analytics || true
python -m app.cli compute-predictions || true

echo "[A-OK] ÉTAPE A TERMINÉE — live, pronostics, value bets et logos disponibles sur les ligues majeures."

# ----------------------------------------------------------------------------
# ÉTAPE B : approfondissement (non bloquant, peut être interrompu sans risque)
# ----------------------------------------------------------------------------
echo "[B1] ESPN — reste de la couverture mondiale (CONMEBOL/CONCACAF/AFC/CAF/international)..."
python -m app.cli ingest-espn --world --days-back 3 --days-ahead 2 || true
python -m app.cli ingest-openligadb --leagues bl1 bl2 bl3 --years 2025 2026 || true

echo "[B2] fduk — profondeur historique (autres divisions + saisons)..."
python -m app.cli ingest-fduk --divs E1 E2 E3 EC SC0 SC1 SC2 SC3 D2 I2 SP2 F2 N1 B1 P1 T1 G1 --seasons 2526 2627 || true

echo "[B3] médias (logos) + recalcul après extension..."
python -m app.cli espn-media || true
python -m app.cli compute-analytics || true
python -m app.cli compute-predictions || true

echo "[B4] RECHERCHE APPROFONDIE par ligue (Wikipedia FR/EN, CC BY-SA, 0 €)..."
python -m app.cli world-research || true

echo "[B-OK] BOOTSTRAP MONDIAL COMPLET — toutes les sources gratuites exploitées."
