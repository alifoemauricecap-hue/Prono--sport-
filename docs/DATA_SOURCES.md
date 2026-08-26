# PRONO SPORT 3.0 — SOURCES DE DONNÉES (état vérifié au 2026-08-26)

> Règle absolue (§2 du cahier des charges) : **aucune donnée inventée**.
> Chaque source ci-dessous a été réellement testée le 2026-08-26 depuis l'environnement de construction.
> Une source « À VALIDER » n'est **jamais** utilisée avant d'avoir passé le pipeline de découverte.

## Sources en production (gratuites, 0 €)

### 1. football-data.co.uk — ✅ VALIDÉE (source historique n°1)
| | |
|---|---|
| **Type** | CSV publics (pas d'API) |
| **Données** | Résultats, scores HT/FT, stats (tirs, tirs cadrés, corners, fautes, cartons), **xG/xGA** (saisons récentes), **cotes pré-match de ~15 bookmakers** + cotes de clôture, arbitres (D1), matchs à venir avec cotes actuelles (`fixtures.csv`) |
| **Couverture** | 22 championnats européens (E0, E1, E2, E3, EC, SC0-3, D1, D2, I1, I2, SP1, SP2, F1, F2, N1, B1, P1, T1, G1…) |
| **Historique** | **Saisons complètes** (2526 : 67 matchs E0 + 37 SP1 ingérés ; 2627 : 10 E0 + 16 SP1 en cours) |
| **Fréquence** | Quotidien en saison (les fichiers de saison se remplissent match après match) |
| **Temps réel** | Non (post-match + cotes pré-match) |
| **Clé** | Aucune |
| **CGU** | Données publiques ; usage personnel/analytique. Attribution appréciée : *football-data.co.uk* |
| **Fiabilité observée** | Très élevée — base de l'historique, toutes les lignes validées par le pipeline (1 rejet audité sur 130) |
| **Limites** | Pas de live, pas de compositions, pas de joueurs individuels, pas de xG en live |

### 2. ESPN (site.api.espn.com) — ✅ VALIDÉE (source live)
| | |
|---|---|
| **Type** | JSON publics (endpoints du site, non documentés officiellement) |
| **Données** | Scoreboards **live par minute**, statuts (LIVE/HT/FT), **logos équipes et ligues**, stades/villes, compositions quand publiées |
| **Couverture** | ~55 ligues mondiales + coupes (UCL, UEL, Libertadores, Sudamericana, Champions Cup, Qualifs CDM) |
| **Historique** | Saisons récentes (pas d'archive profonde) |
| **Fréquence** | Temps réel (boucle `syncLiveMatches` 75 s) |
| **Temps réel** | **Oui** |
| **Clé** | Aucune |
| **CGU** | Endpoints publics sans contrat explicite → **usage avec mesure, toujours cross-checké** ; aucun contournement |
| **Fiabilité observée** | Stable depuis des années (utilisée en 2.0) ; **risque : peut changer sans préavis** → tests de contrat + failover |
| **Limites** | Pas de cotes, pas de stats détaillées post-match (hors top ligues) |

### 3. OpenLigaDB — ✅ VALIDÉE (optionnelle, sans clé)
| | |
|---|---|
| **Type** | JSON publique |
| **Données** | Calendriers + résultats D1-D3 allemandes, classements |
| **Couverture** | Allemagne uniquement |
| **Clé** | Aucune · **CGU** : open data |
| **Rôle** | Cross-check des ligues allemandes (source de vérification) |

### 4. TheSportsDB — ✅ VALIDÉE (optionnelle, clé free)
| | |
|---|---|
| **Type** | JSON publique |
| **Données** | Métadonnées (ligues, équipes, badges, joueurs basiques), événements datés |
| **Clé** | Clé free publique (`3` ; la doc officielle cite aussi `123`) — **limites par méthode** (ex. `schedule day` : 3/j) |
| **Rôle** | Cross-check badges/métadonnées ; pas de source de scores |

### 5. Open-Meteo — ✅ VALIDÉE (météo, sans clé)
| | |
|---|---|
| **Type** | JSON publique |
| **Données** | Météo actuelle + prévisions par lat/long → **météo du stade à l'heure du match** (via `syncWeather`) |
| **Clé** | Aucune · **CGU** : gratuit non-commercial, attribution requise (affichée dans les rapports) |
| **Rôle** | Section « Météo » du Match Center et du rapport expert |

### 6. football-data.org — ✅ VALIDÉE (optionnelle, clé gratuite)
| | |
|---|---|
| **Free tier vérifié 2026-08-26** | 12 compétitions (PL, La Liga, Bundesliga, Serie A, Ligue 1, UCL, Eredivisie, Primeira, Championship, Brasileirão, WC, Euro), **10 req/min**, scores **delayés**, saison courante, classements |
| **Clé** | Gratuite (inscription) — `FOOTBALL_DATA_ORG_TOKEN` dans `.env` |
| **Limites** | Pas de joueurs, pas de stats match, pas de cotes en free |
| **Rôle** | 6ᵉ couche de vérification cross-source (statut → `VERIFIED` avec ESPN/fduk) |

## Sources de recherche en ligne (moteur de recherche approfondie)

### 7. Wikipedia (FR/EN) — ✅ VALIDÉE (recherche contextuelle)
| | |
|---|---|
| **Type** | API REST publique (`/api/rest_v1/page/summary`, opensearch) |
| **Données** | Contexte équipes/compétitions (historique, palmarès) → section « Contexte » du rapport expert + page Recherche |
| **Clé** | Aucune · **CGU** : contenu libre **CC BY-SA** — attribution affichée systématiquement |
| **Rôle** | Recherche approfondie : l'application interroge elle-même la source à la demande (0 €) |

### 8. StatsBomb Open Data — ✅ VALIDÉE (optionnelle, historique événementiel)
| | |
|---|---|
| **Type** | JSON publics sur GitHub |
| **Données** | **Niveau événement** (3 400+ événements/match), **xG**, freeze frames, compositions |
| **Couverture** | Compétitions **sélectionnées** (FA WSL, Women's WC 2023, sélections UCL/La Liga) |
| **Clé** | Aucune · **CGU** : usage recherche/analyse |
| **Rôle** | Profondeur historique événementielle quand la compétition est couverte |

## Sources en attente (pipeline de découverte — jamais utilisées avant validation)

| Source | Statut | Pourquoi pas encore |
|---|---|---|
| API-Football (free ~100 req/j) | 🔍 À VALIDER | Nécessite une clé gratuite (`API_FOOTBALL_KEY`) — utile pour **compositions** et stats joueurs ; activé dès qu'une clé est fournie |
| The Odds API (free 500 crédits/mois) | 🔍 À VALIDER | Clé gratuite (`ODDS_API_KEY`) — cotes live multi-bookmakers |
| worldfootball.net | 🔍 À VALIDER | Licence d'extraction non explicite → **pas de scraping** tant que non clarifié (§5) |
| FBref / Understat (xG) | 🔍 À VALIDER | Pas d'API officielle, pas de licence explicite → **pas de scraping** par défaut |
| Kaggle (datasets historiques) | 🔍 À VALIDER | Licence par dataset → vérification au cas par cas |

## Politique d'agrégation (résumé)

1. **Redondance** : les données importantes passent par ≥ 2 sources quand c'est possible (fduk + ESPN → `VERIFIED`).
2. **Conflit** : scores différents → `CONTRADICTORY`, les deux valeurs sont conservées avec leur provenance (jamais d'arbitrage).
3. **Fraîcheur** : chaque ligne porte `source_timestamp`/`fetched_at` ; au-delà du seuil → `STALE` (affiché `DATA DELAYED`).
4. **Failover** : source DOWN → repli sur la source validée ; aucune source → `DATA UNAVAILABLE`.
5. **Provenance** : `fixture.source_provider`, `source_event_id`, `raw_payload` — chaque donnée est traçable jusqu'à sa source.
