# GUIDE DE DÉPLOIEMENT RENDER — PRONO SPORT 3.0 (0 €)

> Application 100 % données réelles, sans API payante. Ce guide déploie la plateforme
> sur Render en environ 10 minutes, sans carte bancaire.

## 1. Prérequis

- Un compte **GitHub** (gratuit) avec le dépôt PRONO SPORT poussé.
- Un compte **Render** (gratuit) : https://dashboard.render.com — connexion via GitHub.
- Aucune carte bancaire requise pour le plan **Free**.

## 2. Déploiement (méthode Blueprint recommandée — 1 clic)

1. Sur Render : **New → Blueprint**.
2. Sélectionnez le dépôt GitHub `Prono--sport-` (autorisez Render à y accéder).
3. Render détecte le fichier **`render.yaml`** à la racine et propose le service
   **`prono-sport`** (Docker, plan free, healthcheck `/v1/health`). Cliquez **Apply**.
4. Pendant la création, Render demande les variables **secrètes** (laisser vide = OK,
   tout est optionnel) :
   - `ADMIN_TOKEN` — mot de passe protégeant les actions admin (sync manuelles, sauvegarde).
   - `API_FOOTBALL_KEY` — clé **gratuite** api-football.com (compositions & blessures).
   - `ODDS_API_KEY` — clé **gratuite** the-odds-api.com (cotes multi-bookmakers).
   - `FOOTBALL_DATA_ORG_TOKEN` — clé **gratuite** football-data.org (12 compétitions).
5. Cliquez **Deploy**. Le build Docker prend 3-6 minutes la première fois.

> Méthode alternative (sans Blueprint) : **New → Web Service → Docker**, pointez le
> dépôt, le `Dockerfile` racine est détecté automatiquement. Recopiez les variables
> d'environnement listées dans `render.yaml`.

## 3. Clés gratuites optionnelles (toutes 0 €, jamais obligatoires)

| Clé | Où l'obtenir (gratuit) | Apporte | Quota gratuit |
|---|---|---|---|
| `TSDB_KEY` | déjà défini (`3`) | métadonnées/logos, backbone mondial | ~30 req/min |
| `FOOTBALL_DATA_ORG_TOKEN` | football-data.org → Register | calendriers/résultats/classements (12 ligues) | 10 req/min |
| `API_FOOTBALL_KEY` | dashboard.api-football.com | **compositions officielles + blessures/suspensions**, live ~15 s | 100 req/jour |
| `ODDS_API_KEY` | the-odds-api.com | **cotes de 40+ bookmakers** (value bets live) | 500 crédits/mois |

Sans ces clés, l'application fonctionne : live/calendriers via ESPN + TheSportsDB,
historique et cotes de clôture via football-data.co.uk, météo via Open-Meteo. Les
fonctions non alimentées affichent **`MISSING DEPENDENCY` / `DONNÉE INDISPONIBLE`**,
jamais de données inventées.

## 4. Premier démarrage : ce qui se passe

1. Le serveur répond **immédiatement** sur `https://<votre-service>.onrender.com`
   (l'API et l'interface sont en ligne ; les écrans sans donnée affichent « en attente »).
2. En arrière-plan, le **bootstrap par étapes** (`backend/bootstrap_data.sh`) charge les
   vraies données :
   - **Étape A (quelques minutes)** : matchs du jour/à venir (TheSportsDB + ESPN),
     historiques Big 5 + cotes (football-data.co.uk), puis calcul des modèles et des
     **value bets** → l'application devient pleinement utile.
   - **Étape B (ensuite)** : élargissement mondial, profondeur historique, logos,
     recherche de contexte par ligue (Wikipedia).
3. Suivez la progression dans **Logs** Render (`[A1]…[A-OK]…[B-OK]`).

## 5. Maintenir le service éveillé (optionnel, gratuit)

Le plan Free se met en veille après **15 minutes sans trafic** (les workers tournent
quand il est actif). Pour une collecte continue sans payer :

- Créez un cron gratuit sur https://cron-job.org qui ping
  `https://<votre-service>.onrender.com/v1/health` **toutes les 10 minutes**.
- Sinon, passez le service en plan **Starter (7 $/mois)** dans Render → toujours en
  ligne, workers 24/7.

## 6. Persistance des données (optionnel)

- **Sans disque (0 €)** : la base SQLite vit dans le conteneur. Après un **redéploiement**
  (nouveau commit), elle est reconstruite automatiquement par le bootstrap (les données
  sont régénérables à l'infini depuis les sources gratuites). La veille quotidienne, elle,
  **ne** vide **pas** la base.
- **Avec disque (~2,5 $/mois)** : dans Render → service → **Disks**, ajoutez un disque de
  10 Go monté sur `/data`, puis passez la variable `DATABASE_URL` à
  `sqlite:////data/prono_sport.db`. La base persiste entre les redéploiements.

## 7. Vérification après déploiement

- `https://<service>.onrender.com/v1/health` → `{"status":"OK", ...}`.
- L'interface : naviguez **Live**, **À venir**, **Value Bets**, **Pronostics**.
- L'onglet **Admin** (rendez-vous y puis saisissez votre `ADMIN_TOKEN` dans le champ)
  montre les sources, les synchros, la qualité des données et les erreurs.

## 8. Dépannage

| Symptôme | Cause / solution |
|---|---|
| Les pages affichent « en attente / donnée indisponible » au début | Normal : l'étape A du bootstrap dure quelques minutes. Surveillez les logs. |
| `DATABASE_URL ... /data` erreur au boot | Corrigé : le script bascule automatiquement sur un chemin accessible ; sinon utilisez `sqlite:////srv/repo/data/prono_sport.db` ou montez un disque sur `/data`. |
| Aucune composition / blessure | Ajoutez `API_FOOTBALL_KEY` (gratuit). Sans elle, `MISSING DEPENDENCY` s'affiche. |
| Aucune cote live | Ajoutez `ODDS_API_KEY` (gratuit, 500 crédits/mois) ; les cotes de clôture historiques restent disponibles via football-data.co.uk. |
| Le service dort | Mettez en place le cron de ping (§5) ou le plan Starter. |
| Une source ne répond pas | Le système bascule sur une autre source ou affiche `DATA UNAVAILABLE` (§64) ; consultez Admin → Erreurs. |

## 9. Mises à jour

Tout `git push` sur la branche suivie déclenche un redéploiement automatique
(`autoDeploy: true` dans `render.yaml`). La base se reconstruit seule (étape A rapide),
ou persiste si vous avez ajouté un disque.
