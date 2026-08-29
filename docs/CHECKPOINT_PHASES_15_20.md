# CHECKPOINT — Phases 20 (Déploiement Render) & 15 (Frontend)

> Date : 2026-08-29 · Branche : `arena/01a04cd9-prono-sport`
> Signature : **LES DONNÉES D'ABORD. LES MODÈLES ENSUITE. LA DÉCISION EN DERNIER.**

## STATUT GLOBAL

| Phase | Statut |
|---|---|
| Phase 20 — Déploiement Render 0 € | ✅ **COMPLETED** (recette + correction de bug) |
| Phase 15 — Frontend (incrément Joueurs) | ✅ **COMPLETED** (page + API + tests) |
| Tests | ✅ **129 tests verts** (126 + 3 nouveaux) |

---

## 1. Phase 20 — DÉPLOIEMENT RENDER

### Bug corrigé : chemin de base SQLite sur Render free
- **Symptôme** : `render.yaml` fixait `DATABASE_URL=sqlite:////data/prono_sport.db` alors que le
  disque persistant était commenté. Sur Render free, le conteneur s'exécute en utilisateur non-root :
  le répertoire `/data` à la racine du système n'est pas créable → échec de `init-db` au premier boot.
- **Correctif (double sécurité)** :
  1. `render.yaml` pointe désormais vers le répertoire applicatif garanti accessible en écriture
     (`/srv/repo/data/prono_sport.db`) ; le bloc disque persistant (optionnel, ~2,5 $/mois) et la
     variable `/data` correspondante sont documentés en commentaires.
  2. `start_server.sh` teste l'écriture du dossier cible de `DATABASE_URL` ; s'il est inaccessible,
     il bascule automatiquement vers une base dans le répertoire de l'application (idempotent,
     aucune donnée inventée). Vérifié par test de fallback.
- Ajout de `PYTHONUNBUFFERED=1` (logs Render en temps réel), de la clé `dockerPath` validée par les
  tests, et de toutes les variables de sources gratuites (`FOOTBALL_DATA_ORG_TOKEN`,
  `API_FOOTBALL_KEY`, `ODDS_API_KEY`, `TSDB_KEY`).

### Comportement de déploiement (honnête)
- **Sans disque (0 €)** : au 1er démarrage, la base est vide ; l'API répond immédiatement
  (`DONNÉE INDISPONIBLE` là où rien n'est encore chargé) pendant que le bootstrap compile les
  VRAIES données en arrière-plan (TheSportsDB eventsday, ESPN mondial, fduk historique + cotes,
  météo, analytics/modèles/value bets). Le stockage est éphémère : un redéploiement relance le
  bootstrap. C'est un comportement assumé et documenté, jamais de données fictives.
- **Avec disque (optionnel)** : la base persiste entre redéploiements.
- **Veille Render free** : l'instance se met en veille après 15 min d'inactivité ; un cron externe
  gratuit (cron-job.org) peut taper `/v1/health` toutes les 10 min pour la garder éveillée.
- Le réseau du sandbox de développement bloque les appels HTTPS sortants : la collecte live n'est
  donc testable que déployée (Render a un accès internet normal) ; la logique est couverte par les
  129 tests (providers, ingestion, conflits, live, odds, fallback).

## 2. Phase 15 — FRONTEND (incrément Joueurs, §21/§22)

- Nouvelle page **👤 Joueurs** dans la navigation (`#/joueurs`) : liste des joueurs réellement en
  base, avec équipe, poste, nationalité et **statut de disponibilité** (Disponible / Blessé /
  Suspendu / Incertain / Retour) + filtre de recherche.
- Nouvel endpoint API **`GET /v1/players`** (`team_id`, `q`, `limit`) : joueurs + blessures +
  suspensions fusionnés, chaque joueur étiqueté `SOURCE DATA`.
- **Absence honnête** : sans clé gratuite API-Football (effectifs/compositions), la page affiche
  `MISSING DEPENDENCY` avec la solution 0 € — jamais de joueur inventé (§21/§22).
- CSS ajouté (`mini-logo`, `ev-warn`, `player-row`).

## 3. TESTS

- 3 nouveaux tests : endpoint joueurs vide = honnête, forme des statuts §22, présence de la page.
- Suite complète : **129 passed**.

## NEXT STEP

- Phase 15 (suite) : refonte React/Vite optionnelle ou poursuite des finitions multi-pages
  (PAYS/CONTINENTS dédiés, recherches joueurs étendue).
- Phase 18/19 : cache ETag renforcé, auth multi-utilisateurs (JWT), optimisation mobile.
- Après déploiement Render : renseigner les clés gratuites dans le dashboard et vérifier le
  bootstrap mondial dans les logs.
