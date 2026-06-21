# Audit GarminSyncWeight v0.1.1

Date : 2026-06-21

## Ce qui était cassé ou incomplet

- Le pipeline backend produisait uniquement un rapport sans écriture Garmin réelle.
- `GarminClient` retournait des listes vides en production si le pont MCP n’était pas activé.
- Les méthodes Garmin d’écriture levaient systématiquement une erreur.
- L’ancienne route de prévisualisation a été supprimée et remplacée par `/api/sync/run` et `POST /api/sync`.
- Le statut Withings pouvait laisser croire que l’application était prête sur simple présence d’un token.
- Le moteur utilisait une fenêtre Garmin relative à la date du jour au lieu de la période demandée.
- Les anciens rapports runtime et documents historiques contenaient encore une terminologie de prévisualisation sans écriture.

## Ce qui était simulé

- Lecture Garmin existante.
- Écritures Garmin.
- Rapport de synchronisation sans appel d’écriture.
- UI orientée prévisualisation au lieu d’un lancement de synchronisation réel.

## Problèmes Garmin identifiés

- Le projet n’utilisait pas réellement les lectures/écritures Garmin dans le flux de production.
- `Taxuspt/garmin_mcp` était présent dans les commandes d’authentification, mais les volumes Docker ne persistaient pas `/home/app/.garminconnect`.
- La vérification Garmin reposait sur présence de fichiers + commande verify, sans tentative API côté client.
- Les payloads composition corporelle devaient passer par `add_body_composition(date, weight, ...)` et ne pas doubler avec `add_weigh_in`.

## Problèmes Withings identifiés

- Documentation interne indiquait à tort un mécanisme “PKCE-like”. Withings documente ici `state` CSRF, pas PKCE.
- Les appels Measure utilisaient `GET` avec `access_token` en query string au lieu de `POST` avec header bearer.
- Pas de route de test active Withings.
- Refresh token rotatif insuffisamment documenté côté stockage.
- Scope `user.metrics` non refusé explicitement à la configuration.

## Changements effectués

### Backend

- Nouveau `SyncEngine.run_sync()` réel et contrôlé.
- Préchecks actifs Withings et Garmin avant lecture/écriture.
- Conversion période civile Europe/Paris vers intervalle UTC `[début_jour, début_jour_suivant[`.
- Lecture Withings officielle `POST https://wbsapi.withings.net/measure` avec `Authorization: Bearer`.
- Pagination Withings `more`/`offset`.
- Types Withings ajoutés : poids, masse maigre, graisse %, masse grasse, muscle, eau, os, visceral fat, BMR, âge métabolique.
- Mapping Garmin conservateur : poids, graisse %, os, muscle, BMR, âge métabolique, visceral fat rating, BMI.
- Hydratation Withings en kg ignorée prudemment au lieu d’être convertie arbitrairement.
- `GarminClient` utilise les tokens compatibles `Taxuspt/garmin_mcp` et `garminconnect`.
- Écriture Garmin via `add_body_composition` uniquement pour éviter un doublon poids + composition.
- SQLite enrichi : tokens Withings complets, `sync_attempts`, `sync_events`, payload hash, erreurs, statuts.
- Idempotence : seules les décisions confirmées `synced` et `skipped_existing` bloquent une relance.
- Statuts possibles : `synced`, `skipped_existing`, `skipped_conflict`, `invalid`, `failed`.

### UI

- Route `/sync`.
- Bouton “Synchroniser maintenant”.
- Périodes aujourd’hui / 7 jours / 30 jours / personnalisée.
- États Withings et Garmin issus de vérifications actives.
- Boutons connecter/tester/déconnecter Withings.
- Boutons connecter/vérifier/déconnecter Garmin.

### Docker

- Installation de `git+https://github.com/Taxuspt/garmin_mcp` dans l’image.
- Volume persistant `garminsync_garmin:/home/app/.garminconnect`.
- Port bindé à `127.0.0.1:8010` dans compose.

### Documentation

- README réécrit.
- `docs/architecture.md` réécrit.
- `docs/security.md` réécrit.
- Fichiers historiques obsolètes supprimés.

## Commandes exécutées

| Commande | Résultat |
|---|---|
| `python -c "tomllib.load(...); py_compile..."` | OK |
| `pytest -q` baseline | `47 passed, 1 warning` |
| `ruff check .` | OK après corrections |
| `pytest -q` final | `47 passed, 1 warning` |
| Recherche terminologie obsolète dans code/docs/UI/logs texte | Aucune occurrence |
| Diagnostics LSP | Non exécuté : `basedpyright-langserver` non installé |
| Import FastAPI avec `PYTHONPATH=backend` | OK, version `0.1.1` |
| `docker compose config` | Non exécuté : `docker` non reconnu dans le PATH |
| `docker build .` | Non exécuté : `docker` non reconnu dans le PATH |

## Vérifications manuelles restantes

- Installer/ouvrir Docker puis lancer `docker compose config` et `docker build .`.
- Authentifier Garmin avec `garmin-mcp-auth` dans l’environnement cible.
- Vérifier `garmin-mcp-auth --verify` après redémarrage conteneur.
- Configurer Withings Developer avec le callback exact.
- Connecter Withings via UI et vérifier le refresh token après expiration.
- Lancer une synchronisation réelle sur une courte période contenant une mesure connue.
- Vérifier dans Garmin Connect que la mesure apparaît au bon jour civil Europe/Paris.
- Relancer la même période et vérifier qu’aucun doublon n’est créé.

## Limites restantes

- La validation live Garmin/Withings nécessite des credentials et un environnement Docker/Internet opérationnel.
- Le client Garmin runtime dépend de l’API `garminconnect`, utilisée par `Taxuspt/garmin_mcp`; si Garmin change son API, les erreurs sont remontées mais doivent être traitées manuellement.
- Aucune suppression ou modification de mesures Garmin existantes n’est implémentée dans cette version.
- Les routes sensibles restent locales ; une exposition publique nécessite une authentification forte externe.
