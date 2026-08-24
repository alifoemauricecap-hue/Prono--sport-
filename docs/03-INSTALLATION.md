# 03 — INSTALLATION & EXPLOITATION (100 % GRATUIT)

PRONO SPORT 2.0 fonctionne **entièrement sans payer un centime** :
données publiques gratuites (ESPN public API, football-data.co.uk, OpenLigaDB,
TheSportsDB clé « 3 », Open-Meteo), base SQLite par défaut, hébergement possible
sur votre propre machine ou un free-tier cloud.

---

## 1. Installation en 1 commande (Linux / macOS)

```bash
cd prono-sport
bash install.sh
```

Résultat : environnement Python isolé, base initialisée, données réelles ingérées,
modèles entraînés. Ensuite :

```bash
cd backend && source .venv/bin/activate
AUTO_INGEST=1 uvicorn app.api:app --host 0.0.0.0 --port 8000
# Interface : http://localhost:8000 · API : http://localhost:8000/v1/stats
```

### Windows (PowerShell)
```powershell
cd prono-sport\backend
python -m venv .venv ; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m app.cli init-db
# … mêmes commandes CLI que dans install.sh …
uvicorn app.api:app --host 0.0.0.0 --port 8000
```

### Docker (si vous l'avez — pas obligatoire)
```bash
docker compose up api --build      # SQLite intégré, persistant dans le volume pronodata
```

---

## 2. Mise à jour quotidienne (cron, gratuit)

```cron
45 6 * * *  /chemin/vers/prono-sport/update_daily.sh >> /tmp/prono.log 2>&1
```

Le pipeline : cotes du jour → scores/statuts (ESPN, J-3 → J+2) → balayage des statuts
périmés → vérification croisée → logos → Elo/forme → prédictions + value bets.

Quand l'API tourne, deux boucles internes rafraîchissent automatiquement :
- toutes les 5 min : ESPN (hier/aujourd'hui/demain, 55 ligues) ;
- toutes les 75 s : UNIQUEMENT les ligues avec un match **EN DIRECT** (scores live).

---

## 3. L'application 24/7 sans payer

| Option | Coût | Comment |
|---|---|---|
| Votre PC (idéal usage perso) | 0 FCFA — déjà payé | `uvicorn …` + cron |
| Raspberry Pi / ancien PC Linux | ~1-3 W d'électricité | idem, très stable |
| Oracle Cloud « Always Free » (VM ARM) | 0 (offre permanente gratuite) | même install.sh, ouvrir le port 8000 |
| Docker local | 0 | `docker compose up api` |

> Hébergeurs « gratuits » type PaaS (Render/Railway free) : possibles mais leurs offres
> changent — vérifiez toujours les conditions AVANT (§1 : on ne promet jamais du « gratuit
> à vie » sans le vérifier).

---

## 4. 6e source gratuite (optionnel, +1 couche de vérification)

1. Créer un compte gratuit sur https://www.football-data.org (plan « Tier One » : 10 req/min, 0 €)
2. `export FOOTBALL_DATA_ORG_TOKEN=votre_clé`
3. `python -m app.cli ingest-fdorg --comps PL PD BL1 SA FL1 --days-back 3 --days-ahead 7`

Sans cette clé, l'adaptateur se désactive proprement (statut NON CONFIGURÉ tracé) : rien ne casse.

---

## 5. Dépannage rapide

| Symptôme | Cause probable | Action |
|---|---|---|
| « DONNÉE NON DISPONIBLE » partout | première ingestion pas finie | relancer `install.sh` étape 3 |
| 0 value bet | marché efficient / pas de cotes | **normal** (§37 : jamais forcé) |
| Prédictions manquent une ligue | historique < 30 matchs en base | ingérer la saison fduk correspondante |
| Port déjà pris | un ancien serveur tourne | `pkill -f uvicorn` |

Logs provider par provider : `GET /v1/health/providers`.
