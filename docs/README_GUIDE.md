# Guide de maintenance du README

Ce document définit comment écrire, modifier et maintenir le `README.md`.

## Objectif

Le README est la **première chose qu'un humain lit**. Il doit répondre en moins de 30 secondes à :
1. C'est quoi ce projet ?
2. Pourquoi j'en ai besoin ?
3. Comment je le lance ?

Tout le reste — architecture, sécurité, détails techniques — est secondaire et renvoyé vers `docs/`.

## Structure obligatoire (ordre)

1. **Header** — titre + baseline (1 phrase) + liens docs
2. **Pourquoi ?** — problème résolu, proposition de valeur
3. **Ce qui est synchronisé** — tableau des champs avec statut visuel (✅⚠️❌)
4. **Démarrage rapide** — 4 commandes max, résultat visible immédiatement
5. **Installation** — Docker d'abord, puis sans Docker
6. **Déploiement Docker** — lien vers docs/DOCKER.md, résumé 2 lignes
7. **Authentification** — Withings puis Garmin, instructions concrètes
8. **Utilisation** — interface web, CLI, API HTTP
9. **Fonctionnement** — pipeline visuel + règles métier critiques
10. **Configuration** — tableau des variables .env
11. **Développement** — commandes pour les contributeurs
12. **Sécurité** — 5 points max, lien vers `docs/security.md`
13. **Limites** — ce que l'appli ne fait pas (honnêteté)
14. **Footer** — licence, stack

## Règles d'écriture

### Ton
- Direct, pas marketing. On n'est pas en train de vendre.
- Pas de superlatifs ("incroyable", "révolutionnaire", "puissant").
- Pas d'excuses non plus ("c'est encore en dev", "désolé c'est pas parfait").
- Le français du README est concis et technique, pas littéraire.

### Format
- **Un bloc de code par exemple.** Pas de paragraphes de 15 lignes autour.
- **Les tableaux** pour les données structurées (champs, config, plateformes).
- **Les listes à puces** pour les règles et contraintes.
- Pas de `> [!NOTE]` ou autres callouts GitHub — trop lourd pour un petit projet.
- Les chemins de fichiers en backticks : `data/withings_tokens.db`.
- Les URLs d'API en blocs HTTP : `POST /api/sync/run`.

### Longueur
- Chaque section doit tenir dans une capture d'écran sans scroll.
- Si une section dépasse 20 lignes, c'est qu'elle devrait être dans `docs/`.
- Le README entier ne doit pas dépasser ~150 lignes effectives (hors code blocks).

## Ce qui DOIT être dans le README

- La commande exacte pour lancer le projet en local
- Les URLs de l'app (interface, docs API)
- Les prérequis (Python ≥ 3.12, uv, Docker optionnel)
- La configuration minimale (.env.example → config/.env pour Docker, .env pour dev local)
- Les instructions d'auth Withings ET Garmin (les deux sont obligatoires)
- Les décisions de sync possibles (`synced`, `skipped_existing`, etc.)
- La règle : **aucune suppression, aucune modification** des données Garmin
- Les commandes de dev : `uv run ruff check backend`, `uv run pytest`
- Le lien vers la documentation Docker complète (docs/DOCKER.md)
- La mention que l'image est sur GHCR (`ghcr.io/kolokolone/garminsyncweight`)

## Ce qui NE DOIT PAS être dans le README

- Le détail du mapping Withings → Garmin → renvoyer vers `docs/mapping_withings_garmin.md`
- L'architecture complète des composants → `docs/architecture.md`
- Les menaces de sécurité détaillées → `docs/security.md`
- L'historique des bugs et corrections → `AUDIT_GARMINSYNCWEIGHT.md`
- Les secrets, tokens, ou identifiants réels
- Des explications sur le fonctionnement interne de SQLite, FastAPI, ou garminconnect
- Des justifications longues ("on a choisi X parce que Y et Z...") — une phrase max
- Le changelog
- Les instructions de contribution détaillées (pas de CONTRIBUTING.md prévu)

## Informations critiques à maintenir à jour

Quand ces choses changent, le README **doit** être mis à jour :

| Élément | Où dans le README | Impact si obsolète |
|---|---|---|
| Version (pyproject.toml) | Header ou footer | Confusion sur les fonctionnalités |
| Champs synchronisés | Tableau "Ce qui est synchronisé" | Attentes fausses de l'utilisateur |
| Commandes de lancement | Démarrage rapide / Installation | L'utilisateur ne peut pas lancer l'appli |
| URLs et ports | Démarrage rapide | L'utilisateur ne trouve pas l'appli |
| Prérequis | Installation | L'utilisateur part avec une mauvaise config |
| Instructions d'auth Garmin | Authentification | L'utilisateur ne peut pas se connecter |
| Commandes de dev | Développement | Les contributeurs perdent du temps |
| Nouvelles limites | Limites | Fausse confiance dans l'appli |
| Configuration Docker | docs/DOCKER.md | L'utilisateur ne peut pas déployer |

## Convention de nommage

- `README.md` — version stable actuelle (format OpenCode-style)
- `README_old.md` — version legacy (conservée pour référence historique)
- Quand une refonte est nécessaire : créer `README_vN.md`, puis renommer l'ancien en `README_old.md` et le nouveau en `README.md`

## Checklist avant publication

Avant de remplacer le README principal :

- [ ] Toutes les commandes ont été testées (copier-coller dans un terminal)
- [ ] Les URLs sont correctes et accessibles
- [ ] Le tableau de configuration correspond exactement à `.env.example`
- [ ] La version affichée correspond à `pyproject.toml`
- [ ] Les liens vers `docs/` sont valides (les fichiers existent)
- [ ] Aucun secret, token ou identifiant réel n'est présent
- [ ] Le fichier fait moins de 150 lignes (hors code blocks)
- [ ] La section "Pourquoi ?" répond à la question en moins de 4 phrases
- [ ] La section "Démarrage rapide" fait 4 commandes maximum
- [ ] Les champs synchronisés listés correspondent au code dans `backend/app/services/mapper.py`
