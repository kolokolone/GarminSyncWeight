# Architecture GarminSyncWeight

GarminSyncWeight est une application locale FastAPI + UI statique qui synchronise Withings vers Garmin Connect avec contrôles d’idempotence et de sécurité.

```text
Withings OAuth → WithingsClient(getmeas) → WithingsParser
    → WithingsToGarminMapper
    → GarminClient(read existing via garminconnect tokens from Taxuspt/garmin_mcp)
    → Deduplicator
    → GarminClient.add_body_composition
    → SyncStore + ReportBuilder
```

## Backend

| Composant | Rôle |
|---|---|
| `config.py` | Variables d’environnement, version, chemins, seuils |
| `withings_auth.py` | OAuth Withings, state CSRF, refresh token rotatif, vérification active |
| `withings_client.py` | Appels officiels `POST /measure action=getmeas` |
| `withings_parser.py` | Décodage `value × 10^unit`, Europe/Paris, types Withings |
| `mapper.py` | Mapping prudent vers champs Garmin supportés |
| `garmin_auth_service.py` | `garmin-mcp-auth` et `garmin-mcp-auth --verify` |
| `garmin_client.py` | Lecture/écriture Garmin avec tokens compatibles `Taxuspt/garmin_mcp` |
| `deduplicator.py` | Doublons, conflits, idempotence locale |
| `sync_engine.py` | Préchecks actifs, lectures, décisions, écritures, rapport |
| `sync_store.py` | `sync_attempts` et `sync_events` SQLite |
| `report_builder.py` | Rapports JSON `runtime/reports/sync-*.json` |

## États et décisions

La synchronisation refuse d’écrire si :

- Withings n’est pas configuré ou vérifié par appel API ;
- Garmin n’est pas vérifié par `garmin-mcp-auth --verify` et appel actif ;
- la lecture Withings échoue ;
- la lecture Garmin échoue ;
- le poids ou la date est absent ;
- Garmin contient déjà une mesure équivalente ;
- Garmin contient une mesure différente le même jour ;
- la clé d’idempotence locale est déjà `synced` ou `skipped_existing`.

Décisions persistées : `synced`, `skipped_existing`, `skipped_conflict`, `invalid`, `failed`.

## Stockage

- `data/withings_tokens.db` : tokens Withings, états OAuth, tentatives et résultats de sync.
- `/home/app/.garminconnect` en Docker : tokens Garmin créés par `Taxuspt/garmin_mcp`.
- `logs/` : logs structurés avec redaction.
- `runtime/reports/` : rapports JSON.

## Docker

Le compose bind le port sur `127.0.0.1:8010` et persiste `data`, `logs`, `runtime` et `.garminconnect`.
