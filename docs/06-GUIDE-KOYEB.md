# Guide 06 — Héberger PRONO SPORT 2.0 sur KOYEB (LE PLUS SIMPLE — 0 €, 24/7, depuis ton téléphone)

**Pourquoi Koyeb** : déploiement direct depuis ton GitHub en quelques clics — **aucun fichier à créer ni coller**
(tout est déjà dans ton repo : `Dockerfile.koyeb`). Gratuit à vie, toujours en ligne, 512 Mo RAM / 2 Go disque.

**Prérequis** : ton code est déjà sur GitHub (Guide 04 terminé).

---

## La vérité d'abord (§1 honnêteté)

| ✅ Ce que tu gagnes | ⚠️ Les limites honnêtes |
|---|---|
| **Toujours en ligne** (pas de mise en veille comme Render) | Selon les régions, Koyeb **peut** demander une carte bleue pour vérifier que tu n'es pas un robot (0 € débités — simple contrôle). S'ils te la demandent : **STOP, reviens me voir** → on bascule sur Hugging Face (Guide 05, carte **jamais** demandée) |
| Temps réel : live 75 s, ingestion 5 min, pronos recalculés 1 h | Petit processeur gratuit (0.1 vCPU) → pendant le recalcul horaire des pronos, le site peut ralentir 1-2 min. Normal |
| Zéro fichier à configurer : tout est prêt dans le repo | Redéploiement = disque repart à zéro → le **bootstrap auto** remplit tout en 20-40 min (prévu, pas un bug) |
| HTTPS + adresse permanente (`prono-sport-xxx.koyeb.app`) | 1 seul service gratuit par compte (c'est tout ce qu'il nous faut) |

*(Sources vérifiées : free tier Koyeb = 1 service / 512 Mo / sans carte dans la plupart des régions, certaines exigent la vérification.)*

---

## ÉTAPE 1 — Créer le compte (2 min)

1. Sur ton téléphone : **https://app.koyeb.com/auth/signup**
2. **Continue with GitHub** (le plus simple — tu as déjà GitHub).
3. **⚠️ Si une page demande une carte bancaire** : tu n'as RIEN à payer. Reviens me le dire, on passe au Guide 05 (Hugging Face). Sinon continue.

## ÉTAPE 2 — Créer le service (3 min)

1. Clique **Create Web Service** (ou **+ Create App**).
2. Choisis **GitHub** comme source → autorise Koyeb à lire tes repos (bouton **Install GitHub app** si demandé) → sélectionne **`prono-sport`**.
3. Koyeb détecte le projet. Règle ces 3 champs :
   - **Builder** : `Dockerfile`
   - **Dockerfile path** : `Dockerfile.koyeb`  *(c'est le fichier que j'ai mis à la racine du repo)*
   - **Port public** : `8000` (HTTP) — c'est le réglage par défaut de Koyeb, normalement rien à toucher.
4. **Instance** : choisis **Free** (eco / 0.1 vCPU / 512 Mo).
5. **Region** : `Paris` (fra) ou `Frankfurt` — le plus proche de toi.
6. **Service name** : `prono-sport`
7. Clique **Deploy**. ✅

## ÉTAPE 3 — Attendre la mise en route (5-10 min + 20-40 min)

- Onglet **Logs/Deployments** : tu vois le build puis `PRONO SPORT 2.0 en ligne sur le port 8000`.
- Le **bootstrap** remplit ensuite les vraies données en fond (`[1/5]` → `[5/5]`, 20-40 min).
- Pendant ce temps l'app affiche « DONNÉE NON DISPONIBLE » — c'est l'honnêteté §1, pas une panne.
- Ton adresse permanente : **`https://prono-sport-TONSERVICE.koyeb.app`** (visible en haut du service).

## ÉTAPE 4 — Vérifier (30 secondes)

Ouvre ton adresse → tu dois voir l'application PRONO SPORT 2.0 avec :
- les matchs du jour avec logos,
- l'onglet **VALUE BETS**,
- la **minute live** quand un match est en cours,
- l'assistant 💬 en bas.

## Cycle de vie normal

| Situation | Ce qui se passe | Que faire ? |
|---|---|---|
| Tous les jours | Live 75 s · nouveaux matchs 5 min · pronos recalculés 1 h | Rien — automatique |
| Tu changes le code sur GitHub | Koyeb **redéploie tout seul** (auto-deploy activé) → bootstrap auto 20-40 min | Patience |
| Site lent 1-2 min | Recalcul horaire des pronos sur petit CPU gratuit | Patience |
| « DONNÉE NON DISPONIBLE » longtemps | Bootstrap en cours ou source externe en panne | Regarde l'onglet Logs |

## Plans de secours (déjà prêts dans ton repo)

- **Koyeb bloqué par la carte** → Hugging Face Spaces : `docs/05-GUIDE-HUGGINGFACE.md` (jamais de carte)
- **Koyeb HS ponctuellement** → ton site GitHub Pages continue : `docs/04-GUIDE-GITHUB-PAGES.md`

---
*Rappel (§38) : une probabilité, même forte, n'est jamais une certitude. Aucun gain garanti.*
