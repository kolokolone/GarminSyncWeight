# GarminSyncWeight v0.2.7

Application locale pour synchroniser les mesures de poids et de composition corporelle Withings vers Garmin Connect.

Le flux est réel mais prudent : l’application refuse d’écrire si Withings n’est pas vérifié, si Garmin n’est pas vérifié, si la lecture préalable échoue, si la mesure est invalide, déjà présente ou en conflit.

## Architecture

- Backend FastAPI : OAuth Withings, vérification Garmin, moteur de synchronisation, SQLite, logs.
- Frontend statique local : états Withings/Garmin, lancement sync, rapports, logs.
- Garmin : tokens et authentification via `Taxuspt/garmin_mcp` (`garmin-mcp-auth`, `garmin-mcp-auth --verify`) comme GarminToGPT.
- Withings : OAuth2 Authorization Code, `state` CSRF, refresh token rotatif, Measure `getmeas`.

## Données synchronisées

Champs envoyés à Garmin via `add_body_composition` quand disponibles et validés :

- `date`
- `weight` en kg, obligatoire
- `percent_fat`
- `bone_mass`
- `muscle_mass`
- `basal_met`
- `metabolic_age`
- `visceral_fat_rating`
- `bmi`
- `percent_hydration` (converti depuis la masse d'eau Withings en kg → %)

Champs ignorés : champs sans équivalent Garmin confirmé, valeurs incohérentes.

## Installation locale

```powershell
cd C:\Users\domin\Desktop\GarminSyncWeight
uv sync
copy .env.example .env
```

Configurer `.env` :

```env
WITHINGS_CLIENT_ID=...
WITHINGS_CLIENT_SECRET=...
WITHINGS_REDIRECT_URI=http://127.0.0.1:8010/api/withings/auth/callback
WITHINGS_SCOPE=user.metrics
GARMIN_TOKEN_DIR=%USERPROFILE%\.garminconnect
```

Lancer :

```powershell
uv run uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8010
```

Ouvrir : http://127.0.0.1:8010

## Withings OAuth

1. Créer une app sur https://developer.withings.com/dashboard/.
2. Ajouter exactement le callback : `http://127.0.0.1:8010/api/withings/auth/callback`.
3. Scope minimal : `user.metrics`.
4. Cliquer sur “Connecter Withings” dans l’UI.

Le backend stocke `userid`, `access_token`, `refresh_token`, `scope`, `token_type`, `expires_at`, `created_at`, `updated_at` dans SQLite. Avant chaque appel API, il rafraîchit le token si nécessaire et remplace le refresh token quand Withings en renvoie un nouveau.

## Garmin via Taxuspt/garmin_mcp

Authentification recommandée :

```powershell
uvx --python 3.12 --from git+https://github.com/Taxuspt/garmin_mcp garmin-mcp-auth
uvx --python 3.12 --from git+https://github.com/Taxuspt/garmin_mcp garmin-mcp-auth --verify
```

Les tokens sont persistés dans `~/.garminconnect` ou `GARMIN_TOKEN_DIR`. Le compose Docker monte ce dossier dans `/home/app/.garminconnect`.

## Synchronisation

API :

```http
POST /api/sync/run
{
  "start_date": "2026-06-21",
  "end_date": "2026-06-21",
  "timezone": "Europe/Paris"
}
```

CLI :

```powershell
uv run python -m backend.app.cli sync --start-date 2026-06-21 --end-date 2026-06-21
```

Décisions possibles :

- `synced`
- `skipped_existing`
- `skipped_conflict`
- `invalid`
- `failed`

Les décisions sont persistées dans SQLite avec clé d’idempotence, date locale, poids, hash de payload, réponse Garmin ou erreur.

## Docker

```powershell
docker compose up --build
```

Volumes :

- `garminsync_data:/app/data`
- `garminsync_logs:/app/logs`
- `garminsync_runtime:/app/runtime`
- `garminsync_garmin:/home/app/.garminconnect`

Le port est bindé sur `127.0.0.1:8010` par défaut. Ne pas exposer publiquement sans authentification forte, surtout via tunnel ou reverse proxy.

## Vérification Garmin Connect

Après une synchronisation, vérifier dans Garmin Connect que la mesure apparaît au jour civil attendu. Relancer la même période : l’application doit classer la mesure en `skipped_existing` ou déjà traitée, sans doublon.

## Limites connues

- L’écriture Garmin réelle nécessite des tokens valides et le comportement live de Garmin Connect peut changer.
- La composition corporelle est limitée aux champs acceptés par `add_body_composition`.
- Les tests automatisés utilisent des doubles contrôlés pour Withings/Garmin ; une validation live reste nécessaire avant usage prolongé.
