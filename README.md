# ⚽ PRONO SPORT 2.0

Plateforme mondiale d'analyse football — **données publiques 100 % gratuites, zéro donnée inventée** (§1),
multi-sources redondantes (§4), probabilités honnêtes (§38).

## Modules livrés (9/9) — 59 tests automatisés ✅

| Module | Contenu |
|---|---|
| **M1** Fondation | Schéma DB, validation §7 (rejets audités), résolution d'entités §5, idempotence §9 |
| **M2** Multi-sources | 5 providers (fduk, ESPN, OpenLigaDB, TheSportsDB, fdorg optionnel) · moteur de cohérence (VERIFIED/CONTRADICTORY) · UI temps réel |
| **M3** Analytics | Elo interne (K=60), forme 5 matchs, features décroissantes — 100 % calculé sur données réelles |
| **M4** Modèles | Poisson + Dixon-Coles + Elo (ensemble 70/30) entraînés par championnat · anti-leakage §22 · Value Bets 1X2 (EV = P×O−1, marge retirée §32, NO QUALIFIED PICK §37) |
| **M4.1** Garde-fous | Purge matchs passés, anti-désaccord extrême (25 pts), idempotence totale, balayage statuts périmés → UNKNOWN |
| **M5** Marché | Value Bets **O/U 2.5** (cotes réelles uniquement) · tendance des cotes (mouvement marché ↗/↘) |
| **M6** Live | Minute réelle ESPN, probas **in-play** (Poisson restants), boucle 75 s sur les ligues en direct |
| **M7** Expert | Fiche match : prédiction + marché actuel + H2H réel + **météo stade (Open-Meteo)** + arbitre + score qualité §48 |
| **M8** Chat IA | Assistant FR : value bets, pronos, forme/Elo — réponses exclusivement sur données réelles |
| **M9** Scale | `install.sh` 1-commande, `update_daily.sh` (cron), Dockerfile, docs — **0 FCFA, pour toujours** |

## Démarrage (atelier SQLite instantané)

```bash
cd backend && pip install -r requirements.txt
python -m pytest tests -q          # 59 tests
python -m app.cli status           # état de la base
uvicorn app.api:app --host 0.0.0.0 --port 8000   # http://localhost:8000
```

## Installation permanente (votre machine, GRATUIT)

```bash
bash install.sh          # tout-inclus
bash update_daily.sh     # chaque jour (cron)
```
→ `docs/03-INSTALLATION.md` (Linux/macOS/Windows/Docker/free-tier cloud)

## Hébergement 24/7 depuis un téléphone (0 €, SANS carte bancaire)

| Option | Temps réel | Guide |
|---|---|---|
| **Koyeb** 👑 *(le plus simple : 6 clics depuis GitHub, zéro fichier à créer, toujours en ligne ; carte parfois demandée selon région → plan B ci-dessous)* | ✅ | `docs/06-GUIDE-KOYEB.md` + `Dockerfile.koyeb` |
| **Hugging Face Spaces** *(jamais de carte ; 1 fichier à créer)* | ✅ | `docs/05-GUIDE-HUGGINGFACE.md` + `deploy/hf-space/` |
| **GitHub Pages** (site statique, mis à jour 4×/jour par robot CI) | ❌ (photo 6h) | `docs/04-GUIDE-GITHUB-PAGES.md` |

Stratégie : Koyeb (ou HF) = temps réel, GitHub Pages = secours toujours en ligne. Le tout pour 0 €.
Démarrage universel (VPS, Termux…) : `backend/start_server.sh` (init + bootstrap auto si vide + API sur `$PORT`).

## Sources de données (toutes gratuites)

| Source | Usage | Clé |
|---|---|---|
| football-data.co.uk | 22 championnats : historiques complets, xG, arbitres, ~20 bookmakers, cotes actuelles | aucune |
| ESPN public API | 55 ligues : fixtures, scores live/minute, logos équipes+ligues, stades | aucune |
| OpenLigaDB | Allemagne : calendriers complets | aucune |
| TheSportsDB (« 3 ») | cross-check badges/événements | « 3 » (publique) |
| Open-Meteo | météo des stades à l'heure du match | aucune |
| football-data.org (optionnel) | 6e couche de vérification | gratuite à créer (10 req/min) |

## Contrat d'honnêteté

- Donnée manquante → « DONNÉE NON DISPONIBLE », jamais de chiffre inventé.
- Une probabilité n'est jamais présentée comme une certitude.
- `GET /v1/fixtures/{id}/analysis` expose l'audit complet : données disponibles, forces du modèle,
  cotes réelles de capture, score qualité.
