# Guide 08 — GitHub 100 % navigateur, entièrement EN FRANÇAIS (aucun PC, rien à installer)

Ton téléphone n'accepte pas Termux ? Aucun souci. GitHub te prête **un petit ordinateur gratuit DANS TON NAVIGATEUR**
(ça s'appelle « Codespaces » = « espaces de code »). Tu n'installes **rien** sur ton téléphone.
Tu vas juste **copier-coller UNE seule commande**, et elle fait tout le travail à ta place.

> ⚠️ **Important** : GitHub affiche ses boutons en anglais. Dans ce guide, chaque bouton anglais est
> **traduit en français entre guillemets** pour que tu saches exactement où appuyer.

## 📖 Petit lexique (garde-le sous les yeux)

| Ce que GitHub affiche (anglais) | Ça veut dire (français) |
|---|---|
| **Repository** | Dépôt (= ton dossier en ligne) |
| **New repository** | Nouveau dépôt |
| **Repository name** | Nom du dépôt |
| **Public** | Public (visible par tous — c'est ce qu'on veut) |
| **Add a README file** | Ajouter un fichier README (page de présentation) |
| **Create repository** | Créer le dépôt |
| **<> Code** (bouton vert) | Code — le bouton qui ouvre les options |
| **Local / Codespaces** (onglets) | « En local » / « Espaces de code en ligne » |
| **Create codespace on main** | Créer un espace de code sur la branche « main » |
| **Terminal → New Terminal** | Terminal → Nouveau terminal (la zone de commande noire) |
| **Paste** | Coller |
| **Delete** | Supprimer |
| **Settings** | Paramètres |

---

## 🟩 ÉTAPE 1 — Créer ton dépôt (1 minute)

1. Ouvre Chrome sur ton téléphone → tape l'adresse : **github.com/new**
   *(connecte-toi si GitHub te le demande — ton email + mot de passe habituels)*
2. Dans la case **Repository name** (« Nom du dépôt »), écris exactement : **prono-sport**
3. Laisse **Public** coché
4. ⚠️ **COCHE** la case **Add a README file** (« Ajouter un fichier README ») — **OBLIGATOIRE**, sinon l'ordinateur en ligne ne pourra pas démarrer
5. Appuie sur le bouton vert **Create repository** (« Créer le dépôt »)

✅ Résultat : tu arrives sur la page de ton dépôt, qui montre un fichier `README.md`.

## 💻 ÉTAPE 2 — Ouvrir ton ordinateur gratuit en ligne (3 minutes)

1. Sur la page de ton dépôt, appuie le bouton vert **<> Code**
2. Une petite fenêtre s'ouvre : en haut, appuie l'onglet **Codespaces** (à côté de « Local »)
3. Appuie **Create codespace on main** (« Créer un codespace sur main »)
4. ⏳ **Attends 1 à 3 minutes.** GitHub prépare ton ordinateur : tu vas voir apparaître un écran d'éditeur de code (fond sombre)

📱 **Astuce** : tourne ton téléphone **en horizontal (paysage)** — l'écran devient beaucoup plus lisible.

## ⌨️ ÉTAPE 3 — Ouvrir la zone de commande (30 secondes)

1. En haut à gauche, appuie l'icône **☰** (les trois petits traits = le menu)
2. Appuie **Terminal**, puis **New Terminal** (« Nouveau terminal »)
3. Une **zone noire** s'ouvre en bas de l'écran, avec un symbole `$` qui clignote — c'est là qu'on colle la commande

## 🪄 ÉTAPE 4 — Coller la commande magique (2 minutes)

1. **Copie le bloc entier ci-dessous. NE LE TRADUIS PAS et ne changes rien dedans** — le lien frais est déjà dedans :

```sh
cd /workspaces/prono-sport && curl -sL -o /tmp/ps.zip "https://tmpfiles.org/dl/REMPLACE-MOI-PAR-LE-LIEN-DU-JOUR" && ls -la /tmp/ps.zip && unzip -oq /tmp/ps.zip -d . && git add -A && git commit -qm "PRONO SPORT 2.0 complet" && git push && echo "===== TERMINE ====="
```

2. Dans la zone noire : **appui long** (garde le doigt appuyé) → **Coller**
3. Appuie sur **Entrée** ⏎ du clavier
4. ⏳ Tu vois des lignes défiler (téléchargement → extraction → envoi vers ton GitHub)

**Ce que fait cette commande** (pour ta culture, rien à faire) : elle télécharge le projet complet,
le décompresse, et l'envoie sur TON dépôt GitHub avec ton nom dessus. Tout est automatique.

## ✅ ÉTAPE 5 — Lire le résultat

- Tu vois à la fin : **`===== TERMINE =====`** → 🎉 **C'EST RÉUSSI !** Envoie-moi une capture d'écran
- Tu vois une erreur du genre *« cannot find zipfile »* ou *« No such file »* → le lien a expiré :
  écris-moi simplement **« lien mort »** et je t'en régénère un en 10 secondes
- Tu vois autre chose en rouge → **capture d'écran** et je décode

## 🔍 ÉTAPE 6 — Vérifier que tout est là (30 secondes)

Ouvre une nouvelle page : **github.com/TON-PSEUDO/prono-sport** (remplace par ton vrai pseudo).
Tu dois voir les dossiers : `backend/`, `docs/`, `deploy/`, et le fichier `Dockerfile.koyeb`. ✅

## 🧹 ÉTAPE 7 — Rendre l'ordinateur prêté (1 minute, honnêteté quota)

Ton compte gratuit inclut environ 120 heures d'ordinateur en ligne par mois. Tu n'as utilisé que ~10 minutes.
Pour ne rien gaspiller :

1. Va sur **github.com/codespaces**
2. Sur la ligne de ton codespace « prono-sport » → appuie **⋯** (les trois points = « Plus d'actions ») → **Delete** (« Supprimer »)
3. Le codespace disparaît — **mais ton code reste sur ton dépôt pour toujours** ✅

## 🚀 ÉTAPE 8 — La suite

Ton GitHub est rempli → retourne au **Guide 06 (Koyeb)** : 6 clics et ton site est **en ligne 24h/24 avec le temps réel**.

---

## 🆘 Tableau des pannes (en français)

| Ce que tu vois | Ce que ça veut dire | Ce que tu fais |
|---|---|---|
| L'onglet Codespaces n'apparaît pas | Le dépôt n'a pas de README | Refais l'ÉTAPE 1 avec la case cochée |
| Page blanche qui charge longtemps | 3G lente | Recharge la page, ou passe en Wi-Fi |
| Impossible de coller dans la zone noire | Le menu du terminal cache l'option | Fais un **appui long** directement sur la ligne avec le `$` |
| « cannot find zipfile » | Le lien de téléchargement a expiré | Écris-moi **« lien mort »** → nouveau lien instantané |
| « nothing to commit » | Le code est DÉJÀ envoyé | Passe à l'ÉTAPE 6 pour vérifier |
| Message sur le quota | Trop de codespaces ouverts | github.com/codespaces → supprime les anciens (Delete) |
| L'écran est tout petit / coupé | Mode portrait | Tourne le téléphone en horizontal |

## 🔒 Sécurité (la vérité, comme toujours)

- Le fichier voyage via un hébergeur temporaire (lien unique à durée limitée) — le code est **public par nature**, il n'y a **aucun mot de passe ni secret** dedans.
- Codespaces = service **officiel de GitHub**, gratuit, **sans carte bancaire**, tout se passe dans ton navigateur.
- Rien n'est installé sur ton téléphone : impossible d'abîmer quoi que ce soit.

---
*Une fois ce guide terminé, tu ne toucheras plus JAMAIS à cette étape : Koyeb lira ton GitHub automatiquement toute la vie du projet.*
