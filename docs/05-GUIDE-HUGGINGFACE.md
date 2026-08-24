# Guide 05 — Héberger PRONO SPORT 2.0 sur Hugging Face Spaces (GRATUIT, SANS CARTE, DEPUIS TON TÉLÉPHONE)

Le vrai temps réel 24/7 : scores live (75 s), ingestion continue (5 min), recalcul des pronos (1 h).

**Coût : 0 €. Carte bancaire : jamais demandée. PC : pas besoin.**
Prérequis : ton compte GitHub avec le code déjà en ligne (Guide 04).

---

## La vérité d'abord (§1 honnêteté)

| ✅ Ce que tu gagnes | ⚠️ Les limites honnêtes |
|---|---|
| Vrai temps réel : live 75 s, ingestion 5 min, pronos recalculés chaque heure | Le Space est **public** (tout le monde peut voir l'app — il n'y a aucune donnée privée dedans, donc OK) |
| En ligne 24/7 sans rien payer | Après **48 h sans visite**, HF endort le Space → solution gratuite à l'étape 6 (ping automatique) |
| Redémarrage automatique si ça plante | HF redémarre parfois les Spaces (maintenance) → le disque repart à zéro, **le bootstrap auto remplit tout** en 20-40 min. C'est prévu, pas un bug |
| Ton site GitHub Pages continue en bonus (plan B) | Pendant ces 20-40 min, l'app affiche "DONNÉE NON DISPONIBLE" au lieu d'inventer (§1) |

---

## ÉTAPE 1 — Créer ton compte Hugging Face (2 min)

1. Sur ton téléphone : **https://huggingface.co/join**
2. Email + mot de passe. Valide l'email reçu.
3. Aucune carte demandée. C'est fini.

## ÉTAPE 2 — Créer le Space (2 min)

1. Va sur **https://huggingface.co/new-space**
2. Remplis :
   - **Space name** : `prono-sport`
   - **SDK** : choisis **Docker** (IMPORTANT — pas Gradio !)
   - Template Docker : **Blank**
   - **Visibility** : Public (le gratuit ne propose pas de privé — nos données sont publiques de toute façon)
3. **Create Space**. Hugging Face te crée automatiquement un mini-dépôt avec un `README.md`.

## ÉTAPE 3 — Ajouter le fichier Docker (3 min, tout depuis le navigateur)

Dans ton Space : onglet **Files** → bouton **Add file** → **Create a new file**.

### Fichier unique — nom exact : `Dockerfile`
Copie le contenu de `deploy/hf-space/Dockerfile` (dans ce projet) et colle-le.
> ⚠️ **LA SEULE LIGNE À MODIFIER** : dans `ARG REPO_URL=https://github.com/TON-COMPTE/prono-sport.git`, remplace `TON-COMPTE` par **ton nom d'utilisateur GitHub** (celui du Guide 04). C'est tout.
> Les scripts de démarrage (`start_server.sh`, `bootstrap_data.sh`) sont déjà dans ton repo GitHub — le Dockerfile les récupère tout seul.

### Vérifier le README
Le `README.md` déjà créé par HF doit contenir ces lignes en haut (édite-le sinon) :
```yaml
---
title: PRONO SPORT 2.0
emoji: ⚽
colorFrom: green
colorTo: blue
sdk: docker
app_port: 7860
---
```

À chaque **Commit changes**, HF construit l'image automatiquement.

## ÉTAPE 4 — Suivre la construction (5-10 min)

- Onglet **Logs** (ou **Build** si visible) : tu vois l'image se construire.
- Quand tu vois `PRONO SPORT 2.0 en ligne sur le port 7860` → **c'est en ligne !**
- Onglet **App** : ton application s'affiche directement.
- Ton adresse permanente : `https://TON-PSEUDO-prono-sport.hf.space`

## ÉTAPE 5 — Le premier remplissage (20-40 min, automatique)

Au premier démarrage la base est vide : le **bootstrap** tourne en fond (logs : `[1/5]... [5/5] BOOTSTRAP TERMINE`).
Pendant ce temps l'app affiche "DONNÉE NON DISPONIBLE" — **c'est normal et honnête** (§1 : on n'invente jamais).
À la fin : 45 compétitions, ~9000 matchs, logos, pronos et Value Bets réels.

## ÉTAPE 6 — Anti-sommeil GRATUIT (5 min, recommandé)

Sans visite pendant 48 h, HF endort le Space. Solution gratuite :

1. Va sur **https://cron-job.org** → **Sign up** (email + mot de passe, **zéro carte**).
2. **Create cronjob** :
   - **Title** : `prono-sport`
   - **Address (URL)** : `https://TON-PSEUDO-prono-sport.hf.space` (ton adresse de l'étape 4)
   - **Schedule** : toutes les **10 minutes**
3. Sauvegarde. Désormais le Space reçoit une visite toutes les 10 min → **il ne dort jamais**.
   (Alternative : https://uptimerobot.com — gratuit, 50 moniteurs, toutes les 5 min.)

## ÉTAPE 7 — Cycle de vie normal

| Situation | Ce qui se passe | Que faire ? |
|---|---|---|
| Tous les jours | Scores live 75 s, nouveaux matchs 5 min, pronos recalculés 1 h | Rien — c'est automatique |
| Tu modifies le code sur GitHub | Dans le Space : **Settings → Factory rebuild** pour reprendre la dernière version | 1 bouton |
| HF redémarre le Space | Bootstrap auto (20-40 min) puis tout revient | Rien — patience |
| Space endormi (si pas d'étape 6) | Page "Space is sleeping" → bouton **Wake it up** | Fais l'étape 6 ! |

## Astuce
Ton **GitHub Pages** (Guide 04) reste actif en parallèle : utilise-le comme **secours** si le Space est en bootstrap, et le Space pour le **temps réel**. Deux adresses, zéro coût.

---
*Rappel (§38) : une probabilité, même forte, n'est jamais une certitude. Aucun gain garanti.*
