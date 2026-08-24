# Guide 07 — Téléphone 100 % : GitHub en 2 COLLÉS avec TERMUX (aucun PC)

> ⚠️ **Termux refuse de s'installer sur ton téléphone ?** → Passe directement au **`docs/08-GUIDE-CODESPACES.md`** (100 % navigateur, rien à installer, même résultat).

**Ce que TU fais** : 4 gestes. **Ce que les commandes font** : TOUT LE RESTE (créer le repo, envoyer les 90 fichiers, tout).
**Prérequis** : ton compte GitHub existe déjà (juste le compte).

| # | Ton geste | Durée |
|---|---|---|
| 1 | Installer **Termux** depuis F-Droid (⚠️ PAS le Play Store) | 5 min |
| 2 | Appuyer **Télécharger** sur le fichier `prono-sport-code.zip` dans notre conversation Arena | 10 sec |
| 3 | Coller **COLLAGE 1** dans Termux + cliquer **Autoriser** sur la fenêtre | 10 min (téléchargements) |
| 4 | Coller **COLLAGE 2** + taper le **code à 8 lettres** sur la page GitHub (comme WhatsApp Web) | 3 min |

---

## 1️⃣ Installer Termux (une fois dans la vie)

1. Navigateur → **https://f-droid.org/en/packages/com.termux/** → **Download APK**
2. Ouvre le fichier téléchargé → **Autoriser** l'installation → **Installer**
3. Ouvre **Termux** : écran noir avec un `$` → prêt.

> ⚠️ Jamais depuis le Play Store : cette version y est abandonnée et plante.

## 2️⃣ Télécharger le ZIP (1 appui)

Dans notre conversation Arena, sur le fichier **prono-sport-code.zip** → **Télécharger**.
Il atterrit dans **Téléchargements**. Tu n'as RIEN d'autre à en faire.

## 3️⃣ COLLAGE 1 — préparer Termux

Dans Termux : **appui long → Coller**, puis **Entrée** :

```sh
pkg update -y && pkg upgrade -y && pkg install -y wget unzip git gh && termux-setup-storage
```

- ⏳ Ça télécharge plusieurs minutes (garde l'écran allumé, Wi-Fi si possible).
- Si une question orange/violette apparaît → appuie juste **Entrée**.
- À la fin, une fenêtre Android **"Autoriser l'accès aux fichiers"** s'ouvre → **Autoriser**.

## 4️⃣ COLLAGE 2 — tout est automatique

```sh
cd ~ && Z=$(ls -t ~/storage/downloads/prono-sport-code*.zip | head -1) && unzip -q -o "$Z" -d prono-sport && cd prono-sport && git init -b main && git config user.email "p@s.local" && git config user.name "patron" && git add -A && git commit -qm "PRONO SPORT 2.0" && gh auth login --hostname github.com --git-protocol https --web && gh repo create prono-sport --public --source=. --push && echo "===== TERMINE ====="
```

Pendant que ça tourne, Termux va te demander :

| Écran | Que faire |
|---|---|
| `Authenticate Git...? (Y/n)` | **Entrée** |
| `First copy your one-time code: XXXX-XXXX` | **Retiens le code** (8 caractères) |
| `Press Enter to open the browser...` | **Entrée** |
| Le navigateur s'ouvre sur GitHub | Connecte-toi si demandé, **tape le code**, clique **Authorize github** |
| Retourne dans Termux | ⏳ Il envoie les 90 fichiers tout seul (~1-2 min) |
| `===== TERMINE =====` s'affiche | 📸 **Envoie-moi une capture** — c'est gagné ! |

> Si le navigateur ne s'ouvre pas tout seul : ouvre manuellement **https://github.com/login/device** et tape le code.

## ✅ Vérification finale

Navigateur → **https://github.com/TON-PSEUDO/prono-sport**
Tu dois voir : `README.md`, `backend/`, `docs/`, `Dockerfile.koyeb`... → **ensuite : Guide 06 (Koyeb), 6 clics et c'est en ligne.**

---

## 🆘 Pannes fréquentes

| Ce que tu vois | Solution |
|---|---|
| `ls: ...prono-sport-code*.zip: No such file` | Le ZIP n'est pas dans Téléchargements → retape l'étape 2. Vérifie avec `ls ~/storage/downloads/` |
| `Permission denied` | La fenêtre Android n'a pas été autorisée → recolle COLLAGE 1 et clique **Autoriser** |
| `gh: command not found` | COLLAGE 1 a échoué au milieu → recolle-le entièrement |
| `name already exists` (à la fin) | Un repo `prono-sport` existe déjà → sur GitHub supprime-le (repo → Settings → tout en bas → Delete), puis recolle COLLAGE 2 |
| Code GitHub expiré | Recolle COLLAGE 2 — un nouveau code sera généré |
| Ça semble figé | 3G lente : patiente, ne ferme JAMAIS Termux pendant un collage |
| Autre message rouge | 📸 Capture → envoie-la-moi, je décode |

## 🔒 Sécurité (honnêteté)
Personne — moi inclus — ne peut se connecter à TON GitHub à ta place : c'est l'étape du **code à 8 lettres**, comme WhatsApp Web. Tout le reste est automatisé par les collages.

---
*Après ce guide, ton GitHub contient tout le projet, pour toujours. Tu n'y reviendras plus jamais.*
