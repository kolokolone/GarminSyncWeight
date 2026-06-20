# Architecture GarminSyncWeight

## Vue d'ensemble

GarminSyncWeight est un microservice autonome qui récupère les mesures de poids et de composition corporelle depuis l'API Withings, les normalise, vérifie leur unicité par rapport aux données Garmin Connect existantes, et prépare une écriture contrôlée dans Garmin Connect.

## Flux de données

```text
Withings API (getmeas)
    ↓ (OAuth2)
WithingsClient → WithingsParser → BodyCompositionMeasurement
    ↓
WithingsToGarminMapper → GarminBodyCompositionCandidate
    ↓
Deduplicator (compare avec Garmin existant)
    ↓
SyncEngine → DryRunReport (fichier JSON)
    ↓
[Étape future] → GarminClient.add_body_composition()
```

## Composants

### Backend (FastAPI)

| Composant | Rôle |
|---|---|
| `config.py` | Configuration via variables d'environnement (pydantic-settings) |
| `logging_config.py` | Logs structurés JSONL, rotation, redaction |
| `models/withings.py` | Modèle canonique `BodyCompositionMeasurement` |
| `models/garmin.py` | Modèle Garmin `GarminBodyCompositionCandidate` |
| `models/sync.py` | Modèles de rapport et statuts |
| `services/withings_auth.py` | Flux OAuth2 Withings + refresh token |
| `services/withings_client.py` | HTTP client Withings API |
| `services/withings_parser.py` | Parse les groupes de mesures Withings |
| `services/mapper.py` | Mapping prudent Withings → Garmin |
| `services/garmin_client.py` | Client lecture Garmin (MCP ou mock) |
| `services/deduplicator.py` | Anti-doublon et détection de conflits |
| `services/sync_engine.py` | Orchestrateur du pipeline |
| `services/report_builder.py` | Sauvegarde et récupération des rapports |
| `storage/token_store.py` | Stockage persistant des tokens OAuth2 |
| `storage/sync_store.py` | Table d'idempotence et historique |
| `api/routes_status.py` | Endpoint de santé |
| `api/routes_auth.py` | Endpoints OAuth2 Withings |
| `api/routes_sync.py` | Endpoint dry-run |
| `api/routes_logs.py` | Endpoint logs avec redaction |

## Sécurité

- Bind localhost par défaut (`127.0.0.1:8010`)
- Aucun endpoint de suppression Garmin
- Aucune écriture Garmin sans garde-fou centralisé
- Redaction automatique des tokens dans les logs
- Base de données SQLite dans `data/` (hors git)
- `.env` ignoré par git

## Stockage

| Dossier | Contenu |
|---|---|
| `data/` | Base SQLite (tokens, sync_events) |
| `logs/` | Fichiers de logs JSONL avec rotation |
| `runtime/reports/` | Rapports dry-run JSON |

## Pipeline dry-run

1. Vérification du token Withings (refresh si nécessaire)
2. Appel Withings `getmeas` sur la période
3. Parsing des groupes de mesures → `BodyCompositionMeasurement[]`
4. Application de la stratégie journalière (`latest_per_day`)
5. Mapping → `GarminBodyCompositionCandidate[]`
6. Récupération des données Garmin existantes
7. Classification anti-doublon pour chaque candidat
8. Construction du rapport JSON
9. Sauvegarde du rapport dans `runtime/reports/`
10. Aucune écriture Garmin
