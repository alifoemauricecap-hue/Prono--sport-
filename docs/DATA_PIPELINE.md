# PRONO SPORT 3.0 — PIPELINE DE DONNÉES & ARCHITECTURE

> Chaîne de principe (§99 du cahier des charges) :
> `DONNÉES RÉELLES → VALIDATION DES SOURCES → FUSION → QUALITÉ → FEATURES → MODÈLES → CALIBRATION → MARCHÉ → PROBABILITÉS → VALUE → RISQUE → DÉCISION`

## Vue d'ensemble

```
SOURCES GRATUITES (0 €)
  fduk (CSV) · ESPN (JSON) · OpenLigaDB · TheSportsDB · Open-Meteo
  football-data.org (clé free) · Wikipedia (recherche) · StatsBomb (historique)
        │
        ▼
CACHE INTELLIGENT (PS_CACHE_DIR)
  clé = SHA-1(url + params) · cache frais servi sans réseau ·
  réseau KO + cache = dernier contenu réel servi (jamais de donnée inventée)
        │
        ▼
WORKERS (idempotents, journalisés dans sync_jobs)
  syncFixtures (5 min) · syncLiveMatches (75 s) · syncResults (5 min)
  syncWeather (1 h) · syncHistorical (quotidien) · discoverSources (hebdo)
        │
        ▼
INGESTION (validation + rejets audités + résolution d'entités)
  validate_fixture() → ingestion_rejects (audit)
  resolve_team/resolve_competition() → entity_mappings (dédup)
        │
        ▼
DATA FUSION (cohérence multi-sources)
  2 sources concordantes → VERIFIED · divergentes → CONTRADICTORY (les deux valeurs gardées)
        │
        ▼
BASE DE DONNÉES (33 tables, SQLite/PostgreSQL)
  fixtures · teams · competitions · odds_snapshots · team_analytics ·
  fixture_events · sync_jobs · data_quality · predictions · value_bets · …
        │
        ▼
ANALYTICS (Elo + forme 5 + features — 100 % calculé sur données réelles)
        │
        ▼
PREDICTION ENGINE (Poisson + Dixon-Coles + Elo, ensemble 70/30 documenté)
  entraînement strictement antérieur au match (anti-leakage)
  moins de 30 matchs d'historique → pas de prédiction (jamais de fiction)
        │
        ▼
ODDS ENGINE (cotes réelles multi-bookmakers, snapshots append-only)
        │
        ▼
VALUE BET ENGINE (marge retirée, edge, EV, niveaux POTENTIAL/QUALIFIED/STRONG)
  aucun seuil franchi → NO QUALIFIED PICK (jamais de pick forcé)
        │
        ▼
API (FastAPI) + SSE /v1/events
  /v1/fixtures · /v1/value-bets · /v1/quality · /v1/sources · /v1/reports/{id}
  /v1/search · /v1/chat · /v1/notifications · /v1/admin/sync/{worker}
        │
        ▼
FRONTEND (SPA statique, mobile-first, 100 % français)
  badges : SOURCE · CALCULÉ · MODÈLE · VÉRIFIÉ · CONFLIT · DONNÉE INDISPONIBLE
```

## Les 3 étiquettes de donnée (partout dans l'UI et l'API)

| Étiquette | Signification |
|---|---|
| `SOURCE DATA` | Donnée telle quelle d'une source (cotes fduk, météo Open-Meteo, xG, logo ESPN) — provenance affichée |
| `CALCULATED DATA` | Calculé par PRONO SPORT sur données réelles (Elo, forme 5, fatigue, H2H, Data Quality Score) |
| `MODEL ESTIMATE` | Estimation du modèle (probabilités 1X2/OU/BTTS, expected goals) — **jamais présentée comme une certitude** |

## États de données

`FRESH` · `STALE` (→ affiché `DATA DELAYED`) · `UNKNOWN` · `INVALID`
Disponibilité : `AVAILABLE` · `PARTIAL` · `UNAVAILABLE` (→ affiché `DONNÉE INDISPONIBLE`)

## Workers — contrat commun

Chaque worker est :
- **idempotent** : relancer = même état, zéro doublon (clés naturelles + comparaison champ à champ) ;
- **réessayable** : backoff, un échec n'arrête jamais la plateforme (§64 failover) ;
- **journalisé** : table `sync_jobs` (statut, records créés/maj/rejetés, latence, erreurs) ;
- **monitoré** : panneau Analyses → Synchronisations + `GET /v1/sync-jobs`.

## Priorité de collecte (§10)

1. Matchs **LIVE** (75 s) → 2. matchs **à venir** (5 min) → 3. **résultats** (5 min)
→ 4. **compositions** (quand publiées) → 5. **cotes** (15 min / selon crédits)
→ 6. **météo/contexte** (1 h) → 7. **historique** (quotidien) → 8. **découverte de sources** (hebdo)

## Temps réel (SSE)

- `GET /v1/events` : flux Server-Sent Events (pas de WebSocket nécessaire — push unidirectionnel).
- Événements poussés : `LIVE` (but/statut, déduits des changements de score réels), `VALUE_BET`,
  `PREDICTION_RESOLVED`, `SYNC_DONE`, heartbeat 25 s.
- Un but = **évolution observée** du score entre deux lectures d'une source → événement `DERIVED`
  (jamais un événement inventé) ; minute = minute réelle de la source.

## Découverte de sources (discovery engine)

Cycle de vie : `DISCOVERED → TESTING → VALIDATED → APPROVED` (ou `REJECTED` / `NOT_ALLOWED`).
- Fiabilité **calculée sur l'observé** (taux de succès, fraîcheur, latence) — une source nouvelle a
  fiabilité `null` (« non mesurable ») tant qu'elle n'a pas d'historique.
- `terms_status = FORBIDDEN` → `SOURCE_NOT_ALLOWED`, jamais utilisée, jamais contournée.
- Panneau : `GET /v1/sources` + page Analyses → Sources.

## Intégrité & audit

- Chaque prédiction : `model_version`, `feature_version`, `input_snapshot` (forces utilisées) — reproductible.
- Chaque rejet d'ingestion : `ingestion_rejects` (motifs + payload).
- Résolution des pronostics : table `prediction_results` **non-destructive** (la prédiction originale n'est jamais modifiée).
- Test `NO FAKE DATA` : aucun match sans source valide ne peut être servi (test de CI bloquant).

## Démarrage (0 €)

```bash
cd backend
pip install -r requirements.txt
python -m pytest tests -q                 # 88 tests
# Optionnel : pré-remplir le cache avec des données réelles (fourni dans tools/)
# PS_CACHE_DIR=../data/cache
python -m app.cli ingest-fduk --divs E0 SP1 --seasons 2526 2627
python -m app.cli ingest-fduk-fixtures    # matchs à venir + cotes réelles
python -m app.cli compute-analytics       # Elo + forme
python -m app.cli compute-predictions     # Poisson/DC/Elo + value bets
uvicorn app.api:app --host 0.0.0.0 --port 8000
```
