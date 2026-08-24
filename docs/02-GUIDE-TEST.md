# PRONO SPORT — GUIDE DE TEST (M1 + M2) · 2026-08-24

## A. Tester l'interface (1 min)

Le panneau de prévisualisation **PRONO SPORT** est ouvert dans votre navigateur (port 8000).

1. Onglet **À VENIR** → les matchs réels d'aujourd'hui en tête (ex. Fulham vs Chelsea 19h00).
2. Onglet **TERMINÉS** → 710 matchs réels : scores, mi-temps, xG, arbitres lorsque la source les fournit.
3. Sur chaque carte : badge **✓ VÉRIFIÉ / ⚠ NON VÉRIFIÉ / ✕ SOURCES CONTRADICTOIRES** + pastilles des sources (`fduk`, `espn`, `openligadb`, `tsdb`).
4. Bandeau **SOURCES LIVE** en haut : santé et latence réelle de chaque fournisseur.
5. L'interface se rafraîchit toutes les 60 s ; le serveur re-synchronise ESPN toutes les 120 s.

## B. Tester l'API directement

```
http://localhost:8000/v1/docs                     ← documentation interactive (Swagger)
http://localhost:8000/v1/fixtures?tab=upcoming    ← matchs à venir (regroupés multi-sources)
http://localhost:8000/v1/fixtures?tab=finished&competition=ENG-E0   ← Premier League terminés
http://localhost:8000/v1/competitions             ← compétitions + nb de matchs
http://localhost:8000/v1/health/providers         ← DATA HEALTH (§75)
http://localhost:8000/v1/teams/21                 ← fiche équipe + alias
```

Dans une carte renvoyée par `/v1/fixtures`, vérifiez : `sources[]` (chaque fournisseur avec son score), `data_status`, `n_sources`.

## C. Prouver la non-dépendance aux sources

```bash
cd prono-sport/backend
export PYTHONIOENCODING=utf-8

# 1. Source 5 sans clé → échec propre, le reste fonctionne (§64)
python -m app.cli ingest-fdorg --competitions PL

# 2. Vérification croisée inter-sources (§4)
python -m app.cli verify

# 3. Idempotence : relancer la même ingestion = 0 doublon
python -m app.cli ingest-openligadb --leagues bl1 --years 2025   # attendu : skipped_unchanged ~ 306
```

## D. Prouver la qualité du code

```bash
cd prono-sport/backend
python -m pytest tests -q        # attendu : 30 passed
```

## E. Checklist §107 (état actuel, honnête)

| Exigence | État |
|---|---|
| Aucun match fictif | ✅ vrai — toute la base provient de sources publiques réelles, tracer possible (`raw_payload`) |
| Aucun doublon | ✅ testé (idempotence) |
| Validation des fixtures | ✅ 7 contrôles, rejets audités |
| Pas de fusion sur le nom seul | ✅ testé |
| Multi-sources + cohérence | ✅ moteur de cohérence actif |
| Cotes historisées | ✅ 11 900 snapshots (pré-match + clôture) |
| Modèles backtestés / Value Bet / No Pick | ⏳ Modules M4-M5 (pas encore construits) |
| Live temps réel + notifications | ⏳ M6-M8 |
| Monitoring complet, failover automatique | ⏳ partiel (provider_health), complet en M9 |
