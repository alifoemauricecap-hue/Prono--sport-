# PRONO SPORT — TECHNICAL MASTER PLAN v2.0

> **LES DONNÉES D'ABORD. LES MODÈLES ENSUITE. LA DÉCISION EN DERNIER.**
>
> Plateforme professionnelle mondiale d'intelligence football.
> Document rédigé le **2026-08-29**, sources vérifiées ce jour par recherche web.
> Conforme au cahier des charges **PRONO SPORT 3.0 §100** (22 points) — en attente de validation (§101).

| | |
|---|---|
| **Contraintes utilisateur** | 100 % français · **0 €** (aucune API payante) · l'application fait elle-même sa recherche de sources publiques · déployable sur **Render** |
| **Règle absolue** | Aucune donnée inventée (§2). Absence = `DATA UNAVAILABLE`. Donnée calculée = `CALCULATED DATA`. Estimation modèle = `MODEL ESTIMATE`. Donnée source = `SOURCE DATA`. Démo = `DEMO DATA` (jamais en production). |
| **État du dépôt** | Alpha 3.0 fonctionnelle : backend FastAPI/Python, 8 providers, moteur de modèles, value bets, backtest, SSE, SPA française, **126 tests automatisés verts** (vérifiés le 29/08/2026). |
| **Décision d'architecture** | **Faire évoluer l'alpha, pas réécrire** (D5) : le socle providers + ingestion + moteurs + tests est validé ; le plan v2.0 organise la montée en production. |

---

## 0. SOMMAIRE DES 22 POINTS

1. Architecture · 2. Stack · 3. Base de données · 4. Temps réel · 5. Découverte des sources · 6. Agrégation · 7. Validation · 8. Historique · 9. Statistiques · 10. Modèles · 11. Cotes · 12. Value Bets · 13. IA · 14. Frontend · 15. Monitoring · 16. Sécurité · 17. Tests · 18. Déploiement · 19. Limites techniques · 20. Coûts · 21. Alternatives gratuites · 22. Roadmap.
Puis : **catalogue vérifié des sources**, sources exclues, et checkpoint de validation.

---

## 1. ARCHITECTURE

### 1.1 Chaîne de valeur (philosophie §99)

```
REAL DATA (providers)
   ↓
SOURCE VALIDATION (discovery engine, robots/CGU, tests de disponibilité)
   ↓
DATA AGGREGATION (adapters : FootballDataProvider / OddsProvider / WeatherProvider / News / Historical)
   ↓
DATA FUSION (normalisation + résolution + provenance conservée)
   ↓
DATA QUALITY (fraîcheur, couverture, cohérence, sources croisées)
   ↓
FEATURE ENGINEERING (features horodatées, anti-leakage)
   ↓
STATISTICAL MODELS (Elo · Poisson · Dixon-Coles · xG quand disponible)
   ↓
ML / ENSEMBLE (poids validés par walk-forward, jamais arbitraires)
   ↓
CALIBRATION (Brier · Log Loss · fiabilité des probabilités)
   ↓
MARKET ANALYSIS (cotes réelles, marge retirée, mouvement)
   ↓
PROBABILITY → VALUE ANALYSIS → RISK ANALYSIS
   ↓
DÉCISION : PICK · VALUE BET · NO QUALIFIED PICK (jamais de pick forcé)
   ↓
AI EXPLANATION (explique, ne fabrique rien)
```

### 1.2 Déploiement cible Render (un seul service au départ, 0 €)

```
┌────────────────────────────────────────────────────────────┐
│ RENDER WEB SERVICE (Docker, plan free, 0 €)                 │
│                                                            │
│  FRONTEND (SPA française servie en statique par FastAPI)   │
│  pages : Accueil · Live · À venir · Terminés · Compétitions│
│  Pays · Continents · Équipes · Joueurs · Analyses ·        │
│  Value Bets · Pronostics · Favoris · Recherche · Admin     │
│                                                            │
│  API FastAPI (/v1) ── AUTH admin optionnelle ── RATE LIMIT │
│  SSE /v1/events (buts, statuts, cotes, value bets)         │
│                                                            │
│  WORKERS INTERNES (boucles asynchrones idempotentes) :     │
│  syncFixtures · syncLiveMatches · syncResults · syncStats  │
│  syncLineups · syncOdds · syncWeather · syncHistorical ·   │
│  discoverSources · compute (analytics/modèles/value)       │
│                                                            │
│  SQLite (/data, disque persistant optionnel 0,25 $/Go)     │
│  ou reconstruction automatique au boot (bootstrap honnête) │
└────────────────────────────────────────────────────────────┘
        ▲                                ▲
        │ providers HTTP (cache intelligent, ETag/Last-Modified)
   Sources gratuites (§catalogue)   Open-Meteo (météo)
```

**Pourquoi un monolithe FastAPI plutôt que React + API séparée + worker séparé au démarrage :**
- Render free = **un seul service web** qui se met en veille après 15 min d'inactivité ; un worker séparé nécessite un service payant (7 $/mois). L'alpha intègre workers + API + frontend dans un seul processus : **0 €, un seul déploiement**.
- La SPA actuelle (vanilla JS/TS léger, mobile-first) est servie par FastAPI : zéro build, zéro nœud en production, démarrage rapide.
- Le code est **découpé en modules** (providers / ingest / ml / value / chat / admin) de sorte qu'une migration future vers frontend React + worker séparé + Postgres géré se fait module par module, sans réécriture.

### 1.3 Principes inviolables

1. **Abstraction providers (§68)** : route et modèle ne parlent jamais à une source externe directement ; tout passe par un adaptateur enregistré (`registry`). Retirer une source = basculer un registre, sans toucher au reste.
2. **Provenance totale (§57)** : chaque donnée porte `source_id`, `source_timestamp`, `retrieved_at`, `data_version`. Chaque entité a un `PRONO_INTERNAL_ID` + ses identifiants externes (`entity_mappings`).
3. **Étiquettes** visibles dans l'UI et l'API : `SOURCE DATA` · `CALCULATED DATA` · `MODEL ESTIMATE` · `DEMO DATA`.
4. **Fraîcheur (§11)** : `FRESH` · `STALE` · `UNKNOWN` · `INVALID` ; une donnée live trop ancienne devient `DATA DELAYED`, jamais présentée comme temps réel.
5. **Zéro invention (§2, §96)** : toute absence = état explicite (`DATA UNAVAILABLE`, `INSUFFICIENT DATA`, `DATA CONFLICT`, `MISSING DEPENDENCY`).
6. **Pronostics non destructifs (§54, §56)** : audit trail complet, prédiction originale figée, résolution WIN/LOSS/VOID/PENDING après le match.

---

## 2. STACK TECHNOLOGIQUE

| Couche | Choisi (v2.0, 0 €) | Alternative optionnelle | Pourquoi |
|---|---|---|---|
| Backend / API | **Python 3.11 + FastAPI + Uvicorn** | Node/TS ou Python+FastAPI (conforme §67) | Async natif, SSE, typage pydantic, écosystème scientifique (numpy/scipy) pour les modèles. |
| Frontend | SPA française (HTML/CSS/JS léger, composants) servie en statique | **React + Vite + TS + Tailwind** en Phase 15 (build statique servi par FastAPI : même service, 0 €) | Zéro build au départ, mobile-first, fluent. React prévu sans casser l'archi. |
| Base de données | **SQLite** (dev + Render free, fichier ou disque persistant) | **PostgreSQL 16** (Neon free 0,5 Go, ou Render Postgres) via SQLAlchemy (déjà abstrait) | SQLite = zéro coût, zéro dépendance ; l'ORM SQLAlchemy 2 rend le changement transparent. |
| Cache | Cache HTTP en base + mémoire (ETag, Last-Modified, content-hash) | **Redis** (Upstash free 10 k cmd/jour) en Phase 18 | Pas de dépendance externe au départ ; interface de cache déjà isolée. |
| Temps réel | **SSE** (`/v1/events`) : buts déduits des changements de score réels, statuts, cotes, value bets | WebSocket (Phase 18 si scalabilité) | SSE = unidirectionnel suffisant, passe partout, 0 coût. |
| Workers | Boucles async intra-processus journalisées (`sync_jobs`), idempotentes | Worker séparé Render (7 $/mois) si passage à l'échelle | Conforme §14 tout en tenant sur le free tier. |
| ML / Stats | numpy/scipy (Elo, Poisson, Dixon-Coles, Poisson in-play, calibration Brier/LogLoss, backtest walk-forward) | Service Python dédié + Gradient Boosting (scikit-learn) quand le volume de données réelles le justifie | Pas de « ML » cosmétique : le ML n'est activé que s'il bat le marché en backtest (§31). |
| IA explicative | Moteur déterministe français (gabarits à partir des données vérifiées) | Clé LLM gratuite optionnelle (Groq free tier) via interface `AIProvider` — la clé reste serveur | L'IA ne génère que des explications sur données réelles ; sans clé, le moteur déterministe fonctionne (§45). |
| Auth | `ADMIN_TOKEN` optionnel (en-tête `x-admin-token`) pour actions sensibles | Auth.js / JWT multi-utilisateurs en Phase 19 | Suffisant pour protéger sync/backup ; favoris en local storage puis comptes en Phase 19. |
| CI/CD | GitHub Actions (lint → tests → build) + `render.yaml` (déploiement 1 clic) | — | Existe déjà ; étendu aux 126 tests. |

---

## 3. BASE DE DONNÉES

SQLAlchemy 2 (l'alpha contient déjà ~35 tables). Schéma cible (§58), toutes les tables de données portent la provenance :

`countries · continents · competitions · seasons · rounds · venues · teams · players · coaches · referees · fixtures · fixture_events · lineups · team_statistics · player_statistics · injuries · suspensions · weather · data_sources · bookmakers · markets · odds · odds_snapshots · predictions · prediction_snapshots · model_versions · model_outputs · value_bets · analysis_reports · data_quality · sync_jobs · notifications · users · favorites · entity_mappings · source_findings`

Règles :
- **PRONO_INTERNAL_ID** (UUID) sur chaque entité + table `entity_mappings` pour les identifiants externes (ESPN id, fduk name-key, API-Football id, TSDB id…) → déduplication (§60) par matching nom + date + compétition, avec seuils de confidence et résolution manuelle possible.
- **Provenance** : `source_id`, `source_timestamp`, `retrieved_at`, `data_version`, `confidence`, `validation_status` (VERIFIED / CONFLICT / SINGLE_SOURCE / UNAVAILABLE).
- **Audit trail prédictions (§56)** : `fixture_id, timestamp, model_version, features_version, market, selection, probability, odds, fair_odds, edge, ev, confidence, data_quality, decision`. Jamais modifié a posteriori.
- **Odds history (§38)** : `odds_snapshots` horodatés → graphiques de mouvement (12:00 → 2,10 …).
- Migrations : script de création idempotent au boot (l'alpha le fait déjà) ; Alembic introduit avec Postgres en Phase 20.

---

## 4. ARCHITECTURE TEMPS RÉEL

- **Priorité de collecte (§10)** : 1) live · 2) matchs dans les prochaines heures · 3) à venir · 4) compositions · 5) cotes · 6) contexte (météo, arbitre, absences) · 7) historique · 8) découverte de sources.
- **Boucles** (ticks adaptatifs : plus un match est proche/chaud, plus on interroge souvent, dans la limite des quotas gratuits) :
  - `syncLiveMatches` toutes les ~60-75 s pendant les fenêtres de match ;
  - `syncFixtures` toutes les 5 min (calendrier, statuts) ;
  - `syncLineups` ~45 min avant le coup d'envoi (détecte `LINEUP_UPDATE_EVENT` → recalcul features → modèles → analyse) ;
  - `syncOddsLive` toutes les 3 h (budget The Odds API gratuit = ~16 requêtes/jour → réservé aux matchs du jour à forte confiance) ;
  - `syncWeather` (Open-Meteo, prévision 16 j, appel groupé par coordonnées) ;
  - `discoverSources` hebdomadaire.
- **Moteur live (§15)** : détection du passage SCHEDULED→LIVE→HALFTIME→…→FINISHED ; événements (buts, cartons, remplacements, pénalties, corners, tirs, possession…) **uniquement s'ils sont fournis par une source** (§16). Les buts sont déduits des transitions de score réelles ; aucun événement inventé.
- **Recalcul in-play (§53)** : modèle Poisson sur temps restant (score + minute + forces), probabilités AVANT → APRÈS affichées ; le recalcul n'est produit que si les données nécessaires sont présentes, sinon `INSUFFICIENT DATA`.
- **Fin de match (§17)** : snapshot final, stats finales, événements, résolution des pronostics (WIN/LOSS/VOID), mise à jour du track record, déplacement en TERMINÉS.
- **Diffusion** : SSE `/v1/events` alimente l'UI sans rechargement (§79).

---

## 5. MOTEUR DE DÉCOUVERTE DES SOURCES (FREE DATA DISCOVERY ENGINE)

Registre `data_sources` (§4) :

`source_id · name · url · type (api/json/csv/xml/web/feed) · categories · coverage · update_frequency · last_success · last_failure · reliability_score · availability_status · terms_status (ALLOWED / SOURCE_NOT_ALLOWED / UNKNOWN) · attribution_required · last_checked`

Pipeline de découverte (§4) : **DISCOVERED → TEST → VALIDATE → CLASSIFY → QUALITY CHECK → APPROVE/REJECT**.
- Une source découverte commence `DISCOVERED` avec `reliability_score = NULL` : elle n'est **jamais** traitée comme fiable automatiquement.
- Tests automatiques : accessibilité HTTP, respect robots.txt quand pertinent, fréquence de mise à jour observée, cohérence croisée avec les sources APPROVED (ex. un match 2-1 signalé 2-1 par A/B/C = VERIFIED ; A=2-1 vs B=1-1 = DATA CONFLICT, on conserve les deux et on applique la règle de résolution documentée).
- Fiabilité **calculée sur l'observé** (§8) : exactitude historique vs consensus, disponibilité (succès/échecs), fraîcheur réelle, taux d'erreur, couverture — jamais de score saisi à la main.
- Respect des sources (§5) : aucune source dont les CGU interdisent l'automatisation n'est utilisée (`SOURCE_NOT_ALLOWED`), aucun contournement de protection, aucun scraping non autorisé. Les sources « non officielles mais JSON publiques » (ESPN) sont utilisées en débit poli + cache, sous statut `terms_status = UNKNOWN` et affichées comme telles dans le Source Monitor ; elles restent remplaçables instantanément.

---

## 6. STRATÉGIE D'AGRÉGATION

- **Adapters** normalisés : `FootballDataProvider`, `OddsProvider`, `WeatherProvider`, `HistoricalDataProvider`, `NewsProvider` (§68). Chaque fournisseur = un module (ex. `providers/espn.py`), interchangeable.
- **Data Fusion Engine (§7)** : normalisation (noms d'équipes, dates UTC, scores, minutes), puis fusion. Chaque donnée fusionnée garde sa provenance (`source_ids`, `source_timestamps`, `confidence`, `validation_status`, `normalized_value`).
- **Multi-sources quand c'est possible** : un score présent chez plusieurs sources indépendantes → `VERIFIED` ; désaccord → `DATA CONFLICT` (jamais de choix arbitraire : règle documentée = priorité à la source dont la fiabilité observée est la plus haute ET au consensus, sinon la donnée reste marquée CONFLICT et n'est pas utilisée par les modèles).
- **Failover (§64)** : source A en panne → source B ; aucune source fiable → `DATA UNAVAILABLE`.
- **Cache intelligent (§65)** : ETag / Last-Modified / content-hash, intervalles adaptatifs, aucun téléchargement redondant.

---

## 7. STRATÉGIE DE VALIDATION

- **Validation des matchs (§12)** avant affichage : existence réelle, équipes, compétition, date/heure UTC, statut, source. Un match non confirmé n'est jamais affiché comme réel. Le test automatique **NO FAKE DATA** bloque en production tout match sans source valide.
- **Statuts (§13)** : SCHEDULED · UPCOMING · LIVE · HALFTIME · EXTRA_TIME · PENALTIES · FINISHED · POSTPONED · CANCELLED · SUSPENDED · ABANDONED · UNKNOWN.
- **Data Quality Score (§47)** par match/compétition : fraîcheur, couverture, cohérence, nombre de sources, fiabilité, données manquantes. **Data Quality ≠ Model Confidence ≠ Value Quality** : trois indicateurs séparés (§48).
- **Absences (§22)** : AVAILABLE / INJURED / SUSPENDED / DOUBTFUL / RETURNING / UNKNOWN — aucune absence inventée ; sans clé API-Football → `MISSING DEPENDENCY` affiché.
- **Couverture (§61)** : Coverage Center par compétition — Fixtures / Live / Results / Statistics / Lineups / Players / Historical / Odds / xG en AVAILABLE · PARTIAL · UNAVAILABLE.

---

## 8. HISTORIQUE

- **Colonne vertébrale : football-data.co.uk** (CSV libres) : ~22 ligues européennes, profondeur réelle (Big 5 jusqu'à **1993/94** pour certaines, 2000/01 pour la plupart), résultats + cotes de clôture de plusieurs bookmakers + stats récentes (tirs, corners, cartons, fautes). C'est la base du **backtest** et de la calibration (§35).
- **StatsBomb Open Data** : événements niveau match (xG réel, passes, tirs, compositions) pour compétitions sélectionnées (Coupes du monde, FAWSL, quelques ligues) — **historique seulement**, usage non commercial avec accord utilisateur. Sert à valider/calibrer les modèles de buts et les features xG, jamais de donnée live.
- **openfootball** : fichiers JSON domaine public (calendriers/résultats des ligues majeures), profondeur affichée réelle (ex. 2015→2026), communautaire.
- **Profondeur affichée honnêtement (§18)** : chaque compétition montre sa vraie profondeur (« 2015 → 2026 » ou « HISTORICAL DATA UNAVAILABLE »). Jamais de prétention à « toute l'histoire du football ».
- **H2H (§19)** : confrontations directes disponibles, pondérées par récence, domicile/extérieur, changement d'effectifs/entraîneurs ; les rencontres très anciennes ne sont pas surpondérées.

---

## 9. STATISTIQUES

Features (§33), toutes **horodatées** (calculées à partir des données connues au moment T, anti-leakage §34) :
- Équipes (§20) : classement, forme récente (pondérée), buts marqués/encaissés (dom/ext séparés), xG/xGA **si disponibles**, tirs, tirs cadrés, possession, corners, cartons, fautes, force de l'adversaire rencontré.
- Joueurs (§21) : matchs, minutes, buts, passes, tirs, cartons, titularisations/remplacements, forme — quand la source les fournit.
- Contexte (§24-29) : **changement d'entraîneur récent** (recherche web publique type Wikipedia, horodatée), style de jeu quand les stats le permettent (possession, pressing approximé par les fautes/tirs concédés, transitions, coups de pied arrêtés), **Tactical Matchup Engine** (forces/faiblesses croisées), **fatigue** (jours de repos, matchs récents, déplacements quand disponibles), **arbitre** (moyennes cartons/penalties quand l'historique existe — sinon `DATA UNAVAILABLE`), **météo** Open-Meteo (température, pluie, vent, humidité ; sinon `WEATHER DATA UNAVAILABLE`).
- **xG** : jamais estimé « pour faire joli » : xG source (StatsBomb/fduk récent) ou `DONNÉE INDISPONIBLE`. Les modèles fonctionnent sans xG (Poisson/DC/Elo sur buts).

---

## 10. MODÈLES (ANALYTICS ENGINE)

Implémentés (numpy/scipy), documentés dans le code :

| Modèle | Rôle | Données requises |
|---|---|---|
| **Elo** (avec bonus domicile, élasticité, marge de buts) | Force intrinsèque des équipes, évolue dans le temps | résultats |
| **Poisson** (buts domicile/extérieur, attaques/défenses ligue) | Matrice 1X2, over/under, BTTS | résultats + minutes jouées |
| **Dixon-Coles** | Correction faibles scores (0-0, 1-0, 0-1, 1-1) + pondération temporelle | mêmes données |
| **Poisson in-play** | Probabilités live sur temps restant (score + minute + forces) | match live + modèles pré-match |
| **xG model** | Si xG réel disponible sur la compétition | xG source |
| **Ensemble** | Combinaison pondérée ; **poids validés par walk-forward**, pas de « 80/20 » arbitraire (§31) | backtest |
| **ML (supervisé)** | Gradient boosting sur features ; activé **seulement** s'il bat les modèles simples et le marché en backtest, sinon il reste désactivé (pas de ML cosmétique) | volume suffisant |

Pipeline ML (§32) : DATA → FEATURES → TRAIN → VALIDATION → CALIBRATION → BACKTEST → PRODUCTION. **Validation temporelle walk-forward (§34)** : entraînement strictement sur les données antérieures au match prédit.
Calibration (§35) : **Brier Score, Log Loss, accuracy par marché, courbe de fiabilité**, modèle vs marché (cotes sans marge). Backtest Lab (§36) : par modèle, marché, saison, compétition, stratégie — backtest, paper tracking et live track record **séparés (§55)**, aucun taux de réussite fictif.

---

## 11. ODDS ENGINE (§37-39)

- **Cotes réelles uniquement** : provider The Odds API (clé gratuite, 500 crédits/mois) pour les cotes 1X2 et plus, multi-bookmakers (jusqu'à 40 books selon le sport/marché), rattachées aux matchs déjà en base (jamais un match créé depuis une cote).
- **Cotes historiques de clôture** : football-data.co.uk (Bet365, Pinnacle, Betfair, William Hill…) — base du backtest et de l'analyse de valeur de long terme (CLV).
- **Snapshots horodatés** (§38) : évolution 12:00→2,10 · 12:30→2,04… avec graphique de mouvement ; statut des cotes (ouverte/suspendue/fermée) géré (§75).
- **Multi-bookmaker (§39)** : meilleure cote, cote moyenne, dispersion, anomalies détectées. Aucun bookmaker ni aucune cote inventés.
- **Budget gratuit honnête** : 500 crédits/mois ≈ 16 requêtes/jour → la collecte live est réservée aux **matchs du jour priorisés** (fixtures à forte confiance) ; les cotes passées (fduk) couvrent l'historique à volonté. Au-delà, offre payante à partir de 30 $/mois (facultatif).

---

## 12. VALUE BET ENGINE (§40-44)

Pour chaque marché réellement disponible (1X2, double chance, over/under, BTTS, handicap si données — jamais de marché inventé) :

```
probabilité implicite du bookmaker = 1 / cote
retrait de la marge (surroundage) → probabilité marché « no-vig »
probabilité modèle = sortie calibrée de l'ensemble
fair odds = 1 / probabilité modèle
edge = P_modèle − P_marché
EV = (P_modèle × cote) − 1
```
- Gating documenté : niveau **POTENTIAL / QUALIFIED / STRONG** selon edge, EV, taille de l'échantillon, data quality, incertitude.
- **NO QUALIFIED PICK (§41)** si rien ne franchit les seuils : jamais de pronostic forcé, pas de « Over 1.5 par défaut » (§44).
- **Best Qualified Pick (§43)** par match : marché, sélection, P modèle, P marché, fair odds, cote dispo, edge, EV, model confidence, data quality, risques.
- Risques affichés : absences non confirmées, faible historique, marché à cote unique, donnée STALE.

---

## 13. IA (§45, §84)

- Rôle strict : **expliquer, synthétiser, contextualiser, répondre** — jamais inventer un fait.
- Chaîne : VERIFIED DATA → MODÈLES → MARKET ANALYSIS → RÉSULTATS → **AI EXPLANATION**. L'assistant ne reçoit que des données réelles (avec étiquettes) ; si une donnée manque, il répond « DONNÉE INDISPONIBLE » (§84).
- Implémentation : moteur déterministe français par défaut (gabarits sur les sections du rapport expert §46) ; clé LLM gratuite optionnelle (ex. Groq free) via `AIProvider`, clé uniquement serveur (`.env`, jamais exposée côté frontend).
- **Rapport expert (§46)** : 20 sections (contexte, forme, historique, stats, attaque, défense, xG, absences, compositions, tactique, entraîneurs, fatigue, arbitre, météo, marché, évolution des cotes, probabilités, value bets, risques, conclusion), chaque section badgée SOURCE / CALCULÉ / MODÈLE / INDISPONIBLE.

---

## 14. FRONTEND (§49-52, §79-83)

SPA 100 % française, mobile-first, fluide (pas de rechargement, SSE), déjà livrée en alpha et étendue :

- Navigation (§49) : ACCUEIL · LIVE · À VENIR · TERMINÉS · COMPÉTITIONS · PAYS · CONTINENTS · ÉQUIPES · JOUEURS · ANALYSES · VALUE BETS · PRONOSTICS · FAVORIS · RECHERCHE · MONDE (couverture réelle) · ADMIN.
- **Match Center (§50)** : logos, noms, score, heure, compétition, stade, arbitre, météo, statut.
- **Onglets (§51)** : APERÇU · LIVE · STATS · COMPOSITIONS · JOUEURS · TACTIQUE · COTES · ANALYSE · PRONOSTICS (9 onglets livrés).
- **Live UI (§52)** : score, minute, timeline, buts, cartons, remplacements, corners, fautes, tirs, possession — uniquement ce qui est reçu.
- **Pronostics live (§53)** : AVANT → APRÈS en pourcentages après événement important (si données suffisantes).
- **Favoris (§82)** et **notifications navigateur (§83)** : MATCH START, GOAL, RED CARD, LINEUP, ODDS CHANGE, VALUE BET, PREDICTION CHANGE, MATCH END.
- **Recherche globale (§81)** : équipes, joueurs, compétitions, matchs, pays.
- **Transparence (§85)** sur chaque analyse : source, fraîcheur, qualité, modèle + version, confiance, données de marché.
- Évolution optionnelle Phase 15 : refonte React + Vite + TS en build statique (toujours servi par le même service FastAPI → 0 €, même URL Render).

---

## 15. MONITORING (§62, §63, §91)

- **Source Monitor / DATA SOURCES** : source, statut, dernière synchro, erreurs, latence, couverture, fraîcheur, qualité, catégories, fiabilité observée.
- **Admin Panel (§63)** : DATA SOURCES · SYNC (déclenchement manuel des workers) · LIVE MONITOR · ODDS MONITOR · MODEL MONITOR · DATA QUALITY · ERRORS · USERS · PREDICTIONS · VALUE BETS · sauvegarde SQLite.
- **Healthcheck** : `/v1/health` pour Render ; métriques workers dans `sync_jobs` (durée, statut, erreurs, enregistrements traités).
- Surveillance : latence live, âge des données, compteurs d'erreurs par provider, quota restant des clés gratuites.

---

## 16. SÉCURITÉ (§78)

- Aucun secret côté frontend ; clés API uniquement en variables d'environnement serveur (`.env` + `.env.example` sans valeurs).
- `ADMIN_TOKEN` optionnel protégeant les actions sensibles (sync manuelles, backup) ; rate limiting API (300 req/min/IP dans l'alpha) ; validation pydantic de toutes les entrées ; logs d'erreurs sans fuite de secrets ; HTTPS fourni par Render ; sauvegardes base (export SQLite cohérent) ; en-têtes de sécurité.
- Environnements (§70) : DEVELOPMENT / STAGING / PRODUCTION via `APP_ENV` ; mode DEMO (§71) clairement banni en production et données de démo isolées.

---

## 17. TESTS (§72-77, §92)

126 tests automatisés verts aujourd'hui, dont la suite obligatoire 3.0 :
- **NO FAKE DATA** (un match sans source valide ne peut s'afficher en production) ;
- **DATA CONFLICT** (A=2-1 vs B=1-1 → CONFLICT, pas de choix arbitraire) ;
- **LIVE** : but, carton, remplacement, mi-temps, fin de match → synchronisation complète ;
- **ODDS** : nouvelle cote, variation, marché fermé, bookmaker indisponible, cote suspendue ;
- **LINEUP** : absence → rien inventé ; publication → recalcul ;
- **PROVIDER FAILURE** : source principale en panne → fallback ;
- **BACKTEST / calibration** : Brier, Log Loss, walk-forward anti-leakage ;
- **ADMIN / sécurité** : rate limit, token admin, backup ;
- **DÉPLOIEMENT** : parsing `render.yaml`, Dockerfile.
CI GitHub Actions : lint → tests → build (§92).

---

## 18. DÉPLOIEMENT (§90)

**Render (cible principale)** via `render.yaml` (blueprint 1 clic, déjà présent) :
- Service web Docker, plan **free 0 $**, healthcheck `/v1/health`, auto-déploiement depuis GitHub.
- Base : SQLite. Deux modes : (a) **disque persistant 10 Go ≈ 2,5 $/mois** (recommandé, données conservées) ; (b) **sans disque (0 €)** : reconstruction automatique au démarrage depuis les sources gratuites (honnête, prend du temps au premier boot).
- Variables d'environnement : `ADMIN_TOKEN` (secret, dashboard Render), clés optionnelles gratuites (`FOOTBALL_DATA_ORG_TOKEN`, `API_FOOTBALL_KEY`, `ODDS_API_KEY`, `TSDB_KEY`).
- Limite Render free à connaître : **mise en veille après 15 min d'inactivité** → les workers tournent quand le service est réveillé ; réveil possible via un cron externe gratuit (cron-job.org ping `/v1/health` toutes les 10 min). Service toujours en ligne : plan Starter 7 $/mois (facultatif).
- Autres cibles documentées : Koyeb, Railway, VPS, Hugging Face Spaces (guides existants dans `docs/`).
- Postgres/Redis : migration sans réécriture (SQLAlchemy) vers Neon free / Upstash free si besoin de scale.

---

## 19. LIMITES TECHNIQUES (honnêteté §95)

1. **Aucune source 100 % gratuite, sans clé, temps réel mondial, avec cotes live ET profondeur illimitée n'existe.** Le 0 € est atteint par combinaison de sources gratuites complémentaires + quotas respectés + cache + priorisation. La couverture « temps réel mondial » dépend de l'ESPN non officiel (JSON public, stable depuis des années, mais **sans garantie contractuelle**) : si ESPN ferme ou bloque, le système bascule sur ce qui reste (TheSportsDB/API-Football dans la limite des quotas) et affiche `DATA UNAVAILABLE` là où rien ne couvre — jamais de données inventées.
2. **Cotes live gratuites très limitées** : ~16 requêtes/jour The Odds API → value bets live sur un sous-ensemble de matchs, pas sur tout le calendrier.
3. **football-data.org gratuit n'a pas le live** (live = option payante 12 €/mois) ni les compositions (29 €/mois) ; le free tier donne 12 compétitions, calendriers/résultats/classements.
4. **xG gratuit** : historique (StatsBomb, fduk récent) ; pas de flux xG live gratuit fiable → `DONNÉE INDISPONIBLE` affichée.
5. **Render free** se met en veille : latence au premier réveil (~30-60 s) ; workers non continus 24/7 sans plan payant ni cron de réveil.
6. **ML avancé** différé tant que le volume de données réelles ne permet pas de battre le marché en backtest : la décision reste sur les modèles statistiques calibrés.
7. **Compositions/blessures** nécessitent la clé gratuite API-Football (100 req/jour) : sans elle, `MISSING DEPENDENCY` affiché, pas de simulation.

---

## 20. COÛTS (vérifiés le 29/08/2026)

| Poste | Option 0 € | Option payante (facultative) |
|---|---|---|
| Hébergement Render | Free (veille 15 min) | Starter 7 $/mois (always-on) |
| Disque persistant | Reconstruction auto au boot | 0,25 $/Go/mois (~2,5 $ pour 10 Go) |
| Base de données | SQLite (fichier) | Neon Postgres free 0,5 Go, puis payant |
| Cache | Cache interne | Upstash Redis free |
| Football data | ESPN (public), fduk, openfootball, StatsBomb, OpenLigaDB, TheSportsDB free | football-data.org live 12 €/mois · API-Football Pro 19 $/mois |
| Cotes | The Odds API free 500 crédits/mois | The Odds API 30 $/mois (20 k crédits) |
| Compositions/blessures | API-Football free 100 req/jour | API-Football Pro 19 $/mois |
| Météo | Open-Meteo (10 k appels/jour, attribution CC BY) | — |
| IA | Moteur déterministe | Groq free tier (LLM gratuit) |
| **Total plancher** | **0 €/mois** | **~10-30 €/mois** pour un service always-on avec cotes live élargies |

---

## 21. ALTERNATIVES GRATUITES (par besoin)

- **Live scores sans clé** : ESPN JSON public (utilisé, statut non officiel) → repli : TheSportsDB test key (live v2 limité), API-Football free (100/j).
- **Calendriers/résultats/classements** : football-data.org free (12 ligues, clé gratuite), OpenLigaDB (Allemagne, sans clé), openfootball (domaine public).
- **Historique + cotes de clôture** : football-data.co.uk CSV (sans clé, profondeur décennales).
- **xG / events** : StatsBomb Open Data (non commercial, historique).
- **Météo** : Open-Meteo (sans clé).
- **Métadonnées/logos** : TheSportsDB (clé test « 3 »), Wikipedia/Wikidata (CC BY-SA) pour les contextes (entraîneurs, stades).
- **Cotes** : The Odds API free ; repli historique fduk.
- **Recherche de contexte** : moteur de recherche web intégré (Wikipedia FR/EN d'abord, sources publiques), cache 7 j.

---

## 22. ROADMAP (§93) — CHECKPOINT (§94)

| Phase | Contenu | Statut (29/08/2026) |
|---|---|---|
| 1 | Architecture (modules, providers, SSE, rendu) | ✅ COMPLETED |
| 2 | Database (35 tables, provenance, mappings) | ✅ COMPLETED |
| 3 | Source Discovery (registre, cycle, fiabilité observée) | ✅ COMPLETED |
| 4 | Data Aggregation (8 adapters, fusion, cache) | ✅ COMPLETED |
| 5 | Data Validation (états, qualité, conflits, NO FAKE DATA) | ✅ COMPLETED |
| 6 | Fixtures (calendrier, statuts, dédup) | ✅ COMPLETED |
| 7 | Historical Data (fduk profondeur réelle, StatsBomb, openfootball) | ✅ COMPLETED |
| 8 | Live Engine (boucles, événements, SSE, in-play) | ✅ COMPLETED |
| 9 | Statistics (features équipes/joueurs/contexte) | ✅ COMPLETED (xG live : UNAVAILABLE par conception) |
| 10 | Analytics (Elo, H2H, tactique, fatigue, arbitre, météo) | ✅ COMPLETED |
| 11 | Prediction Engine (Poisson, DC, ensemble, walk-forward) | ✅ COMPLETED |
| 12 | Odds Engine (snapshots, mouvement, multi-books) | ✅ COMPLETED (quotas free connus) |
| 13 | Value Bet Engine (edge, EV, gating, NO PICK) | ✅ COMPLETED |
| 14 | AI (chat FR déterministe, rapports 20 sections) | ✅ COMPLETED (hook LLM gratuit prévu) |
| 15 | Frontend | 🟡 PARTIAL : SPA FR 9 onglets livrée → **reste : refonte React + finitions multi-pages** |
| 16 | Admin (10 panneaux) | ✅ COMPLETED |
| 17 | Tests (126 verts, suites obligatoires) | ✅ COMPLETED (maintenance continue) |
| 18 | Performance + cache + Redis optionnel | 🟡 NEXT : cache ETag renforcé, optimisation mobile, SSE à l'échelle |
| 19 | Sécurité durcie (auth multi-users, JWT, headers) | 🟡 NEXT : token admin OK, auth utilisateurs à venir |
| 20 | Déploiement Render prod + Postgres optionnel | 🟡 NEXT : recette Render complète, disque/Postgres, monitoring live |

**NEXT STEP après validation :** Phase 15 (frontend React multi-pages fluide) en parallèle de la Phase 20 (recette de déploiement Render 0 €), puis Phase 18/19 (performance, auth). Chaque phase suit le checkpoint : construire → tester → corriger → documenter → présenter.

---

## CATALOGUE DES SOURCES VÉRIFIÉES (29/08/2026)

> Fiabilité indiquée = *constat de stabilité/réputation au moment de la vérification* ; la fiabilité **effective** est ensuite recalculée par le Source Reliability Engine sur les observations. Aucune source n'est présentée comme garantie.

### S1 — ESPN public JSON (`site.api.espn.com`)
- **Type** : API JSON non officielle (endpoints utilisés par le site ESPN) · **Clé** : non · **Coût** : 0 €
- **Données** : scoreboards live, calendriers, résultats, classements, stats équipes/matchs, compositions, effectifs, logos ; couverture soccer large (eng.1, esp.1, fra.1, ligues des 6 confédérations…).
- **Historique** : limité (saisons récentes) · **MAJ** : temps réel (secondes/minute) · **Temps réel** : **oui**
- **Limites** : non documenté, peut changer sans préavis ; pas de CGU d'API publique explicite → `terms_status = UNKNOWN` ; débit poli + cache obligatoires ; xG/odds absents ou minces.
- **Fiabilité constatée** : élevée (endpoints stables depuis des années, utilisés massivement) · **Risque principal** : fermeture/restriction sans préavis → failover documenté.

### S2 — football-data.co.uk (CSV)
- **Type** : fichiers CSV publics · **Clé** : non · **Coût** : 0 €
- **Données** : résultats, stats (tirs, corners, cartons, fautes selon saisons) et **cotes de plusieurs bookmakers** (Bet365, Pinnacle, Betfair, William Hill…), 1X2 et over/under.
- **Couverture** : ~22 ligues européennes majeures · **Historique** : profond (jusqu'à 1993/94 pour les Big 5, 2000/01 ailleurs) · **MAJ** : après les matchs (quotidienne en saison) · **Temps réel** : non
- **Limites** : pas de live, pas de compositions/joueurs détaillés · **CGU** : données gratuites fournies pour l'analyse, citation recommandée · **Fiabilité** : **très élevée** (référence du betting research) · **Risque** : faible.

### S3 — football-data.org (API v4)
- **Type** : API REST JSON · **Clé** : oui (gratuite) · **Coût** : 0 € (12 compétitions, 10 req/min)
- **Données free** : calendriers, résultats, classements, meilleurs buteurs, équipes (PL, LaLiga, Bundesliga, Serie A, Ligue 1, CL, Eredivisie, Primeira, Championship, Brésil Série A, CDM, Euro).
- **Historique** : saison courante en free · **MAJ** : temps réel **non** en free (scores en direct = option 12 €/mois) · **Temps réel free** : non
- **Limites** : 10 req/min ; lineups/events/odds = add-ons payants (15-29 €/mois) · **CGU** : usage personnel/éducatif en free ; attribution · **Fiabilité** : **très élevée**, doc excellente · **Risque** : faible.

### S4 — API-Football (api-sports.io)
- **Type** : API REST JSON · **Clé** : oui (gratuite) · **Coût** : 0 € (**100 req/jour**, tous endpoints)
- **Données** : 1 200+ ligues, **live (~15 s)**, événements, **compositions**, **blessures/suspensions**, stats, joueurs, H2H, cotes pré-match et live (qualité variable hors Big 5).
- **Historique** : plusieurs saisons (limité selon quotas) · **Temps réel** : oui
- **Limites** : 100 req/jour → réserver aux compositions/blessures des matchs prioritaires ; payant à partir de 19 $/mois (7 500/j) · **CGU** : free pour prototypes/usage personnel · **Fiabilité** : **élevée** · **Risque** : quota quotidien très petit.

### S5 — TheSportsDB
- **Type** : API JSON communautaire · **Clé** : clé test publique « 3 » (ou « 1 » en dev) · **Coût** : 0 €
- **Données** : métadonnées, logos, équipes, joueurs, calendriers/résultats ; endpoint `eventsday` (tous les matchs du jour en 1 requête, backbone mondial) ; livescores v2 = Patreon 9 $/mois.
- **Couverture** : mondiale, large mais peu profonde · **Historique** : variable · **MAJ** : quotidienne/temps réel selon endpoint · **Temps réel free** : limité
- **Limites** : clé test ≈ 30 req/min et 10 résultats par endpoint sur certaines recherches · **CGU** : usage commercial → soutien Patreon attendu · **Fiabilité** : **moyenne-bonne** (communautaire) · **Risque** : profondeur et fraîcheur variables.

### S6 — OpenLigaDB
- **Type** : API REST JSON sans clé · **Coût** : 0 €
- **Données** : calendriers, résultats, événements (buts/cartons/remplacements) — principalement football allemand (Bundesliga et divisions inférieures).
- **Temps réel** : oui (matchday) · **Historique** : bon sur l'Allemagne · **Limites** : couverture géographique étroite · **Fiabilité** : bonne · **Risque** : faible (projet communautaire stable).

### S7 — openfootball (football.json)
- **Type** : fichiers JSON/TXT sur GitHub (**domaine public**) · **Clé** : non · **Coût** : 0 €
- **Données** : calendriers et résultats des ligues majeures européennes + coupes · **Temps réel** : non (mises à jour communautaires) · **Historique** : ~2010/15 → aujourd'hui selon ligues.
- **Fiabilité** : bonne (maintenu, mais dépendant de la communauté) · **Risque** : délai de mise à jour après les matchs.

### S8 — StatsBomb Open Data (GitHub)
- **Type** : jeux de données JSON événementiels · **Clé** : non · **Coût** : 0 €
- **Données** : events niveau match (**xG**, tirs, passes, compositions, 360 non inclus) pour compétitions sélectionnées (Coupes du monde H/F, FAWSL, quelques ligues).
- **Temps réel** : **non, historique seulement** · **CGU** : usage non commercial, acceptation du User Agreement, attribution StatsBomb · **Fiabilité** : **très élevée** (qualité data science) · **Risque** : périmètre figé et limité.

### S9 — The Odds API
- **Type** : API REST JSON de cotes · **Clé** : oui (gratuite) · **Coût** : 0 € (**500 crédits/mois ≈ 16 req/jour**)
- **Données** : cotes pré-match (et endpoint live) de **40+ bookmakers**, marchés 1X2, over/under, BTTS, handicaps ; soccer couvert.
- **Historique** : limité en free (les snapshots constitués par PRONO SPORT deviennent l'historique) · **Temps réel** : oui mais quota très faible · **Limites** : pas de streaming, polling ; payant dès 30 $/mois (20 k crédits) · **Fiabilité** : **élevée** (acteur historique depuis 2017) · **Risque** : quota gratuit insuffisant pour du live mondial.

### S10 — Open-Meteo
- **Type** : API météo JSON · **Clé** : non · **Coût** : 0 € (10 000 appels/jour non commercial)
- **Données** : prévisions jusqu'à 16 jours (température, précipitations, vent, humidité) + archive historique ; coordonnées GPS des stades.
- **Temps réel** : prévisions/réanalyse · **CGU** : données CC BY 4.0 (attribution) · **Fiabilité** : **très élevée** · **Risque** : quasi nul.

### S11 — Wikipedia / Wikidata (recherche de contexte)
- **Type** : API web publiques · **Clé** : non · **Coût** : 0 €
- **Données** : contexte vérifiable (entraîneurs, stades, historiques de clubs, changements notables) pour le rapport expert et la résolution d'homonymies.
- **CGU** : CC BY-SA (attribution + partage) · **Fiabilité** : moyenne-bonne (source encyclopédique, horodatage de récupération conservé) · **Risque** : qualité variable → jamais utilisé comme source de score ou de cote.

### Sources examinées et **ÉCARTÉES** (documenté)
- **Sportmonks** : free tier réduit à 2 ligues (Superliga danoise, Premiership écossaise) → inutile pour la couverture visée.
- **SofaScore / FotMob / Understat / FBref / Transfermarkt « APIs »** : endpoints non documentés dont les CGU interdisent ou n'autorisent pas clairement l'accès automatisé → `SOURCE_NOT_ALLOWED`, contournement interdit (§5).
- **SharpAPI / odds-api.io** : free trop centré sur les sports US ou inscriptions gratuites en pause → non retenus pour le soccer mondial 0 €.
- **Sportradar / TheStatsAPI / Sportmonks payants** : qualité réelle mais 50-500+ $/mois → hors contrainte 0 €, restent des options de croissance future.

---

## EN ATTENTE DE VALIDATION (§101)

Ce plan est la **PREMIÈRE LIVRAISON**. Aucun nouveau code de construction massive ne sera lancé avant ta réponse.

Quand tu répondras **« VALIDÉ — COMMENCE LA PHASE 1 »** (ou directement « valide et continue »), j'exécuterai les phases restantes dans l'ordre de la roadmap §22 — en commençant par la **Phase 15 (frontend React multi-pages professionnel)** et la **Phase 20 (recette de déploiement Render 0 €)** — avec, pour chaque phase : construire → tester → corriger → documenter → checkpoint STATUS / NEXT STEP.
