# PRONO SPORT 3.0
## TECHNICAL MASTER PLAN — v1.0

> **LES DONNÉES D'ABORD. LES MODÈLES ENSUITE. LA DÉCISION EN DERNIER.**

| | |
|---|---|
| **Date** | 2026-08-26 |
| **Statut** | ✅ **VALIDÉ PAR L'UTILISATEUR (26/08/2026)** — contraintes ajoutées : application 100 % en français, **0 €** (aucune API payante), recherche approfondie en ligne par l'application elle-même sur sources publiques fiables |
| **Périmètre** | Plan technique complet (22 points) du prompt PRONO SPORT 3.0 §100 |
| **Règle absolue** | Aucune donnée inventée. Source inconnue = `DATA UNAVAILABLE`. |
| **Déroulé** | 26/08/2026 : plan livré → validé avec contraintes (FR, 0 €, recherche en ligne par l'app) → **alpha 3.0 construite en 2 itérations** : 130 matchs réels, **98 tests**, 4 value bets STRONG sur cotes réelles, Backtest Lab (Brier/LogLoss, modèle vs marché), providers compositions/blessures (API-Football free) + cotes live (The Odds API free), résolution non-destructive des pronos, interface FR 11 pages, workers journalisés + SSE + monitoring. Prochaines phases : alimentation des clés gratuites (lineups/cotes live actives), Postgres prod, calibration sur plus d'historique. |

---

## 0. CONTEXTE — ÉTAT DES LIEUX DE PRONO SPORT 2.0

Le dépôt contient déjà une plateforme **fonctionnelle et testée** (2.0) :

| Ce qui existe (2.0) | Détail |
|---|---|
| Backend | FastAPI + SQLAlchemy 2 (Python), API `v1` (12 routes), boucles de fond (ingest 300 s, live 75 s, compute) |
| Providers | 5 adapters : football-data.co.uk, ESPN, OpenLigaDB, TheSportsDB, football-data.org (optionnel) |
| Ingestion | Validation + rejets audités, résolution d'entités, moteur de cohérence multi-sources (VERIFIED / CONTRADICTORY) |
| Modèles | Poisson + Dixon-Coles + Elo (ensemble 70/30), anti-leakage, in-play Poisson restants |
| Value Bets | 1X2 + O/U 2.5, EV = P×O−1, marge retirée, `NO QUALIFIED PICK` |
| IA | Chat FR déterministe, réponses exclusivement sur données réelles |
| Tests | 59 tests automatisés |
| Déploiement | Docker, Koyeb, Hugging Face Spaces, GitHub Pages, Termux — **0 €** |
| UI | Une page statique `index.html` intégrée au backend |

### Décision stratégique (D5) : ÉVOLUER, PAS RÉÉCRIRE

3.0 conserve ce qui fonctionne (providers, ingestion, modèles, tests) et ajoute les moteurs manquants du cahier des charges 3.0. Une réécriture complète jetterait 59 tests validés et 5 providers opérationnels pour un coût sans retour. Le delta 2.0 → 3.0 est chiffré en **Annexe B**.

---

## 1. ARCHITECTURE

### 1.1 Diagramme de référence

```
┌─────────────────────────────────────────────────────────────────────────┐
│ FRONTEND (React + Vite + TS, mobile-first, SSE client)                  │
│ ACCUEIL · LIVE · À VENIR · TERMINÉS · COMPÉTITIONS · ÉQUIPES ·         │
│ JOUEURS · ANALYSES · VALUE BETS · PRONOSTICS · FAVORIS · ADMIN          │
└──────────────┬──────────────────────────────┬───────────────────────────┘
               │ REST /v1                     │ SSE /v1/events
┌──────────────▼──────────────────────────────▼───────────────────────────┐
│ API (FastAPI) ── AUTH (optionnelle, admin) ── RATE LIMIT ── VALIDATION  │
└──────┬─────────────────────────────────────────────────────────────┬────┘
       │                                                             │
┌──────▼──────────────┐   ┌────────────────────────────┐   ┌────────▼──────┐
│ DATA AGGREGATION    │   │ DATA QUALITY / FUSION      │   │ LIVE ENGINE   │
│ (adapters §68)      │──▶│ (validation, provenance,   │◀──│ (événements,  │
│ discovery engine    │   │  VERIFIED/CONFLICT,        │   │  in-play,     │
│ (source registry)   │   │  fraîcheur FRESH/STALE)    │   │  AVANT/APRÈS) │
└──────┬──────────────┘   └────────────────────────────┘   └────────┬──────
       │                                                             │
──────▼─────────────────────────────────────────────────────────────▼────┐
│ DATABASE (SQLite dev / PostgreSQL prod) — 33 tables, PRONO_INTERNAL_ID,  │
│ provenance (source_id, source_timestamp, retrieved_at) sur chaque ligne │
└──────┬─────────────────────────────────────────────────────────────┬────┘
       │                                                             │
┌──────▼──────────────┐   ┌────────────────────────────┐   ┌────────▼──────┐
│ ANALYTICS ENGINE    │   │ PREDICTION ENGINE          │   │ ODDS ENGINE   │
│ features, Elo, H2H, │──▶│ Poisson, Dixon-Coles, ML,  │◀──│ snapshots,    │
│ tactique, fatigue,  │   │ ensemble, calibration,     │   │ mouvement,    │
│ arbitre, météo      │   │ walk-forward, audit trail  │   │ multi-books   │
└─────────────────────┘   └────────────────────────────┘   └────────┬──────┘
                                                                    │
                                                      ┌─────────────▼──────────┐
                                                      │ VALUE BET ENGINE       │
                                                      │ edge, EV, gating,      │
                                                      │ NO QUALIFIED PICK      │
                                                      └─────────────┬──────────┘
                                                                    │
                                                      ┌─────────────▼──────────┐
                                                      │ AI EXPLANATION (jamais │
                                                      │ générateur de faits)   │
                                                      └────────────────────────┘
```

### 1.2 Organisation du monorepo

```
prono-sport/
├── backend/
│   ├── app/
│   │   ├── api/          # routes FastAPI (split par domaine, schema pydantic)
│   │   ├── providers/    # adapters : FootballDataProvider, OddsProvider,
│   │   │                 #   WeatherProvider, HistoricalDataProvider, NewsProvider
│   │   ├── discovery/    # source registry, pipeline de découverte, reliability
│   │   ├── ingest/       # validation, fusion, résolution d'entités, rejets audités
│   │   ├── workers/      # workers nommés idempotents (§14) + journal sync_jobs
│   │   ├── live/         # moteur live : événements, in-play, transitions de statut
│   │   ├── analytics/    # features, Elo, H2H, tactique, fatigue, arbitre, météo
│   │   ├── ml/           # Poisson, Dixon-Coles, ML, ensemble, calibration, backtest
│   │   ├── odds/         # cotes : collecte, snapshots, mouvement, multi-bookmaker
│   │   ├── value/        # value bet engine : edge, EV, gating, décision
│   │   ├── chat/         # assistant IA (explication uniquement)
│   │   ├── admin/        # API admin : sources, sync, qualité, erreurs
│   │   └── db/           # 33 tables + migrations Alembic
│   └── tests/
├── frontend/             # React + Vite + TypeScript + Tailwind (Phase 15)
├── docs/                 # documentation technique (livrée à chaque phase)
├── deploy/               # Docker, Koyeb, HF Spaces
└── .github/workflows/    # CI : lint → typecheck → tests → build
```

### 1.3 Principes d'architecture (inviolables)

1. **Abstraction providers (§68)** : aucune route ni modèle n'appelle une source externe directement ; toujours via un adapter. Retirer une source = désactiver un registry entry.
2. **Provenance totale (§57)** : chaque ligne de données porte `source_id`, `source_timestamp`, `retrieved_at`. Chaque entité porte un `PRONO_INTERNAL_ID` + les IDs externes des sources (`entity_mappings`).
3. **Étiquettes de données** : `SOURCE DATA` · `CALCULATED DATA` · `MODEL ESTIMATE` — affichées dans l'UI et dans l'API.
4. **États de fraîcheur (§11)** : `FRESH` · `STALE` · `UNKNOWN` · `INVALID` (+ `DATA DELAYED` affiché, jamais d'ancienne donnée présentée comme temps réel).
5. **Zéro donnée inventée (§2, §96)** : toute absence est rendue par un état explicite (`DATA UNAVAILABLE`, `INSUFFICIENT DATA`, `DATA CONFLICT`), jamais par une valeur plausible.

---

## 2. STACK

| Couche | Choix | Justification |
|---|---|---|
| Backend | **Python 3.11+ / FastAPI** | Base 2.0 existante, testée, en production ; l'écosystème ML est natif Python |
| ORM / migrations | **SQLAlchemy 2 + Alembic** | Alembic ajouté : 33 tables exigent un versionnement de schéma |
| Base de données | **SQLite** (défaut) / **PostgreSQL** (prod scale) | 0 € par défaut ; Postgres gratuit dispo (Supabase/Neon free tier) si montée en charge |
| Numérique / stats | **numpy + scipy** (existants) + **scikit-learn** (nouveau, ML/calibration) | Pas de dépendance payante |
| ML | **scikit-learn** (gradient boosting) ; **LightGBM** optionnel | Walk-forward + calibration exigés (§34-36) |
| Temps réel | **SSE (Server-Sent Events)** | Simple, traversé par tous les proxies (Koyeb/HF), unidirectionnel = suffisant pour du push scores/événements. WebSocket uniquement si un besoin bidirectionnel apparaît |
| Workers | **Boucles async in-process** (existantes), structurées en workers nommés idempotents journalisés | 0 € ; abstraction `Worker` permettant un futur passage à une file (RQ/Celery) sans réécriture |
| Frontend | **React 18 + Vite + TypeScript + Tailwind CSS** | Mobile-first, rapide à builder, servi en statique par l'API (aucun 2e hébergement) |
| Graphiques | **ECharts** (cotes, calibration, poss., xG) | Gratuit, léger, responsive |
| Cache | **Cache mémoire + disque avec ETag / Last-Modified / content-hash** (§65) | Pas de Redis obligatoire en 0 € ; Redis seulement si multi-instance |
| Tests | **pytest** (existant) + **ruff** (lint) + **mypy** (typecheck) | Pipeline CI complet (§92) |

**Décisions écartées (documentées)** : Next.js (SSR inutile — pas de SEO requis, et complexité de déploiement gratuit) · Node.js (abandon de la base de code testée) · Postgres obligatoire (contrainte 0 €).

---

## 3. BASE DE DONNÉNES

### 3.1 Schéma complet — 33 tables exigées (§58)

**Existantes en 2.0 (16)** : `data_sources`, `provider_health`, `competitions`, `seasons`, `teams`, `team_aliases`, `entity_mappings`, `fixtures`, `bookmakers`, `markets`, `odds_snapshots`, `ingestion_rejects`, `model_versions`, `predictions`, `value_bets`, `team_analytics`.

**À créer en 3.0 (17)** :

| Table | Contenu clé |
|---|---|
| `continents` | id, nom |
| `countries` | id, nom, continent_id |
| `rounds` | id, competition_id, season_id, round_num, label |
| `venues` | id, nom, ville, pays, capacité, lat/lng (→ météo) |
| `players` | id, nom, date_naissance, poste, nationalité + external source IDs |
| `player_aliases` | nom alternatif / source → mapping dedup |
| `coaches` | id, nom, période par équipe, style (si source) |
| `referees` | id, nom + moyennes cartons/pénalités (si source) |
| `fixture_events` | id, fixture_id, minute, type (goal, yellow, red, sub, penalty, var…), actor, team, source, timestamp |
| `lineups` | id, fixture_id, team_id, numéro, player_id, position, statut (starting/sub) |
| `team_statistics` | id, fixture_id, team_id, as_of, possession, tirs, tirs_cadrés, corners, fautes, cartons, xg, xga… |
| `player_statistics` | id, fixture_id, player_id, minutes, buts, passes, tirs… (PARTIAL par source) |
| `injuries` | id, player_id, type, gravité, retour_estimé, source, statut |
| `suspensions` | id, player_id, cause, matchs, source |
| `weather` | id, venue_id, at, température, pluie, vent, humidité, source (Open-Meteo) |
| `analysis_reports` | id, fixture_id, modèle, version, rapport JSON (Expert Report), created_at |
| `prediction_snapshots` | id, prediction_id, minute, probas avant/après (in-play AVANT→APRÈS), trigger |
| `sync_jobs` | id, worker, started_at, finished_at, status, records_in, records_out, errors, detail |
| `data_quality` | id, competition_id, as_of, score 0-100, fraîcheur, couverture, nb_sources, manquant |
| `notifications` | id, user_id, type (MATCH_START, GOAL, LINEUP, ODDS_CHANGE, VALUE_BET…), payload, read |
| `users` | id, email, hash, rôle (viewer/admin) — auth optionnelle |
| `favorites` | user_id, type (team/player/competition/fixture), ref_id |

### 3.2 Conventions

- **Identifiants (§59)** : `PRONO_INTERNAL_ID` = PK integer par table ; les IDs externes vivent dans `entity_mappings` (table, source_id, external_id) — une source ne peut jamais imposer son ID au schéma.
- **Déduplication (§60)** : normalisation de noms + similarité (Jaro-Winkler) + croisement des IDs externes ; tout doublon suspect génère un enregistrement audité, jamais une merge silencieuse.
- **Intégrité** : FK + index sur `(fixture, team)`, `(source, external)`, `as_of` ; purge contrôlée (jamais de `DELETE` non journalisé).
- **Migrations** : Alembic versionnées ; le schéma 2.0 existe déjà → migration 0001 de base + une migration par phase.

---

## 4. ARCHITECTURE TEMPS RÉEL

### 4.1 Workers (§14, priorités §10)

| Worker | Fréquence | Priorité |
|---|---|---|
| `syncLiveMatches` | 75 s (existant) | **P1** — score, minute, événements |
| `syncFixtures` | 5 min (hier/auj./demain) | **P2** — nouveaux/changements de matchs |
| `syncResults` | 5 min | **P2** |
| `syncLineups` | 15 min (fenêtre pré-match) | **P4** |
| `syncOdds` | 15 min (soumis aux crédits gratuits) | **P5** |
| `syncContext` (injuries/suspensions/refs) | 15-30 min | **P6** |
| `syncWeather` | 1 h (avant chaque match du jour) | **P6** |
| `syncHistoricalData` | quotidien (cron) | **P7** |
| `discoverSources` | hebdomadaire | **P8** |

**Chaque worker est** : idempotent (ré-exécuter = même état), réessayable (backoff exponentiel, max 5), journalisé (`sync_jobs`), monitoré (panneau Admin), tolérant aux erreurs (une source morte ≠ crash ; failover §64).

### 4.2 Flux temps réel

```
Provider ─▶ Worker ─▶ Ingest/Validation ─▶ DB ─▶ EventBus (in-process)
                                                    │
                              ┌─────────────────────┼──────────────────────┐
                              ▼                     ▼                      ▼
                          SSE /v1/events      Recompute in-play       Notifications
                          (score, minute,     (si données dispo)      (histo + SSE)
                           goal, card, sub,
                           lineup, value_bet,
                           prediction_change,
                           match_end)
```

- **Transitions de statut (§13, §15)** : `SCHEDULED → UPCOMING → LIVE → HALFTIME → EXTRA_TIME → PENALTIES → FINISHED` + `POSTPONED / CANCELLED / SUSPENDED / ABANDONED / UNKNOWN`. Chaque transition est un événement journalisé.
- **Détection LIVE** : un match passant en `LIVE` déclenche automatiquement la boucle 75 s + le push SSE (existant, à formaliser).
- **In-play (§53)** : après événement majeur (but, rouge, pen), recalcul des probabilités **uniquement si les données le permettent** ; sinon pas de recalcul (pas de fausse précision). Snapshot `prediction_snapshots` : `AVANT → APRÈS`.
- **Fin de match (§17)** : données finales → snapshot final → **résolution des pronostics (WIN / LOSS / VOID / PENDING)** → stats de performance → le match bascule en TERMINÉS. **La prédiction originale n'est jamais modifiée rétroactivement** (§54).
- **Freshness (§11)** : seuil de fraîcheur par catégorie (live : secondes/minutes ; odds : minutes ; historique : jours). Au-delà → `STALE`, affiché `DATA DELAYED`.

---

## 5. SOURCE DISCOVERY ENGINE

### 5.1 Pipeline de vie d'une source

```
DISCOVERED ─▶ TEST ─▶ VALIDATE ─▶ CLASSIFY ─▶ QUALITY CHECK ─▶ APPROVE / REJECT
```

- **TEST** : fetch réel, parsing, conformité schéma, échantillonnage de couverture.
- **VALIDATE** : accessibilité, robots.txt (lorsqu'applicable), conditions d'utilisation, restrictions d'accès automatisé, attribution requise. Si interdiction d'usage automatisé ou restriction incompatible → **`SOURCE_NOT_ALLOWED`** (jamais de contournement §5).
- **CLASSIFY** : catégories de données, couverture, fréquence.
- **QUALITY CHECK** : fraîcheur, erreurs, cohérence sur plusieurs cycles d'observation.
- **APPROVE** : inscription au registry avec statut `AVAILABLE` + fiabilité **initiale basse**, qui ne monte qu'avec l'observation.

### 5.2 Champs du registry (table `data_sources`, déjà existante — extension)

`source_id`, `source_name`, `source_url`, `source_type`, `data_categories`, `coverage`, `update_frequency`, `last_successful_fetch`, `last_failed_fetch`, `reliability_score`, `availability_status`, `terms_status`, `attribution_required`, `last_checked`, + `status` (`DISCOVERED/TESTING/VALIDATED/APPROVED/REJECTED/NOT_ALLOWED/DOWN`) et `priority_failover_rank`.

### 5.3 Source Reliability Engine (§8)

Score **calculé uniquement à partir de l'observé** (jamais inventé) :

```
reliability = 0.35 × taux_de_succès_30j
            + 0.25 × exactitude_crosscheck      # accord avec les autres sources
            + 0.20 × fraîcheur_observée
            + 0.15 × stabilité (variance latence/erreurs)
            + 0.05 × couverture_cible
```

Une source nouvellement découverte est **toujours `TRUST=LOW`** jusqu'à N cycles d'observation valides. Toute baisse est détectée → tentative de failover (§64) ; source disparue → `DATA UNAVAILABLE` si aucune source de repli.

---

## 6. STRATÉGIE D'AGRÉGATION MULTI-SOURCES

### 6.1 Interfaces (adapters)

```python
class FootballDataProvider:  fixtures, live, results, lineups, stats, events
class OddsProvider:          prematch, live, snapshots
class WeatherProvider:       current, forecast_at(venue, at)
class HistoricalDataProvider:depth(competition) -> (season_min, season_max)
class NewsProvider:          (stub Phase 3 — aucune source non vérifiée)
```

### 6.2 Matrice de redondance (v1, ajustée par le Coverage Center)

| Donnée | Primaire | Cross-check | Remarque |
|---|---|---|---|
| Fixtures / résultats | football-data.co.uk | ESPN, OpenLigaDB (DE), football-data.org | existant (2.0) |
| Live (score/minute/évén.) | ESPN | football-data.org (delayed, si clé) | ESPN non-officiel → jamais seul pour un match sensible |
| Compositions | API-Football (optionnel, 100 req/j) | — | sinon `LINEUP UNAVAILABLE` |
| Historique profond | football-data.co.uk | StatsBomb Open Data (sélection), Kaggle (au cas par cas) | matrice §8 |
| xG | football-data.co.uk (2017+, top 5) | StatsBomb (sélection), Understat (EPL, risque) | jamais de xG inventé |
| Météo | Open-Meteo | — | gratuit, sans clé |
| Cotes pré-match | football-data.co.uk (~20 books) | The Odds API (crédits gratuits) | multi-bookmaker réel |
| Cotes live | The Odds API (crédits) | — | sinon `ODDS LIVE UNAVAILABLE` |
| Joueurs | API-Football (optionnel) | TheSportsDB (basique) | `PARTIAL` affiché |

### 6.3 Fusion (§7)

Chaque valeur fusionnée conserve : `fixture_id`, `source_ids[]`, `source_timestamps[]`, `confidence`, `validation_status` (`VERIFIED` / `DATA_CONFLICT` / `SINGLE_SOURCE`), `normalized_value`. **Règle de résolution documentée** : en cas de conflit, les deux valeurs sont conservées avec leur provenance ; aucune n'est arbitrairement choisie ; l'UI affiche `DATA CONFLICT` et le modèle refuse de se positionner sur ce champ.

---

## 7. STRATÉGIE DE VALIDATION

1. **Validation d'ingestion** (existant) : champs requis, valeurs impossibles (score < 0, date future > horizon), statuts incohérents → rejet **audité** dans `ingestion_rejects` (quoi, pourquoi, source, quand).
2. **Validation croisée multi-sources** : accord ≥ 2 sources → `VERIFIED` ; désaccord → `DATA CONFLICT` (§6.3) ; 1 seule source → `SINGLE_SOURCE` (affiché comme tel).
3. **Vérification d'existence du match (§12)** : un match n'est affiché « réel » que s'il est confirmé par au moins une source approuvée avec équipes, compétition, date et heure cohérentes. Sinon → `UNCONFIRMED`, invisible des listes publiques. **PRONO SPORT n'affiche jamais de match inventé.**
4. **NO FAKE DATA GATE (§72)** : test automatique bloquant — aucun endpoint de production ne peut renvoyer un match sans source valide (test inclus dans CI).
5. **Fraîcheur** : horodatage de chaque ligne + seuils par catégorie (§4.2) ; aucune donnée `STALE` n'est présentée comme temps réel.
6. **Étiquetage systématique** : `SOURCE DATA` / `CALCULATED DATA` / `MODEL ESTIMATE` sur chaque valeur renvoyée par l'API.

---

## 8. HISTORIQUE (profondeur réelle, jamais supposée)

| Source | Profondeur réelle | Périmètre |
|---|---|---|
| football-data.co.uk | **~1993 → saison en cours** (22 ligues européennes) | résultats, cotes ~20 books, arbitres, xG (2017+ pour top 5) |
| StatsBomb Open Data | saisons **sélectionnées** (ex. FA WSL, Women's WC 2023, sélections UCL/La Liga) | niveau événement + xG + lineups |
| OpenLigaDB | calendriers complets D1-D3 allemandes | saisons récentes |
| ESPN | historique **recent** (quelques saisons) sur ~55 ligues | fixtures/résultats, pas d'archive profonde |
| Kaggle / worldfootball.net | archives profondes **au cas par cas** (vérification Phase 3/7) | qualité non garantie → pipeline de découverte |

→ Pour chaque compétition, l'UI affichera la profondeur **réellement stockée** : `2015 → 2026`, `2020 → 2026`, ou `HISTORICAL DATA UNAVAILABLE` (§18). La couverture réelle dépend des sources, jamais d'un affichage marketing.

---

## 9. STATISTIQUES

| Donnée | Provenance gratuite réelle | État garanti |
|---|---|---|
| Statistiques équipe (tirs, possession, corners, fautes, cartons) | ESPN (live + fini), fduk (post-match) | `AVAILABLE` ligues majeures · `PARTIAL` autres |
| xG / xGA équipe | fduk (top 5, 2017+), StatsBomb (sélection) | `AVAILABLE` où la source existe, sinon `UNAVAILABLE` |
| Statistiques joueurs (buts, passes, minutes, cartons) | API-Football (optionnel 100 req/j), TheSportsDB (basique) | `PARTIAL` — jamais complété par estimation |
| Classements | fduk, ESPN, OpenLigaDB, fd.org | `AVAILABLE` ligues couvertes |
| Forme (5 derniers, buts, xG) | calculé sur données réelles stockées | `CALCULATED DATA` (existant) |
| Performance domicile/extérieur | calculé sur historique réel stocké | `CALCULATED DATA` |

Toute statistique est horodatée (`as_of`) et liée à sa source. **Pas de statistique sans source.**

---

## 10. MOTEUR STATISTIQUE & MODÈLES

### 10.1 Modèles

| Modèle | Statut | Notes |
|---|---|---|
| **Elo** (K=60, ajusté domicile) | existant (2.0) | mis à jour post-match sur résultats réels |
| **Poisson** (matrice de scores) | existant (2.0) | par compétition |
| **Dixon-Coles** (corr. basses scores) | existant (2.0) | par compétition |
| **xG model** | **nouveau** | activé **seulement si** xG réel ≥ seuil de profondeur pour la ligue ; sinon désactivé avec label (pas de xG inventé) |
| **ML (gradient boosting)** | **nouveau** | features timestampées (§33) |
| **Ensemble** | **nouveau** (formalisé) | pondérations **validées historiquement par walk-forward par ligue** — jamais de « 80 % IA + 20 % Poisson » arbitraire ; l'ensemble n'est utilisé que s'il bat le meilleur membre seul en backtest |

### 10.2 Pipeline ML (§32)

```
DATA (réelle, horodatée) ─▶ FEATURE ENGINEERING (features_version versionnée)
   ─▶ TRAINING ─▶ VALIDATION (temporal + walk-forward, §34 : aucune info post-prédiction)
   ─▶ CALIBRATION ─▶ BACKTEST (Backtest Lab, séparé de la production) ─▶ PRODUCTION (model_versions)
```

### 10.3 Calibration & suivi (§35)

Par `model_version` : **Brier Score, Log Loss, courbe de calibration, fiabilité par marché**, calculés sur l'historique réel. Une probabilité annoncée est donc évaluable historiquement.

### 10.4 Audit trail (§56)

Chaque prédiction : `fixture_id, timestamp, model_version, features_version, market, selection, probability, odds, fair_odds, edge, EV, confidence, data_quality, decision` — la prédiction est **immuable** après création (les mises à jour in-play créent des `prediction_snapshots`).

---

## 11. ODDS ENGINE

- **Collecte réelle** : fduk (~20 bookmakers, pré-match, actuel — existant) + **The Odds API** (gratuit 500 crédits/mois, ~40 books — **à ajouter, clé gratuite**) + API-Football (optionnel).
- **Snapshots** : `(fixture, market, bookmaker, selection, odds, timestamp)` dans `odds_snapshots` (existant) → courbe de mouvement `12:00 → 2.10 / 12:30 → 2.04 / …` affichée graphiquement.
- **Multi-bookmaker (§39)** : meilleure cote, moyenne, dispersion, mouvement, anomalies détectées — uniquement sur cotes réellement collectées. **Jamais de cote ni de bookmaker inventés** : marché sans cote réelle = `MARKET DATA UNAVAILABLE`.
- **Cotes live** : seulement si les crédits gratuits le permettent ; sinon `LIVE ODDS UNAVAILABLE` (le pré-match reste disponible).

---

## 12. VALUE BET ENGINE

### 12.1 Formules (documentées dans le code, §40)

```
implied_probability = 1 / odds
fair_odds           = 1 / P_model
edge                = P_model / implied_probability − 1
EV                  = (P_model × odds) − 1
```

avec **retrait de la marge** du bookmaker (normalisation des implied probabilities) — logique existante (2.0), à documenter et couvrir par tests.

### 12.2 Gating & décision (§41, §43, §44)

1. Analyser **tous les marchés réellement disponibles** (1X2, double chance, O/U, handicap, BTTS si cotes réelles existent) — **aucun marché par défaut** (pas d'Over 1.5 automatique).
2. Un pick est `QUALIFIED` seulement si : edge ≥ seuil **et** model confidence ≥ seuil **et** data quality ≥ seuil. Sinon → **`NO QUALIFIED PICK`** (état de premier niveau, jamais de pick forcé).
3. **Trois indicateurs distincts, jamais confondus (§48)** : `DATA QUALITY` (fraîcheur, couverture, sources, cohérence) · `MODEL CONFIDENCE` (dispersion des modèles, calibration) · `VALUE QUALITY` (edge, EV, stabilité de la cote).
4. Pour chaque match : `BEST QUALIFIED PICK` complet (marché, sélection, P modèle, P marché, fair odds, cote dispo, edge, EV, confiances, risques) **ou** `NO QUALIFIED PICK` explicite avec les raisons.

---

## 13. IA

### 13.1 Principe (§45)

```
VERIFIED DATA ─▶ STATISTICAL MODELS ─▶ ML MODELS ─▶ MARKET ANALYSIS ─▶ RESULTS ▶ AI EXPLANATION
```

**L'IA ne fabrique jamais une statistique, un score ou une probabilité.** Elle explique, synthétise, compare, contextualise, répond.

### 13.2 Architecture

- **Moteur déterministe (existant, 2.0)** : chat FR structuré qui répond **uniquement** à partir des données stockées (value bets, pronos, forme, Elo). Si la donnée manque → `DATA UNAVAILABLE`. C'est la brique de base garantie.
- **LLM optionnel (Phase 14)** : synthèse du *Expert Match Report* et réponses ouvertes, avec contexte strictement issu de l'API réelle, garde-fous de non-fabrication, clé **serveur uniquement** (.env). Si aucun LLM configuré → le mode déterministe reste actif (graceful degradation).

### 13.3 Expert Match Report (§46)

Généré **si les données sont suffisantes**, 20 sections (contexte, forme, historique, stats, attaque, défense, xG, absences, compositions, tactique, entraîneurs, fatigue, arbitre, météo, marché, évolution des cotes, probabilités, value bets, risques, conclusion) — chaque section affiche son étiquette de donnée ou `DATA UNAVAILABLE`.

---

## 14. FRONTEND

- **Stack** : React 18 + Vite + TypeScript + Tailwind CSS + ECharts ; servi en statique par FastAPI (1 seul déploiement) ; SSE client pour le live.
- **Mobile-first** : toutes les fonctions principales accessibles sur smartphone (§80).
- **Navigation** : `ACCUEIL · LIVE · À VENIR · TERMINÉS · COMPÉTITIONS · PAYS · CONTINENTS · ÉQUIPES · JOUEURS · ANALYSES · VALUE BETS · PRONOSTICS · FAVORIS · RECHERCHE · ADMIN`.
- **Match Center (§50, §51)** : logos, score, heure, compétition, stade, arbitre, météo, statut + 9 tabs : `APERÇU · LIVE · STATS · COMPOSITIONS · JOUEURS · TACTIQUE · COTES · ANALYSE · PRONOSTICS`.
- **Langage de la donnée (visible partout)** :
  - Badges : `SOURCE DATA` / `CALCULATED` / `MODEL ESTIMATE` ;
  - Fraîcheur : `FRESH` / `STALE` / `DATA DELAYED` ;
  - États vides **designés, pas masqués** : `DATA UNAVAILABLE` · `INSUFFICIENT DATA` · `DATA CONFLICT` · `VERIFIED DATA` ;
  - In-play : `AVANT → APRÈS` (ex. Home Win 47 % → 58 %) avec snapshot.
- **Transparence (§85)** : chaque analyse expose `DATA SOURCE · FRESHNESS · QUALITY · MODEL · VERSION · CONFIDENCE · MARKET DATA` (endpoint `/v1/fixtures/{id}/analysis` existant, à enrichir).
- **Recherche globale (§81)** : équipes, joueurs, compétitions, matchs, pays. **Favoris (§82)** : équipes, joueurs, compétitions, matchs. **Notifications (§83)** : `MATCH START · GOAL · RED CARD · LINEUP · ODDS CHANGE · VALUE BET · PREDICTION CHANGE · MATCH END` (SSE + historique persistant).

---

## 15. MONITORING (§91)

| Cible | Mécanisme |
|---|---|
| API | `/v1/health` (latence, requêtes), logs structurés |
| Sources | **SOURCE MONITOR** (Data Sources panel) : statut, dernière sync, erreurs, latence, fraîcheur, qualité, catégories — table `data_sources` + `provider_health` (existant) |
| Workers | `sync_jobs` : statut, durée, records, erreurs par exécution ; alerte sur échecs répétés |
| Live | latence détection LIVE → première mise à jour |
| Données | **DATA QUALITY SCORE** par compétition : fraîcheur, couverture, cohérence, nb sources, fiabilité, manquant |
| Modèles | Brier/LogLoss par `model_version` (recalcul périodique) |
| Erreurs | panneau Admin → `ERRORS` (rejets d'ingestion, failovers, erreurs workers) |

---

## 16. SÉCURITÉ (§78)

- **Secrets** : `.env` serveur uniquement + `.env.example` ; **aucune clé exposée au frontend** (§69).
- **Validation** : schémas pydantic sur toutes les entrées ; rejet strict des statuts inconnus.
- **Rate limiting** : `slowapi` sur l'API publique (défaut modéré, configurable) — et respect strict des rate limits des sources (10 req/min fd.org, 100/j API-Football, crédits The Odds API).
- **Auth/authorization** : optionnelle — rôle `viewer` (public) / `admin` (panneau Admin, sync manuelle, approbation de sources) par jeton ; désactivable en déploiement personnel.
- **Transport/infra** : HTTPS (fourni par l'hébergeur), sauvegardes DB quotidiennes (export SQLite / `pg_dump`), audit des dépendances (`pip-audit`), aucune exécution de code tiers non versionné.
- **Éthique sources** : robots.txt/CGU vérifiées avant approbation ; `SOURCE_NOT_ALLOWED` si incompatibilité ; **jamais de contournement de protection** (§5).

---

## 17. TESTS (§17, §72-77)

### 17.1 Suite existante (59 tests) — conservée

### 17.2 Tests obligatoires 3.0 (matrice)

| Test | Scénario | Résultat attendu |
|---|---|---|
| **NO FAKE DATA** (§72) | fixture sans source valide, production | rejetée / invisible (404) — **test bloquant de CI** |
| **DATA CONFLICT** (§73) | Source A = 2-1, Source B = 1-1 | `DATA CONFLICT`, deux valeurs conservées + provenance |
| **LIVE** (§74, env de test uniquement) | goal → card → substitution → halftime → fulltime | synchronisation complète, transitions de statut, snapshots, résolution des pronos |
| **ODDS** (§75) | nouvelle cote / variation / marché fermé / bookmaker indisponible / cote suspendue | snapshot correct, mouvement, états `MARKET CLOSED` / `SUSPENDED`, pas d'invention |
| **LINEUP** (§76) | lineup absente / lineup publiée | rien d'inventé / recalcul analyse + marché (pipeline LINEUP_UPDATE_EVENT) |
| **PROVIDER FAILURE** (§77) | source principale HS | failover sur source de repli validée ; si aucune → `DATA UNAVAILABLE` |
| **Anti-leakage** | feature postérieure à t₀ | exclue de la prédiction à t₀ (walk-forward) |
| **Calibration** | probabilités sur N matchs réels | Brier/LogLoss calculés et stockés |
| **Idempotence** | réexécution d'un worker | zéro doublon, zéro drift |
| **Freshness** | donnée trop ancienne | `STALE` / `DATA DELAYED`, jamais « live » |

### 17.3 CI/CD (§92)

`commit → lint (ruff) → typecheck (mypy) → tests (pytest) → security (pip-audit) → build (API + frontend) → staging → validation → production`. Pipeline GitHub Actions (existant, à étendre).

---

## 18. DÉPLOIEMENT (§90)

| Environnement | Usage | Coût |
|---|---|---|
| **DEVELOPMENT** | local / Codespaces / Termux (guide existant) | 0 € |
| **STAGING** | instance de test des sources et des workers (déploiement HF ou Koyeb séparé) | 0 € |
| **PRODUCTION** | Koyeb 👑 (guide existant) / HF Spaces / VPS / Railway / Render | 0 € (free tiers) |
| **DEMO** | mode UI clairement badgeé `DEMO DATA`, base séparée, jamais en contact avec la base de prod (§71) | 0 € |

- **Base 0 €** : toutes les sources vérifiées du présent plan sont gratuites ; l'hébergement free tier suffit au démarrage.
- **Évolution** : la stack (FastAPI + Postgres + SSE) s'installe sans changement sur VPS/Render/Railway/Koyeb/Cloud ; le passage SQLite → PostgreSQL est une variable d'environnement + migration.
- **Honnêteté** : un hébergement gratuit ne suffit **pas** à une collecte temps réel massive multi-sources ; le plan documente le point de bascule (VPS ~5-15 €/mois) en Annexe « coûts ».

---

## 19. LIMITES TECHNIQUES (honnêtes)

| Limite | Impact | Gestion |
|---|---|---|
| **Pas de source gratuite de compositions officielles pour tous les matchs** | lineups `UNAVAILABLE` pour la majorité des matchs | badge honnête ; API-Football (100 req/j gratuit) pour les matchs prioritaires |
| **Stats joueurs temps réel : aucune source gratuite fiable** | `PARTIAL` / `UNAVAILABLE` | jamais d'estimation |
| **xG temps réel : indisponible en gratuit** | xG = post-match seulement | label `POST-MATCH xG` |
| **Cotes live : plafonnées par crédits gratuits** (~16 req/j The Odds API free) | `LIVE ODDS UNAVAILABLE` hors fenêtre | snapshots pré-match + mouvement sur les matchs prioritaires |
| **ESPN = API non officielle** | peut changer sans préavis | cross-check systématique + failover + tests de contrat |
| **fd.org free : scores delayed, saison courante, 10 req/min** | pas de live ni d'historique par cette source | réservé au cross-check |
| **TheSportsDB free : limites par méthode** (ex. 3/jour « schedule day ») | usage restreint | metadata + cross-check badges seulement |
| **Rate limits gratuits** (100 req/j API-Football) | couverture plafonnée | file de priorité + cache agressif (§65) |
| **Historique mondial** | pas d'archive complète gratuite | matrice de profondeur réelle par compétition (§8) |

---

## 20. COÛTS ÉVENTUELS

**Baseline : 0 € / mois, durablement** (sources vérifiées + hébergement free tier).

Options payantes **optionnelles** (prix indicatifs à vérifier au moment de l'achat — aucune ne bloque la construction) :

| Besoin | Option | Ordre de prix | Impact si absent |
|---|---|---|---|
| Lineups + stats joueurs mondiales | API-Football Pro | ~19-29 $/mois | lineups/stats joueurs `PARTIAL`/`UNAVAILABLE` |
| Plus de cotes + live odds | The Odds API Pro | ~20-100 $/mois (crédits) | cotes live limitées |
| Plus de ligues fd.org (live officiel) | football-data.org paid | ~10 €/mois et + | cross-check limité à 12 compétitions |
| Serveur 24/7 dédié | VPS | ~5-15 €/mois | free tier (Koyeb/HF) suffisant au démarrage |
| Postgres managé | Supabase/Neon (free tier existe) | 0-10 $/mois | SQLite (suffisant single-instance) |

Chaque dépendance manquée est rendue au format : `MISSING DEPENDENCY` + raison + impact + solution + alternative gratuite réellement disponible (§95).

---

## 21. ALTERNATIVES GRATUITES (réellement disponibles)

| Besoin | Alternative gratuite | Limite |
|---|---|---|
| Fixtures/résultats mondiaux | ESPN (sans clé) | non-officiel |
| Historique + cotes multi-books | football-data.co.uk (CSV) | 22 ligues, xG top 5 |
| Live minute + événements | ESPN | non-officiel, ligues couvertes |
| Données événementielles + xG (sélection) | StatsBomb Open Data (GitHub) | compétitions sélectionnées |
| Calendriers DE | OpenLigaDB | Allemagne uniquement |
| Météo stade | Open-Meteo (sans clé) | non-commercial |
| Cotes multi-bookmakers | The Odds API (500 crédits/mois) | ~16 req/j |
| Cross-check badges/métadonnées | TheSportsDB (clé free) | limites par méthode |
| Archives profondes | Kaggle / worldfootball.net | qualité à vérifier au cas par cas (pipeline §5) |
| Hébergement | Koyeb / HF Spaces / GitHub Pages / Termux | free tiers |

---

## 22. ROADMAP 20 PHASES (avec checkpoints §94)

Légende : ✅ = déjà livré (2.0) · 🔶 = partiel · ⬜ = à faire (3.0)

| # | Phase | Statut 2.0 | Travail 3.0 | Livrable checkpoint |
|---|---|---|---|---|
| 1 | Architecture | 🔶 | Restructuration modulaire (workers/, discovery/, live/, value/, admin/), config centralisée, CI lint+typecheck | structure validée, CI verte |
| 2 | Database | 🔶 | **17 tables nouvelles + Alembic**, conventions d'IDs, déduplication | migrations jouables, tests de schéma |
| 3 | Source Discovery | ⬜ | registry étendu, pipeline DISCOVERED→APPROVED, reliability engine, catalogues candidats (Annexe A) | 3+ sources passées au pipeline |
| 4 | Data Aggregation | 🔶 | adapters **The Odds API** + **API-Football** (optionnels), matrice de redondance v1, cache ETag/Last-Modified | nouveaux adapters en test |
| 5 | Data Validation | 🔶 | règles de conflit formalisées, vérification d'existence des matchs, NO FAKE DATA gate | tests §72/§73 passants |
| 6 | Fixtures | ✅ | statuts complets (§13), transitions journalisées | suite live §74 |
| 7 | Historical Data | 🔶 | matrice de profondeur réelle par compétition, import StatsBomb Open Data | page HISTORIQUE par compétition |
| 8 | Live Engine | 🔶 | événements structurés (`fixture_events`), in-play AVANT→APRÈS, SSE, fin de match → résolution des pronos | E2E live en test |
| 9 | Statistics | 🔶 | `team_statistics`, xG multi-sources, `player_statistics` (PARTIAL honnête) | stats horodatées + provenance |
| 10 | Analytics | 🔶 | tactique match-up, fatigue/calendrier, arbitre (si dispo), météo horodatée | sections du rapport expert |
| 11 | Prediction Engine | 🔶 | ML walk-forward, calibration (Brier/LogLoss), ensemble validé historiquement, `xG model` conditionnel | courbes de calibration publiées |
| 12 | Odds Engine | 🔶 | The Odds API, snapshots multi-books, mouvement graphique, états marché | page COTES par match |
| 13 | Value Bet Engine | ✅ | multi-marchés réel, gating 3-indicateurs, `BEST QUALIFIED PICK` / `NO QUALIFIED PICK` | endpoint + page VALUE BETS |
| 14 | AI | 🔶 | Expert Report 20 sections, LLM optionnel (explication seulement), garde-fous | rapport par match |
| 15 | Frontend | 🔶 | **SPA React complète** : 15 pages, Match Center 9 tabs, SSE, recherche, favoris, notifications, mobile-first | build frontend vert |
| 16 | Admin | ⬜ | DATA SOURCES · SYNC · LIVE MONITOR · ODDS MONITOR · MODEL MONITOR · DATA QUALITY · ERRORES · PREDICTIONS · VALUE BETS | panneau accessible (rôle admin) |
| 17 | Tests | 🔶 | suite obligatoire §17.2 + CI/CD complet | 100 % des tests obligatoires passants |
| 18 | Performance | 🔶 | cache disque ETag, pagination, throttling SSE, métriques de latence | benchmark documenté |
| 19 | Security | ⬜ | rate limiting, auth optionnelle, backups, pip-audit | audit sécurité documenté |
| 20 | Deployment | ✅ | environnements DEV/STAGE/PROD + DEMO isolé, docs finales | production 0 € validée |

**Protocole de checkpoint (chaque phase)** : construire → tester → corriger → documenter → vérifier → présenter le résultat avec :

```
STATUS: COMPLETED | FAILED | BLOCKED
NEXT STEP: ...
```

Une phase `FAILED`/`BLOCKED` est arrêtée avec cause, impact et alternative — jamais simulée.

---

## ANNEXE A — FICHES SOURCES (vérifiées le 2026-08-26)

> Statuts : ✅ VALIDÉE (en production 2.0 ou vérifiée cette session) · 🔍 À VALIDER (entrée dans le pipeline Phase 3) · ⚠️ RISQUE (usage conditionnel)

### A1. football-data.co.uk — ✅ VALIDÉE (production 2.0)
- **Type** : CSV publics (pas d'API) · **Clé** : aucune
- **Données** : résultats, classements, cotes pré-match ~20 bookmakers, arbitres, xG/xGA (top 5 depuis 2017)
- **Couverture** : 22 ligues européennes (top 5 + 2e divisions) · **Historique** : ~1993 → saison courante
- **Fréquence** : mise à jour hebdomadaire (lors de la saison) · **Temps réel** : non
- **CGU** : usage personnel/académique recommandé — **à confirmer avant usage commercial**
- **Fiabilité observée** : très élevée (base historique de 2.0) · **Risques** : périmètre limité, rythme hebdo

### A2. ESPN (site.api.espn.com) — ✅ VALIDÉE (production 2.0)
- **Type** : JSON **non officiel** (endpoints publics du site) · **Clé** : aucune
- **Données** : fixtures, scores **live par minute**, événements, stats, logos, stades, ~55 ligues
- **Historique** : saisons récentes (pas d'archive profonde) · **Temps réel** : **oui**
- **CGU** : pas de documentation officielle ; endpoints non garantis
- **Fiabilité observée** : stable depuis des années (usage 2.0) · **Risques** : **peut changer sans préavis** → cross-check + tests de contrat + failover obligatoires

### A3. OpenLigaDB — ✅ VALIDÉE (production 2.0)
- **Type** : JSON · **Clé** : aucune · **Données** : calendriers complets D1-D3 allemandes · **Temps réel** : non
- **CGU** : open data · **Risques** : périmètre Allemagne uniquement

### A4. TheSportsDB — ✅ VALIDÉE (cross-check 2.0)
- **Type** : JSON · **Clé** : clé free publique (traditionnellement `3` ; la doc officielle cite actuellement `123` — **à vérifier en Phase 3**)
- **Données** : métadonnées (ligues, équipes, badges, joueurs basiques), événements datés
- **Limites free** : quotas par méthode (ex. `search_all_leagues` : 10 ; `schedule day` : 3/j) · **Temps réel** : non
- **CGU** : free API publique, limites documentées · **Risques** : quotas très bas → usage metadata seulement

### A5. football-data.org — ✅ VALIDÉE (vérifiée 2026-08-26)
- **Type** : JSON REST · **Clé** : gratuite (inscription)
- **Free tier** : **12 compétitions** (PL, La Liga, Bundesliga, Serie A, Ligue 1, UCL, Eredivisie, Primeira, Championship, Brasileirão, WC, Euro), **10 requêtes/min**, **scores delayed**, **saison courante uniquement** ; **sans** données joueurs, stats match, cotes au free
- **Temps réel** : non (delayed) · **CGU** : ToS football-data.org, token serveur
- **Fiabilité** : élevée (source établie) · **Rôle 3.0** : 6e couche de cross-check, jamais source primaire

### A6. Open-Meteo — ✅ VALIDÉE (production 2.0)
- **Type** : JSON · **Clé** : aucune (limite non-commerciale) · **Données** : météo actuelle/prévisions par lat-lng (stade, à l'heure du match)
- **Temps réel** : oui · **CGU** : gratuit non-commercial · **Risques** : quasi nuls

### A7. The Odds API — ✅ VALIDÉE (vérifiée 2026-08-26)
- **Type** : JSON REST · **Clé** : gratuite
- **Free tier** : **500 crédits/mois** (≈ 16 req/j ; les requêtes multi-marchés/multi-régions coûtent plusieurs crédits), ~40 bookmakers, 20+ sports
- **Temps réel** : non (polling REST uniquement, aucun streaming) · **Historique** : oui (coût credits multiplié)
- **CGU** : ToS the-odds-api.com · **Rôle 3.0** : cotes pré-match des matchs prioritaires + mouvement ; cotes live seulement si crédits suffisants

### A8. StatsBomb Open Data — ✅ VALIDÉE (vérifiée 2026-08-26)
- **Type** : JSON sur GitHub (fichiers) · **Clé** : aucune
- **Données** : niveau **événement** (3 400+ événements/match), **xG**, freeze frames, lineups ; packages Python/R officiels
- **Couverture** : **compétitions sélectionnées** (FA WSL, Women's WC 2023, sélections UCL/La Liga…) · **Historique** : oui (saisons sélectionnées) · **Temps réel** : non
- **CGU** : usage public/chercheurs · **Rôle 3.0** : profondeur événementielle + xG de référence

### A9. API-Football (API-Sports) — ✅ VALIDÉE (vérifiée 2026-08-26)
- **Type** : JSON REST · **Clé** : gratuite (inscription)
- **Free tier** : **~100 requêtes/jour**, **tous les endpoints** (fixtures, live scores, standings, **lineups**, stats, joueurs), couverture mondiale
- **Temps réel** : oui (live) · **CGU** : ToS API-Sports, clé serveur
- **Rôle 3.0** : source optionnelle n°1 pour **compositions** et stats joueurs des matchs prioritaires (budget 100 req/j géré par file de priorité + cache)

### A10. Understat — 🔍 À VALIDER (⚠️ RISQUE)
- **Type** : pages web (xG EPL/top 5) · **Clé** : aucune
- **Données** : xG/xGA post-match · **CGU** : pas d'API officielle, pas de licence explicite → **extraction web non recommandée** ; entrée au pipeline seulement si une autorisation d'usage est identifiée

### A11. worldfootball.net — 🔍 À VALIDER (⚠️ RISQUE)
- **Type** : CSV/HTML · **Données** : archives profondes de résultats mondiaux · **CGU** : non explicite → vérification obligatoire (Phase 3) ; rejet si incompatible

### A12. FBref — 🔍 À VALIDER (⚠️ RISQUE)
- **Type** : pages web (xG, stats) · **CGU** : dérivé FiveThirtyEight/ESPN, scraping non explicitement autorisé → par défaut **non utilisé** ; seulement si une source équivalente autorisée est trouvée

### A13. Kaggle (jeux de données football) — 🔍 À VALIDER (au cas par cas)
- **Type** : fichiers (CSV/parquet) · **Données** : archives historiques variées · **CGU** : licences par dataset (vérifier chacun) · **Rôle** : profondeur historique ponctuelle, **jamais source de données live**

---

## ANNEXE B — GAP ANALYSIS 2.0 → 3.0 (résumé)

| Exigence 3.0 | 2.0 | 3.0 |
|---|---|---|
| 33 tables DB | 16 tables | +17 tables, Alembic |
| Source discovery | providers codés en dur | registry + pipeline + reliability engine |
| Workers nommés idempotents journalisés | 3 boucles async | 9 workers + `sync_jobs` + Admin |
| Statuts complets §13 | partiel | transitions journalisées E2E |
| Événements structurés | score/minute seulement | `fixture_events` complet |
| Lineups / absences / joueurs | absent | tables + adapters (PARTIAL honnête) |
| Cotes live multi-books | pré-match fduk | + The Odds API + mouvement graphique |
| ML + calibration | Poisson/DC/Elo | + gradient boosting, walk-forward, Brier/LogLoss |
| Ensemble validé historiquement | 70/30 fixe | pondérations par backtest walk-forward |
| Frontend pro multi-pages | 1 page statique | SPA React 15 pages + Match Center 9 tabs |
| Admin | endpoint santé | 9 panneaux admin |
| Notifications / favoris / recherche | absent | SSE + tables |
| SSE temps réel | polling | SSE |
| Tests obligatoires §72-77 | 59 tests | + 10 tests obligatoires bloquants |
| Security (rate limit, auth, backups) | minimal | Phase 19 |

---

## ANNEXE C — REGISTRE DES DÉCISIONS

| # | Décision | Raison |
|---|---|---|
| D1 | Backend **Python/FastAPI conservé** (pas de split Node) | base 2.0 testée (59 tests) + écosystème ML |
| D2 | **SSE** plutôt que WebSocket | suffisant (push unidirectionnel), traverse les free tiers (Koyeb/HF) |
| D3 | **SQLite par défaut**, PostgreSQL optionnel prod | 0 € par défaut ; passage par variable d'env |
| D4 | **Baseline 0 €** ; sources payantes = options documentées | exigence §3 du prompt |
| D5 | **Évoluer 2.0, pas réécrire** | 59 tests + 5 providers opérationnels |
| D6 | **Alembic** dès la Phase 2 | 33 tables sans versionnement = risque |
| D7 | **React + Vite** (pas Next.js) | pas de SEO requis, 1 seul déploiement |
| D8 | **Pas de scraping** (Understat/FBref/worldfootball) tant que l'autorisation d'usage n'est pas vérifiée | §5 du prompt — ne jamais contourner |
| D9 | LLM **explication uniquement**, optionnel, clé serveur | §45 — l'IA ne fabrique jamais de données |
| D10 | **NO QUALIFIED PICK** est un état normal et affiché | §41/§44/§98 — jamais de pick forcé |

---

## STATUT DU PLAN

```
STATUS:      COMPLETED (plan technique livré — 22 points + 3 annexes)
FAKE DATA:   NONE (toutes sources vérifiées ou explicitement marquées À VALIDER / RISQUE)
NEXT STEP:   EN ATTENTE DE VALIDATION — répondre « # VALIDÉ — COMMENCE LA PHASE 1 »
```
