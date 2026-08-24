# PRONO SPORT 2.0 — DOCUMENT D'ARCHITECTURE (Livrable §108)

**Version :** 1.0 · **Date :** 2026-08-24 · **Statut :** EN ATTENTE DE VALIDATION AVANT IMPLÉMENTATION
**Contrainte budgétaire :** 0 € — sources de données publiques gratuites uniquement.

> Conformément à la §108 du cahier des charges, ce document présente **avant tout code** : architecture, diagramme des services, stack, fournisseurs, modèle de données, synchronisation, ML, Value Bet, live, écrans, API, sécurité, monitoring, coûts, roadmap. **Aucun module ne sera codé avant votre validation.**

---

## 1. ARCHITECTURE GÉNÉRALE

Pipeline conforme §2, adapté aux sources gratuites :

```
FOURNISSEURS PUBLICS GRATUITS (§4 ci-dessous)
        │
        ▼
PROVIDER ABSTRACTION LAYER  ← chaque fournisseur = un "adapter" remplaçable
        │
        ▼
INGESTION LAYER (workers Python planifiés)
        │
        ▼
DATA VALIDATION ENGINE      ← rejet des données incohérentes, jamais de complétion silencieuse (§1)
        │
        ▼
NORMALIZATION + ENTITY RESOLUTION (§5-6) ← IDs internes PRONO_SPORT_*, mapping N fournisseurs
        │
        ▼
EVENT STREAM (Redis Streams) ← GOAL_EVENT, ODDS_CHANGE, MATCH_STATUS_CHANGE… (§10)
        │
        ▼
DATA WAREHOUSE (PostgreSQL + Parquet/DuckDB, 0 €)
        │
        ▼
FEATURE STORE (tables versionnées, timestamps anti-leakage §21-22)
        │
        ▼
ANALYTICS / ML MODELS (Elo, Poisson, Dixon-Coles, ML) 
        │
        ▼
ENSEMBLE → CALIBRATION (walk-forward, §19-22)
        │
        ▼
ODDS ENGINE → VALUE BET ENGINE → DECISION ENGINE (§30-39, §99-100)
        │
        ▼
EXPLANATION ENGINE (données validées → explication ; jamais l'inverse §46)
        │
        ▼
API FastAPI (publique v1)
        │
        ▼
WEB Next.js (responsive : desktop + mobile)
```

## 2. DIAGRAMME DES SERVICES

```
┌─────────────────────────────────────────────────────────────┐
│                     PRONO SPORT 2.0                          │
├──────────────┬──────────────┬───────────────┬───────────────┤
│ ingestion-   │ odds-        │ scheduler     │ reconstructor │
│ worker       │ worker       │ (APScheduler) │ (audit §73)   │
├──────────────┴──────────────┴───────────────┴───────────────┤
│              Redis (cache + Redis Streams)                  │
├──────────────────────────────────────────────────────────────┤
│              PostgreSQL 16 (données + feature store          │
│              + model registry + audit)                       │
├──────────────────────────────────────────────────────────────┤
│  ml-service (Python) : Elo · Poisson · Dixon-Coles ·        │
│  Ensemble · Calibration · Decision · Explanation             │
├──────────────────────────────────────────────────────────────┤
│              api-service (FastAPI, v1)                       │
├──────────────────────────────────────────────────────────────┤
│              web (Next.js 14 — responsive)                   │
├──────────────────────────────────────────────────────────────┤
│  Prometheus + Grafana (self-hosté, 0 €)                      │
└──────────────────────────────────────────────────────────────┘
```

Choix structurant justifiés (§11 : « l'architecture doit être justifiée ») :
- **Un seul langage backend : Python** (API + ML + ingestion). Moins de services à maintenir, zéro friction entre Data Science et API.
- **Redis Streams** au lieu de Kafka/Redpanda : même sémantique événementielle (§10), 0 € de cluster, abstraction `EventBus` permettant la migration Kafka plus tard sans réécriture (§3 : « jamais irréversible »).
- **PostgreSQL + fichiers Parquet (DuckDB)** au lieu de BigQuery/Snowflake : warehouse columnar analytique gratuit sur disque, requêtable en SQL.
- **TimescaleDB écarté v0** : les `odds_snapshots` tiennent dans PostgreSQL partitionné à notre échelle ; réversible plus tard.

## 3. STACK TECHNIQUE

| Couche | Choix | Justification |
|---|---|---|
| Web | **Next.js 14 + React + Tailwind** | §11, responsive mobile, gratuit, déployable partout |
| Mobile | phase 9 (Flutter) | web responsive d'abord |
| Backend | **Python 3.12 + FastAPI** | API + ML dans un même langage |
| ML | **numpy, pandas, scikit-learn, scipy, statsmodels** | Poisson/Dixon-Coles/calibration ; XGBoost/LightGBM en phase 4 |
| DB | **PostgreSQL 16** | transactionnel + JSONB pour payloads bruts |
| Cache/Events | **Redis 7** | cache TTL (§93) + Streams (§10) |
| Warehouse | **Parquet + DuckDB** | historique analytique 0 € |
| Jobs | **APScheduler** | synchronisation par priorités (§9, §95) |
| Tests | **pytest, httpx, responses** | §67-68 |
| Monitoring | **Prometheus + Grafana** | §65, image Docker officielle gratuite |
| Packaging | **Docker Compose** | tout démarre d'une commande, 0 € |

## 4. FOURNISSEURS POTENTIELS (testés en direct le 2026-08-24)

Chaque fournisseur derrière la **Provider Abstraction Layer** (`interface Provider` + `registry`) — remplaçable sans réécriture (§3).

| Rôle | Fournisseur | Coût | Données | Statut test |
|---|---|---|---|---|
| **Football Data A** | **football-data.co.uk** (CSV publics) | 0 € | Résultats, arbitres, tirs, corners, cartons, fautes, **xG (HxG/AxG)**, **cotes réelles ~20 bookmakers + Max/Avg marché + closing odds**, ~20 pays, historique 1993→2026 | ✅ HTTP 200, CSV 2627 valide (ex. E1 14/08/2026, Wolves–Blackburn 2-2, HxG 1.97) |
| **Football Data B** | **football-data.org** v4 (tier gratuit) | 0 € (clé à créer, 10 req/min) | Fixtures, statuts, classements, scores, 189 compétitions | ✅ endpoint compétitions 200 ; 403 sans clé sur le reste → **clé gratuite à créer par vous** |
| **Équipes/Logos/Stades** | **TheSportsDB** (clé publique `3`) | 0 € | Identités, badges (logo_url §57), stades, joueurs de base | ✅ testé OK (Arsenal : badge + Emirates Stadium) |
| **Météo** | **Open-Meteo** | 0 €, sans clé | température, pluie, vent, humidité | ✅ testé OK (Lomé 27.9 °C) |
| **xG avancé** | **StatsBomb Open Data** (GitHub) | 0 € | événements + xG sur compétitions couvertes (sinon « DONNÉE NON DISPONIBLE » §97) | ✅ testé OK |
| **Odds appoint** | **The Odds API** | 0 € = 500 req/mois | cotes pré-match multi-bookmakers | ⚠️ quota faible → usage ciblé uniquement |
| **Elo** | **calcul interne** (football-data.co.uk) | 0 € | rating dynamique §16 | ClubElo instable au test → externe écarté |

**Conséquences honnêtes de la contrainte 0 € (§97 — pas de faux « monde entier ») :**
- **Live** : football-data.org gratuit = polling 10 req/min. Live « quasi temps réel » possible mais **pas** sur le monde entier simultanément — priorité §95. Latence réelle toujours affichée (§43).
- **Cotes live streaming** : indisponible gratuitement → **PRONO SPORT v1 = Value Bet pré-match** (cotes football-data.co.uk, enrichies The Odds API sur matchs ciblés). Marché live = phase 7, marqué « limité ».
- **Compositions officielles** : sources gratuites partielles → statut `LINEUPS_PENDING` si non fournies ; jamais d'invention (§26).
- **Profondeur historique affichée** : « Historique disponible : 1993–2026 selon compétition » (§13).

## 5. MODÈLE DE DONNÉES (PostgreSQL)

Tables v1 (§12) — chaque ligne portant données externes conserve `provider`, `provider_id`, `source_url`, `fetched_at`, `last_updated_at` (§47 traçabilité) :

```
countries, competitions, seasons, rounds, venues(?), teams, team_aliases,
players(?), fixtures, fixture_events, team_statistics, injuries(?), 
weather, odds, bookmakers, markets, odds_snapshots,
predictions, model_versions, model_outputs, value_bets, analysis_reports,
data_sources, data_quality, provider_health, entity_mappings, notifications(?)
```

(?) = alimenté seulement si une source gratuite le fournit — sinon `DONNÉE NON DISPONIBLE`.

Points clés :
- **`entity_mappings`** : `internal_id ↔ provider_X_id` — jamais de match par simple nom (§5-6).
- **`fixtures.status`** : enum complet §8 (SCHEDULED…UNKNOWN).
- **`odds_snapshots`** : `(fixture_id, bookmaker, market, selection, odds, status, timestamp)` append-only (§30).
- **`predictions`** : `fixture_id, created_at_timestamp, model_version, feature_version, input_snapshot(JSONB), probabilities, odds_snapshot_ref, decision, confidence` → **reproductibilité totale §73**.
- **`model_versions`** : governance §20 (dataset_version, metrics, calibration, perf par ligue/marché).

## 6. STRATÉGIE DE SYNCHRONISATION (§9, §95, §94)

Budget requêtes gratuit : football-data.org **600 req/h** (10/min) ; football-data.co.uk CSV = 1 téléchargement par fichier modifié.

| Priorité | Population | Fréquence |
|---|---|---|
| P0 LIVE | matchs `LIVE/HT` détectés | poll 60 s (6 compétitions max en parallèle par clé) |
| P1 | coup d'envoi < 2 h | 5 min |
| P2 | < 24 h | 1 h |
| P3 | futur lointain / terminés (jusqu'à confirmation §9) | 1×/jour |
| Historique | football-data.co.uk CSV | vérification quotidienne (HEAD) |
| Météo | stade J-0 | 1× le jour du match |

Chaque donnée : `last_updated_at` (§9). UI affiche « Mis à jour il y a X s » réelle (§43). Failover A→B→`DATA UNAVAILABLE` (§64), jamais de fausse donnée.

## 7. ARCHITECTURE ML (§16-22, §40, §101-102)

**Quantitative Brain** (Python, déterministe) — séparé du Reasoning Brain (§102) :

1. **TEAM POWER** : Elo interne (calculé sur historique football-data.co.uk) + forme pondérée **decay temporel** (§14) + force adversaire + domicile. Composantes conservées séparément (§16).
2. **GOALS** : Poisson bivarié puis **Dixon-Coles** (time-weighted, §17) ; paramètres estimés par max de vraisemblance (scipy). xG (HxG/AxG) en features quand disponible.
3. **ML** (phase 4) : Logistic Regression → LightGBM, **sélection par validation temporelle uniquement** (§18).
4. **ENSEMBLE** : combinaison pondérée par performance historique (Brier par ligue/marché) (§19).
5. **CALIBRATION** : Platt/isotonic sur fenêtre glissante (§22 walk-forward strict : aucune feature postérieure au timestamp de prédiction — test automatisé anti-leakage §67).
6. **Monte Carlo** : simulation des scores depuis la distribution Dixon-Coles pour Over/Under, BTTS, scores exacts (§40).
7. **CONFIDENCE ENGINE** (§39) : qualité données × calibration × accord modèles × échantillon × fraîcheur — affichée **séparément** de la probabilité (§49).
8. **MODEL GOVERNANCE** (§20) : registre `model_versions`, rollback possible, aucune modification silencieuse.

## 8. STRATÉGIE VALUE BET (§30-39, §83-85, §99-100)

- **P_market_fair** : probabilités implicites depuis football-data.co.uk (`MaxH/D/A`, `AvgH/D/A`, Pinnacle `PSH/PSD/PSA`, closing `PSCH…`), **marge retirée par normalisation proportionnelle (+ méthode Shin en option documentée)** — jamais 1/cote brute (§32).
- **EV = P_model × O − 1** ; Edge = P_model − P_fair (§33).
- **Robust Value Filter** (§34) : seuils quantitatifs écrits en config versionnée, ex. v0 : `EV ≥ +3 %`, `data_quality ≥ 80/100`, `agreement_inter-modèles ≥ seuil`, `cote fraîche < 24 h`, `marché identifié sans ambiguïté`, sinon **NO QUALIFIED PICK** (§37/§85 — obligatoire).
- **Niveaux** (§35) : NO VALUE (<+1 %) · POTENTIAL (+1 à +3 %) · QUALIFIED (+3 à +8 % + filtres) · STRONG (> +8 % + confiance ÉLEVÉE). Définitions figées dans `config/value_levels.yml`.
- **Best Pick Engine** (§36) : v1 compare **1X2, DC, DNB, O/U 0.5–4.5, BTTS** (cotes dispo dans CSV) ; handicaps asiatiques quand `AHh` renseigné. Jamais de choix 1X2 par défaut.
- **Backtest/Paper trading** : `backtest_lab` sur closing odds historiques (football-data.co.uk = le terrain idéal : ~30 ans de closing odds réels), KPI §69 (ROI, yield, drawdown, hit rate, calibration). Mode **PAPER BETTING** avant toute publication (§70).

## 9. ARCHITECTURE LIVE (§41-44)

- Détection : scheduler P0 interroge football-data.org `status=LIVE`.
- Chaque `MATCH_STATUS_CHANGE/GOAL_EVENT` → Redis Stream → **LIVE ENGINE** recalcule (score → nouvelle distribution Poisson live → 1X2/O-U/BTTS actualisés §41).
- Push UI : **SSE** (Server-Sent Events) — gratuit, natif navigateur (WebSocket possible plus tard).
- Latence affichée = `now − fetched_at` réelle (§43). Cote suspendue = jamais considérée disponible (§42).

## 10. ÉCRANS (§51-56, §44, §50)

Identité visuelle propre **PRONO SPORT** (aucune copie, §50). Navigation : ACCUEIL · EN DIRECT · À VENIR · TERMINÉS · COMPÉTITIONS · ÉQUIPES · ANALYSES · VALUE BETS · RECHERCHE.
- **Accueil** : LIVE NOW · UPCOMING · TOP ANALYSIS · QUALIFIED VALUE BETS · ODDS MOVERS · RECENT RESULTS (§52).
- **Match Center** (§44) : header logos réels TheSportsDB + score + météo Open-Meteo ; onglets APERÇU · LIVE · STATS · COTES · ANALYSE IA · HISTORIQUE (onglets indisponibles affichés « DONNÉE NON DISPONIBLE », §82).
- **Page PERFORMANCE** (§87) : sépare BACKTEST / PAPER / LIVE TRACK RECORD — aucune perte effacée.
- **Mode Simple & Mode Expert** (§78-79) ; admin /data-health & /models (§74-76) réservé.

## 11. API (§90-92) — FastAPI, préfixe `/v1`

`GET /v1/fixtures?date=&status=` · `/v1/fixtures/{id}` · `/v1/fixtures/{id}/live` · `/v1/fixtures/{id}/analysis` · `/v1/competitions` · `/v1/teams/{id}` · `/v1/odds/{fixture_id}` · `/v1/value-bets` · `/v1/predictions` · `/v1/performance` · `GET /v1/health/providers`.
Réponses avec `model_version`, `data_quality (§48)`, `confidence`, `updated_at` à chaque fois (§91). Cache Redis : fixtures TTL 24 h, live TTL 30 s, odds TTL 5 min (§93).

## 12. SÉCURITÉ & CONFORMITÉ (§88-89)

- Aucune clé en dur — `.env` (clé football-data.org gratuite à créer par vous, 2 min, aucune CB).
- Aucune donnée personnelle en v1 → privacy trivialement conforme (§89).
- Mentions : « moteur d'analyse probabiliste » (§86), avertissement 18+/jeu responsable selon juridiction de diffusion (§88), pages légales prévues.
- Respect des conditions des sources gratuites : pas de scraping interdit, uniquement endpoints/CSV publics autorisés.

## 13. MONITORING (§65-66, §75)

Prometheus + Grafana self-hosté : `api_latency`, `provider_latency`, `data_freshness_seconds`, `failed_requests_total`, `prediction_latency`, fraîcheur du dernier CSV. Dashboard DATA HEALTH (provider/status/latence/last_update/couverture §75) + alertes : « odds feed > 30 min », « provider indisponible », « fixture dupliqué » (§66).

## 14. COÛTS ESTIMÉS

| Poste | Coût |
|---|---|
| Données (toutes sources ci-dessus) | **0 €** |
| Hébergement développement (votre machine / ce workspace) | 0 € |
| Docker, PostgreSQL, Redis, Grafana | 0 € |
| Domaine + hébergement prod (phase 9, optionnel) | ~5–10 €/mois OVH/Railway — **hors périmètre v1** |
| **TOTAL v1** | **0 €** |

Suivi des quotas API en base (`provider_health`, §94) pour ne jamais dépasser le gratuit.

## 15. ROADMAP (§106 adaptée 0 €)

- **M1 — FONDATION** : repo, Docker Compose, schéma DB, Provider Abstraction, ingestion **football-data.co.uk** (historique réel E0–SP2…), validation+tests. ✅ testable immédiatement.
- **M2 — FIXTURES & SCORES** : adapter football-data.org (clé gratuite), statuts §8, UI Accueil/À venir/Terminés.
- **M3 — ANALYTICS** : Elo interne, features §21, decay §14, backfill historique.
- **M4 — MODÈLES** : Poisson → Dixon-Coles → calibration → walk-forward → métriques §68. Backtest Lab sur closing odds.
- **M5 — VALUE BETS v1** : Odds Engine, P_fair, EV, niveaux §35, Best Pick §36, page Value Bets + Performance §87.
- **M6 — LIVE** : statuts live football-data.org, LIVE ENGINE, SSE, Match Center §44.
- **M7 — EXPERT** : météo Open-Meteo §28, rapport expert §45, Explanation Engine §46, traçabilité §47.
- **M8 — IA conversationnelle §77** (contexte structuré anti-hallucination §103), notifications internes §60-61.
- **M9 — Échelle** : quotas multi-sources, failover testé §64, coverage map §96, éventuel mobile.

**Méthode (§108) : un module à la fois → tests → validation → module suivant. Jamais de gros code non testé.**

---

### ✅ PROCHAINE ÉTAPE

Sur votre **« GO »**, je livre le **Module 1 — FONDATION** : structure du projet + schéma PostgreSQL + Provider Abstraction + ingestion réelle football-data.co.uk + tests pytest verts. Ensuite vous validez, et on enchaîne.
