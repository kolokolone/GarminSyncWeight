<p align="center">
  <h1 align="center">GarminSyncWeight</h1>
</p>
<p align="center">Pont contrôlé entre Withings Body Cardio et Garmin Connect.<br/>Lecture, vérification, déduplication — écriture uniquement si tout est valide.</p>
<p align="center">
  <a href="docs/architecture.md">Architecture</a> ·
  <a href="docs/security.md">Sécurité</a> ·
  <a href="docs/mapping_withings_garmin.md">Mapping</a> ·
  <a href="AUDIT_GARMINSYNCWEIGHT.md">Audit</a>
</p>

---

## Pourquoi ?

Garmin ne se synchronise pas avec Withings. Cette application locale fait le pont de manière **prudente et contrôlée** : elle lit vos mesures Withings, vérifie l'état de vos comptes, détecte les doublons et les conflits, puis écrit uniquement les mesures valides et nouvelles dans Garmin Connect.

**Aucune suppression, aucune modification.** Seulement des `add_body_composition` vérifiés et idempotents.

### Ce qui est synchronisé

| Champ | Statut |
|---|---|
| `weight` (kg) | ✅ Direct |
| `percent_fat` | ✅ Withings type 6 |
| `bone_mass` (kg) | ✅ Withings type 88 |
| `muscle_mass` (kg) | ✅ Withings type 76 |
| `basal_met` | ✅ Withings |
| `metabolic_age` | ✅ Withings |
| `visceral_fat_rating` | ✅ Withings |
| `bmi` | ⚠️ Calculé (poids / taille²) |
| `percent_hydration` | ❌ Withings en kg, Garmin en % — ignoré |

## Démarrage rapide

```powershell
git clone https://github.com/dominique-m/GarminSyncWeight.git
cd GarminSyncWeight
uv sync
copy .env.example .env
# 🔴 Éditez .env avec vos identifiants Withings
./scripts/dev.ps1
```

Ouvrez [http://127.0.0.1:8010](http://127.0.0.1:8010) — le tableau de bord vous guide pour connecter Withings et Garmin.

```
http://127.0.0.1:8010       → Tableau de bord
http://127.0.0.1:8010/docs  → Documentation API (Swagger)
```

## Installation

### Avec Docker (recommandé)

```powershell
copy .env.example .env
# Éditez .env
docker compose up --build
```

Volumes persistants : `data/`, `logs/`, `runtime/`, `~/.garminconnect`.

### Sans Docker

```powershell
uv sync                     # Installe les dépendances
copy .env.example .env      # Configurez vos identifiants
./scripts/start.ps1         # Lance le serveur (sans reload)
./scripts/dev.ps1           # Lance avec --reload
```

Prérequis : Python ≥ 3.12, [`uv`](https://docs.astral.sh/uv/).

## Authentification

### Withings (OAuth2)

1. Créez une app sur [developer.withings.com](https://developer.withings.com/dashboard/)
2. Le callback doit être **exactement** `http://127.0.0.1:8010/api/withings/auth/callback`
3. Scope requis : `user.metrics`
4. Dans l'interface, cliquez sur **Connecter Withings**

Le refresh token est rotatif — chaque renouvellement est persisté automatiquement.

### Garmin (via Taxuspt/garmin_mcp)

```powershell
uvx --python 3.12 --from git+https://github.com/Taxuspt/garmin_mcp garmin-mcp-auth
uvx --python 3.12 --from git+https://github.com/Taxuspt/garmin_mcp garmin-mcp-auth --verify
```

Les tokens sont stockés dans `~/.garminconnect`. Le mot de passe Garmin n'est **jamais** conservé par l'application.

## Utilisation

### Interface web

- **Tableau de bord** : état Withings/Garmin, lancement de synchronisation
- **Historique** : mesures Withings avec statut Garmin
- **Statistiques** : tendances poids, graisse, IMC
- **Logs** : logs structurés JSONL avec redaction automatique
- **Réglages** : paramètres et API admin

### Ligne de commande

```powershell
# Statut
uv run python -m backend.app.cli status

# Configuration
uv run python -m backend.app.cli check-config

# Synchronisation
uv run python -m backend.app.cli sync --start-date 2026-06-21 --end-date 2026-06-21
```

### API HTTP

```http
POST /api/sync/run
{
  "start_date": "2026-06-21",
  "end_date": "2026-06-21",
  "timezone": "Europe/Paris"
}
```

Décisions possibles : `synced`, `skipped_existing`, `skipped_conflict`, `invalid`, `failed`.

## Fonctionnement

```
Withings OAuth → WithingsClient (getmeas) → WithingsParser
    → WithingsToGarminMapper
    → GarminClient (lecture existante)
    → Deduplicator (doublons, conflits)
    → GarminClient.add_body_composition ✍️
    → SyncStore + ReportBuilder
```

La synchronisation **refuse d'écrire** si :
- Withings ou Garmin n'est pas vérifié par appel API actif
- La lecture Withings ou Garmin échoue
- Le poids ou la date est absent
- Une mesure équivalente existe déjà dans Garmin (± 0.05 kg)
- Une mesure différente existe le même jour (± 0.2 kg → conflit)
- La clé d'idempotence locale est déjà `synced` ou `skipped_existing`

## Configuration

Copiez `.env.example` vers `.env` :

| Variable | Description | Défaut |
|---|---|---|
| `WITHINGS_CLIENT_ID` | ID client OAuth Withings | — |
| `WITHINGS_CLIENT_SECRET` | Secret client Withings | — |
| `USER_HEIGHT_M` | Taille en mètres (pour l'IMC) | — |
| `APP_TIMEZONE` | Fuseau horaire | `Europe/Paris` |
| `GARMIN_TOKEN_DIR` | Dossier des tokens Garmin | `~/.garminconnect` |
| `ADMIN_API_TOKEN` | Token pour les routes admin | — |
| `WEIGHT_DUPLICATE_EPSILON_KG` | Seuil doublon | `0.05` |
| `WEIGHT_CONFLICT_EPSILON_KG` | Seuil conflit | `0.2` |

## Développement

```powershell
uv sync --group dev          # Inclut pytest, ruff
uv run ruff check backend    # Lint
uv run pytest                # Tests (47+)
uv run pytest -k "test_run_sync" -v  # Test spécifique
./scripts/test.ps1           # Lint + tests
```

Le `PYTHONPATH` doit pointer vers `backend/` — les scripts le font automatiquement.

## Sécurité

- Bind sur `127.0.0.1` uniquement — **ne pas exposer publiquement** sans reverse proxy authentifié
- Redaction automatique dans les logs : tokens, secrets, emails
- Aucune suppression de données Garmin
- Tokens Garmin isolés dans `~/.garminconnect`
- Refresh tokens Withings persistés chiffrés dans SQLite
- State CSRF pour le flux OAuth Withings

[En savoir plus](docs/security.md)

## Limites

- L'API Garmin Connect n'est pas publique — des changements côté Garmin peuvent casser l'intégration
- `percent_hydration` n'est pas synchronisé (format incompatible)
- Pas de suppression de mesures Garmin existantes
- Pas d'authentification intégrée pour l'interface (restriction réseau recommandée)

---

<p align="center">
  <sub>v0.3.4 · Construit avec FastAPI, SQLite et le SDK garminconnect.<br/>Licence MIT.</sub>
</p>
