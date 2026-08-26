# ⚽ PRONO SPORT 3.0

**Plateforme professionnelle mondiale d'intelligence football** — données 100 % réelles et gratuites,
zéro donnée inventée, zéro euro.

> # LES DONNÉES D'ABORD. LES MODÈLES ENSUITE. LA DÉCISION EN DERNIER.

## Ce qui est livré (alpha 3.0 — construit le 26/08/2026)

| Module | État | Détail |
|---|---|---|
| **Données réelles** | ✅ | 83 matchs réels ingérés (Premier League, La Liga, FA Cup — saisons 2025-26 et 2026-27 : 78 terminés, 5 à venir), xG (10), arbitres (46), **cotes réelles de 5 bookmakers** (2 684 snapshots), cotes actuelles sur les matchs à venir |
| **Moteur de modèles** | ✅ | Poisson + Dixon-Coles + Elo (ensemble documenté), entraînement anti-leakage, **3 prédictions** sur les matchs à venir + **6 Value Bets** (5 STRONG + 1 QUALIFIED) calculées sur cotes réelles (edge + EV) |
| **Value Bet Engine** | ✅ | Marge retirée, edge, EV, niveaux POTENTIAL/QUALIFIED/STRONG, **NO QUALIFIED PICK** si rien ne franchit les seuils (jamais de pick forcé) |
| **Backtest Lab + calibration** | ✅ | Walk-forward anti-leakage sur les 78 matchs terminés réels : **Brier / LogLoss / top-1 accuracy, modèle vs marché réel** (marge retirée). Séparé du paper-tracking et du live (§55) — affiché dans Analyses |
| **Recherche approfondie en ligne** | ✅ | L'application interroge elle-même les sources publiques (Wikipedia CC BY-SA, Open-Meteo, fduk, ESPN) — 0 € ; rapport expert 20 sections par match, chaque section badgée SOURCE / CALCULÉ / MODÈLE / DONNÉE INDISPONIBLE |
| **Compositions + blessures (0 €)** | ✅ | Provider **API-Football** (clé gratuite ~100 req/jour) : lineups officielles + blessures. Sans clé → `MISSING DEPENDENCY` affiché, jamais de simulation |
| **Cotes live multi-books (0 €)** | ✅ | Provider **The Odds API** (clé gratuite 500 crédits/mois) : 1X2 + O/U 2,5 rattachées aux matchs déjà en base (jamais de match inventé) |
| **Découverte de sources** | ✅ | 11 sources au registre (8 APPROVED + 3 DISCOVERED), catalogue de découverte 11 candidats 0 €, cycle DISCOVERED→APPROVED, fiabilité **calculée sur l'observé** (jamais inventée), `SOURCE_NOT_ALLOWED` si CGU incompatibles |
| **Workers journalisés** | ✅ | syncFixtures (5 min), syncLiveMatches (75 s), syncResults, syncLineups (45 min), syncOddsLive (3 h), syncWeather, syncHistorical, discoverSources (hebdo) — idempotents, journalisés (`sync_jobs`), failover |
| **Temps réel** | ✅ | SSE `/v1/events` : buts (déduits des changements de score réels), statuts, value bets, sync |
| **Résolution des pronos** | ✅ | WIN/LOSS/VOID/PENDING automatiques à la fin du match — prédiction originale **conservée telle quelle** (non-destructive, §54) |
| **Interface (FR)** | ✅ | SPA mobile-first : Accueil, Live, À venir, Terminés, Compétitions, **Équipes**, **Pronostics**, Value Bets, Analyses (monitoring + backtest), Assistant IA, Recherche, **Favoris**, **Admin (9 panneaux)**, fiche match **9 onglets** (Aperçu, Pronos, Cotes, Stats, H2H, Météo, Événements, Risques, Analyse) |
| **Admin & sécurité** | ✅ | Panneau admin : vue d'ensemble, sources, syncs (déclenchables), qualité, backtest, prédictions, value bets, erreurs, **sauvegarde SQLite cohérente** (API + CLI) · **rate limiting** 300 req/min/IP · `ADMIN_TOKEN` optionnel sur les actions sensibles |
| **Qualité & transparence** | ✅ | Data Quality Score par compétition, % vérifié (multi-sources), profondeur historique réelle, fraîcheur (FRESH/STALE) |
| **Tests** | ✅ | **113 tests** dont la suite obligatoire 3.0 : NO FAKE DATA, DATA CONFLICT, LIVE, ODDS, LINEUP, PROVIDER FAILURE, BACKTEST, providers à clé, **ADMIN, SÉCURITÉ (rate limit, backup), DÉPLOIEMENT RENDER** |
| **Honnêteté** | ✅ | xG absent → « DONNÉE INDISPONIBLE » (jamais d'estimation) · compositions/joueurs sans clé → affichés comme tels · historique partiel → profondeur réelle affichée · backtest < marché → affiché tel quel |

## Démarrage (0 €, 3 commandes)

```bash
cd backend
pip install -r requirements.txt
python -m app.cli status            # état de la base
uvicorn app.api:app --host 0.0.0.0 --port 8000
```

→ http://localhost:8000 — l'interface est en français, les données sont celles de la base.

### Alimenter la base (sources gratuites, sans clé)

```bash
cd backend
python -m app.cli ingest-fduk --divs E0 SP1 D1 I1 F1 --seasons 2526 2627   # historique + xG + cotes
python -m app.cli ingest-fduk-fixtures                                     # matchs à venir + cotes actuelles
python -m app.cli ingest-espn --leagues eng.1 esp.1 fra.1 --days-back 1 --days-ahead 2  # live + logos
python -m app.cli compute-analytics && python -m app.cli compute-predictions
python -m app.cli backtest                                                 # backtest walk-forward + calibration
```

Les workers automatiques (AUTO_INGEST=1, AUTO_LIVE=1, AUTO_COMPUTE=1) poursuivent ensuite en continu.
Avec `PS_CACHE_DIR` défini, le cache intelligent sert les dernières données réelles sans re-télécharger.

### Clés GRATUITES facultatives (0 € — rien ne fonctionne moins sans elles)

```bash
# .env ou environment : chaque clé absente → « MISSING DEPENDENCY » affiché, jamais de donnée inventée
API_FOOTBALL_KEY=    # gratuite (api-sports.io, ~100 req/jour) → compositions + blessures (worker syncLineups)
ODDS_API_KEY=        # gratuite (the-odds-api.com, 500 crédits/mois) → cotes live multi-books (syncOddsLive)
```

## Les 3 étiquettes de donnée (partout)

`SOURCE` = donnée d'une source (provenance affichée) · `CALCULÉ` = calculé sur données réelles ·
`MODÈLE` = estimation du modèle (probabilité ≠ certitude) · et `DONNÉE INDISPONIBLE` quand rien n'existe.

## Réseau & résilience (important)

L'application fait **elle-même** ses recherches en ligne (Wikipedia CC BY-SA, Open-Meteo, fduk, ESPN) —
aucune API payante. Elle est conçue pour **rester 100 % fonctionnelle sans réseau** :

- **Avec réseau** (machine habituelle) : contexte web réel, météo, cotes live, compositions (si clés
  gratuites) — tout est rempli et les rapports sont mis en cache 6 h.
- **Sans réseau** (ex. certains environnements de sandbox/proxy qui bloquent les appels sortants de
  l'application) : l'app s'appuie sur les **données déjà en base** (matchs, cotes, modèles) et affiche
  honnêtement `DONNÉE INDISPONIBLE` pour les sections qui exigent le web (contexte, météo, xG live…).
  Un rapport dont le contexte web est indisponible **n'est pas mis en cache** : il sera régénéré automatiquement
  à la requête suivante, quand le réseau est de retour.

> C'est un choix de transparence, pas une limitation : PRONO SPORT préfère l'abstention affichée
> à la donnée inventée.

## Déploiement (prêt dans le repo)

| Où | Fichier | Pour qui |
|---|---|---|
| **Render** 👑 (choix retenu) | `render.yaml` (blueprint 1 clic) | **0 $ au démarrage** (instance Free 512 Mo) ; auto-déploiement à chaque push sur `main` ; guide pas-à-pas : `docs/09-GUIDE-RENDER.md` |
| **Koyeb** (24/7) | `Dockerfile.koyeb` | alternative : déploiement depuis GitHub, 512 Mo RAM, gratuit dans la plupart des régions |
| **Hugging Face Spaces** | `deploy/hf-space/Dockerfile` | alternative sans carte bancaire ; repo GitHub **déjà configuré** dans le fichier |
| **docker compose** (VPS / machine perso) | `docker-compose.yml` + `backend/Dockerfile` | `docker compose up api` — SQLite persistant, option PostgreSQL |
| **Installation locale / Termux** | `install.sh` | 1 commande : venv + base + ingestion + moteur |
| **Site statique public (bonus)** | `.github/workflows/update-site.yml` | snapshot auto-mis-à-jour toutes les 6 h sur GitHub Pages (0 €) |

**Honnêteté Render (détail dans `docs/09`)** : l'instance Free dort après 15 min d'inactivité
(réveil 30-60 s) et n'a pas de disque persistant → à chaque redéploiement le **bootstrap auto**
recompile les vraies données (~20-40 min). Toujours en ligne : Starter 7 $/mois ; persistance :
disque 0,25 $/Go/mois. **Rien n'exige de payer au démarrage.**

**Comportement au premier déploiement** : l'app démarre immédiatement (interface FR + API) avec
« DONNÉE NON DISPONIBLE », puis le **bootstrap auto** remplit la base avec les vraies données
publiques (5 étapes, ~20-40 min) — tout est journalisé, idempotent, `|| true` (§64 : une source KO
n'arrête jamais le tout).

**Avant de déployer** : fusionner la branche `arena/01a03e4e-prono-sport` dans `main` (les images
Docker se construisent depuis `main`). Ensuite, suivre le guide adapté :
`docs/05-GUIDE-HUGGINGFACE.md` ou `docs/06-GUIDE-KOYEB.md` (pas à pas, 5 min).

## Documentation

- `TECHNICAL_MASTER_PLAN.md` — le plan technique complet (22 points + fiches sources)
- `docs/DATA_SOURCES.md` — fiches sources **vérifiées** au 26/08/2026
- `docs/DATA_PIPELINE.md` — architecture du pipeline (sources → cache → workers → modèles → value → UI)
- `docs/01-ARCHITECTURE.md` → `docs/08-GUIDE-CODESPACES.md` — guides d'installation/déploiement (Koyeb, HF Spaces, VPS, Termux…)

## Coût total : 0 €

Toutes les sources actives sont gratuites et sans clé obligatoire. Les clés **facultatives**
(football-data.org, API-Football, The Odds API) débloquent plus de données mais **rien ne fonctionne
moins** sans elles — chaque source manquante est signalée `MISSING DEPENDENCY`, jamais simulée.
