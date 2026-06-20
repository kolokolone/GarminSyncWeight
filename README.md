# GarminSyncWeight

Bridge sécurisé entre votre balance Withings Body Cardio et Garmin Connect.

**Version** : 0.1.0 — Dry-run pipeline uniquement. Aucune écriture Garmin réelle dans cette version.

## Objectif

Récupérer les mesures de poids et composition corporelle depuis l'API Withings,
les normaliser, vérifier les doublons/conflits avec Garmin Connect, puis
préparer une écriture contrôlée — **sans jamais écrire sans validation humaine**.

## État actuel

- ✅ Authentification OAuth2 Withings
- ✅ Récupération des mesures Withings (getmeas)
- ✅ Parsing et normalisation des unités
- ✅ Mapping prudent Withings → Garmin
- ✅ Anti-doublon et détection de conflits
- ✅ Rapport dry-run complet (JSON)
- ✅ Tests automatisés
- ✅ Docker
- ❌ Écriture Garmin réelle (prévue en v0.2+)

## Prérequis

- Windows 11 avec PowerShell 5.1+
- Python 3.12
- `uv` (gestionnaire de paquets)
- Compte développeur Withings avec credentials OAuth2
- Accès en lecture à Garmin Connect (via MCP)

## Installation

```powershell
# Cloner / Créer le projet
cd C:\Users\domin\Desktop\GarminSyncWeight

# Créer l'environnement virtuel et installer les dépendances
uv sync

# Copier et configurer les variables d'environnement
cp .env.example .env
# Éditer .env avec vos credentials Withings
```

## Configuration Withings

1. Créez une application sur https://developer.withings.com
2. Configurez l'URL de redirection OAuth2 :
   ```
   http://127.0.0.1:8010/api/withings/auth/callback
   ```
3. Copiez `Client ID` et `Client Secret` dans `.env`
4. Le scope requis est `user.metrics`

## Démarrage

```powershell
# Développement (avec rechargement automatique)
.\scripts\dev.ps1

# Production-like
.\scripts\start.ps1
```

Puis ouvrez `http://127.0.0.1:8010`.

## Authentification Withings

1. Allez sur `http://127.0.0.1:8010/docs`
2. Appelez `GET /api/withings/auth/start`
3. Vous êtes redirigé vers Withings — autorisez l'accès
4. Vous êtes redirigé vers l'application — token stocké

## Dry-run

```powershell
# CLI
python -m backend.app.cli dry-run --start-date 2026-06-01 --end-date 2026-06-19

# Script
.\scripts\dry-run.ps1 -StartDate 2026-06-01 -EndDate 2026-06-19

# API
curl -X POST http://127.0.0.1:8010/api/sync/dry-run \
  -H "Content-Type: application/json" \
  -d '{"start_date": "2026-06-01", "end_date": "2026-06-19"}'
```

## Statut

```powershell
python -m backend.app.cli status
# ou
curl http://127.0.0.1:8010/api/status
```

## Tests

```powershell
.\scripts\test.ps1
# ou
uv run pytest -v
```

## Docker

```powershell
# Build et lancement
docker compose up -d

# Logs
docker compose logs -f

# Arrêt
docker compose down
```

Le service écoute sur `127.0.0.1:8010` (non exposé publiquement).

## Structure du projet

```
backend/
  app/
    main.py              # Point d'entrée FastAPI
    config.py            # Configuration (pydantic-settings)
    logging_config.py    # Logs structurés JSONL
    cli.py               # CLI dry-run
    models/              # Modèles Pydantic
    services/            # Logique métier
    api/                 # Routes FastAPI
    storage/             # Base SQLite
  tests/                 # Tests unitaires
    fixtures/            # Données de test
docs/                    # Documentation
scripts/                 # Scripts PowerShell
data/                    # Données persistantes (hors git)
logs/                    # Logs (hors git)
runtime/reports/         # Rapports dry-run (hors git)
Dockerfile
docker-compose.yml
.env.example
```

## Sécurité

- Aucune écriture Garmin sans validation humaine
- Aucun token dans les logs
- Aucun endpoint DELETE
- Aucun secret dans Git
- Bind localhost par défaut

Voir `docs/security.md` pour les détails.

## Limites v0.1

- Aucune écriture Garmin réelle
- Le client Garmin MCP n'est pas connecté — les données Garmin
  existantes sont simulées (mock)
- L'analyse des conflits ne fonctionne qu'avec la fenêtre de
  recherche configurée
- Le frontend n'est pas implémenté

## Licence

MIT
