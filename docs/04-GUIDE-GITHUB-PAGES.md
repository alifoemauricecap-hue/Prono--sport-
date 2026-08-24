# 04 — SITE PUBLIC 24/7 GRATUIT, SANS CARTE, TOUT AU TÉLÉPHONE 📱

**Résultat :** une URL type `https://TON-PSEUDO.github.io/prono-sport/` qui affiche
le site complet (matchs, logos, pronostics, value bets, légende), **mise à jour 4×/jour
automatiquement**, accessible partout, **0 FCFA, 0 carte bancaire, PC éteint**.

**Comment ça marche (1 phrase)** : GitHub héberge le site gratuitement (Pages) et ses
serveurs gratuits régénèrent les données réelles 4 fois par jour (Actions).

---

## Étape 1 — Compte GitHub gratuit (2 min, téléphone)

1. Ouvre https://github.com dans ton navigateur → **Sign up**.
2. E-mail + mot de passe + pseudo. (Aucune carte demandée — pour un repo **public**, jamais.)
3. Vérifie ton e-mail.

## Étape 2 — Créer le dépôt public

1. En haut à droite → **+** → **New repository**.
2. Name : `prono-sport` · **Public** ✅ (obligatoire pour le gratuit illimité) · Create.

## Étape 3 — Envoyer les fichiers (au choix)

### Option A — depuis le téléphone (interface web)
1. Dans le dépôt vide → **« uploading an existing file »** / **Add file → Upload files**.
2. Envoie le contenu de l'archive projet (dossier `backend` + `docs` + `install.sh`,
   `update_daily.sh`, `README.md`, `.env.example`, `docker-compose.yml`,
   `.github/` — **sauf** le dossier `data/` qui se régénère tout seul).
   > Astuce téléphone : envoie par petits lots (l'interface limite à ~100 fichiers
   > par envoi) — l'arborescence est conservée.

### Option B — via Termux (plus rapide si tu l'as)
```bash
pkg install git -y
git clone https://github.com/TON-PSEUDO/prono-sport.git
cd prono-sport && unzip ~/storage/downloads/prono-sport-code.zip
git add -A && git commit -m "PRONO SPORT 2.0"
git push    # identifiant : TON-PSEUDO + Personal Access Token (Settings → Developer settings)
```

## Étape 4 — Activer GitHub Pages (1 min)

1. Dépôt → **Settings** (icône ⚙️) → menu gauche **Pages**.
2. **Source : GitHub Actions** (choisir dans la liste déroulante). Rien d'autre.

## Étape 5 — Première génération

1. Onglet **Actions** du dépôt → workflow « PRONO SPORT — mise à jour du site »
   → **Run workflow** ▶ (bouton à droite).
2. Attends ~10-15 min (la première ingestion télécharge les vraies données : normal).
3. TON SITE : `https://TON-PSEUDO.github.io/prono-sport/` 🎉

---

## Ensuite, au quotidien — tu n'as RIEN à faire

- **4×/jour** (5h40, 11h40, 17h40, 23h40 UTC) : nouvelles données réelles, nouvelles
  cotes, Elo recalculé, prédictions et value bets régénérés → le site change tout seul.
- Envie d'une mise à jour immédiate ? Onglet **Actions → Run workflow** (même au téléphone).

## Ce que tu obtiens / ne pas attendre (honnêteté §1)

✅ Inclus : matchs & logos, vérification multi-sources, Elo, probabilités, marché réel,
value bets, H2H, météo, fiches match, légende, chat (mode données encapsulées).
⚠️ Version **statique** : les valeurs datent de la dernière génération (max 6 h) —
la date exacte est affichée en pied de page. Pas de live minute-par-minute.
➡️ Pour le **LIVE 75 s + chat serveur** : voie serveur (`install.sh` sur une machine,
Termux, ou VM gratuite).

## En cas de souci

| Problème | Solution |
|---|---|
| Actions rouge ❌ | Onglet Actions → clique le run → le log dit quelle source a répondu autre chose ; relance (Run workflow) — les sources gratuites ont parfois des délais. |
| « Page 404 » juste après | Pages met ~2 min à publier la 1re fois ; vérifie Settings → Pages = GitHub Actions. |
| Repo privé ? | Le gratuit illimité exige **public** (le contenu est de toute façon des données sportives publiques). |
