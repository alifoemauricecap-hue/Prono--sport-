# Guide 09 — Déployer PRONO SPORT 3.0 sur RENDER (0 € au démarrage)

**Pourquoi Render** : déploiement par **Blueprint** (`render.yaml` déjà dans le repo) — Render
lit le fichier, crée le service, déploie automatiquement à chaque push sur `main`.
HTTPS + domaine permanent (`prono-sport.onrender.com`), rien à configurer à la main.

**Coûts (page officielle render.com/pricing, vérifiée le 26/08/2026)** :

| Élément | Prix | Ce que tu obtiens |
|---|---|---|
| Espace de travail **Hobby** | **0 $/mois** | jusqu'à 25 services |
| Instance web **Free** | **0 $/mois** | 512 Mo RAM / 0.1 CPU — **mise en veille après 15 min d'inactivité** (réveil ~30-60 s) |
| Instance web **Starter** (optionnel) | 7 $/mois | toujours en ligne, 512 Mo / 0.5 CPU |
| Disque persistant (optionnel) | 0,25 $/Go/mois | la base survit aux redéploiements |
| **Total au démarrage** | **0 €** | instance Free, sans carte bancaire |

**La vérité d'abord (§1 honnêteté)** :

| ✅ Ce que tu gagnes | ⚠️ Les limites honnêtes |
|---|---|
| Zéro fichier à écrire : `render.yaml` prêt dans le repo | Free = **veille après 15 min** : le 1er visiteur attend le réveil (~30-60 s). Pour du 24/7 → Starter (7 $/mois) |
| Auto-déploiement à chaque push sur `main` | **Pas de disque sur le Free** : à chaque redéploiement, la base repart de zéro et le **bootstrap auto mondial** recompile les vraies données (~40-90 min). Prévu, pas un bug — jamais de données inventées |
| `/v1/health` surveillé (healthcheck) | 512 Mo RAM : pendant le bootstrap/ingestion, le service est un peu plus lent |
| `ADMIN_TOKEN` en secret (jamais dans le code) | L'API reste **sans clé payante** : les sources sont gratuites (fduk, ESPN, OpenLigaDB, TheSportsDB, Wikipedia, Open-Meteo) |

---

## ÉTAPE 1 — Fusionner le code dans `main` (2 min)

1. Sur GitHub, ouvre le Pull Request de la branche `arena/01a03e4e-prono-sport` → **Merge**.
   *(Les images Docker se construisent depuis `main` — indispensable.)*

## ÉTAPE 2 — Créer le compte (2 min)

1. **https://render.com** → **Sign Up** → **Continue with GitHub** (ou email).
2. L'espace **Hobby (0 $/mois)** est sélectionné par défaut.

## ÉTAPE 3 — Déployer depuis le Blueprint (3 min)

1. Dans le dashboard Render : **New → Blueprint**.
2. Sélectionne ton dépôt **`Prono--sport-`** → branche `main`.
3. Render détecte `render.yaml` → bouton **Create (1 service)**.
4. Avant de confirmer : **Settings → Environment** du service `prono-sport` :
   - `ADMIN_TOKEN` : mets un secret (ex. `prono-XXXXX`) — il protège les actions admin
     (déclencher un worker, télécharger la sauvegarde). *Tout fonctionne sans, c'est facultatif.*
5. **Deploy**. ✅

## ÉTAPE 4 — Vérifier (2 min)

1. Attends le build (3-6 min) → l'état passe à **Live**.
2. Ouvre **`https://prono-sport.onrender.com`** (ou ton adresse Render).
3. Si la page est vide au 1er chargement : c'est la **veille free** — recharges après 30 s,
   ou ouvre d'abord **`https://prono-sport.onrender.com/v1/health`** pour réveiller le service.
4. Pendant le bootstrap mondial (~40-90 min) : l'app affiche « DONNÉE INDISPONIBLE » → normal,
   les vraies données arrivent en fond (onglet **Logs** → tu vois `[1/5]` … `[5/5]`).

## ÉTAPE 5 — Garder tout à jour (0 action)

Chaque push sur `main` = redéploiement automatique (`autoDeploy: true`).
Le cron interne (workers `AUTO_INGEST`/`AUTO_LIVE`/`AUTO_COMPUTE`) tourne dans le service.

---

## Sauvegarde & restauration (0 €)

- **Télécharger** : onglet **Admin → backup** de l'interface (ou `GET /v1/admin/backup`
  avec l'en-tête `x-admin-token` si `ADMIN_TOKEN` est défini).
- **Cli** : `python -m app.cli backup` → `data/backups/prono-sport-AAAAJJJJ-HHMMSS.db`.
- **Restaurer** : recopie le `.db` à l'emplacement de `DATABASE_URL` et redémarre.

## Évoluer plus tard (optionnel, rien ne bloque)

| Besoin | Action sur Render | Coût |
|---|---|---|
| Toujours en ligne (pas de veille) | Instance → **Starter** | 7 $/mois |
| Base persistante entre redéploiements | Settings → **Disks** → ajouter 10 Go sur `/data` | ~2,50 $/mois |
| Plus de données (compositions, cotes live) | Clés **gratuites** `API_FOOTBALL_KEY` / `ODDS_API_KEY` en variables d'environment | 0 € |
