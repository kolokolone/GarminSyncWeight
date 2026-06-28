# Déploiement Docker — GarminSyncWeight

Documentation complète pour déployer GarminSyncWeight avec Docker Compose.
Dernière mise à jour : version 0.3.6.

## Prérequis

- Docker et Docker Compose installés
- Accès à Internet pour télécharger l'image GHCR
- Un compte développeur [Withings](https://developer.withings.com/dashboard/) avec une application configurée
- Un compte Garmin Connect

## Installation rapide

1. Créez un dossier pour l'application, par exemple `/opt/garminsyncweight`
2. Copiez le `docker-compose.yml` (voir section « Fichier docker-compose.yml »)
3. Créez le dossier `config/` et le fichier `config/.env` avec vos variables
4. Lancez : `docker compose up -d`
5. Accédez à `http://IP_DU_SERVEUR:8010`

## Fichier docker-compose.yml

### Installation LAN direct

```yaml
services:
  garminsync:
    image: ghcr.io/kolokolone/garminsyncweight:latest
    container_name: garminsyncweight
    ports:
      - "8010:8010"
    volumes:
      - garminsync_data:/app/data
      - garminsync_logs:/app/logs
      - garminsync_runtime:/app/runtime
      - garminsync_garmin:/home/app/.garminconnect
      - garminsync_config:/app/config
    restart: unless-stopped
    init: true
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; resp = urllib.request.urlopen('http://127.0.0.1:8010/api/healthz', timeout=5); exit(0 if resp.status == 200 else 1)"]
      interval: 30s
      timeout: 5s
      start_period: 20s
      retries: 3
    stop_grace_period: 30s

volumes:
  garminsync_data:
  garminsync_logs:
  garminsync_runtime:
  garminsync_garmin:
  garminsync_config:
```

### Installation derrière reverse proxy

Pour une exposition HTTPS via un reverse proxy (Traefik, Caddy, Nginx Proxy Manager, etc.), ajoutez les labels ou la configuration réseau appropriés à votre proxy. Le conteneur GarminSyncWeight reste inchangé — seul le proxy gère le TLS.

Exemple avec Nginx :

```nginx
server {
    listen 443 ssl;
    server_name garmin.mondomaine.fr;

    location / {
        proxy_pass http://127.0.0.1:8010;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

Dans ce cas, vos variables d'URL doivent utiliser le domaine HTTPS :

```env
APP_BASE_URL=https://garmin.mondomaine.fr
WITHINGS_REDIRECT_URI=https://garmin.mondomaine.fr/api/withings/auth/callback
```

## Volumes persistants

| Volume | Chemin conteneur | Contenu |
|---|---|---|
| `garminsync_data` | `/app/data` | Base SQLite (tokens Withings, historique sync, mesures) |
| `garminsync_logs` | `/app/logs` | Logs structurés JSONL |
| `garminsync_runtime` | `/app/runtime` | Rapports de sync générés |
| `garminsync_garmin` | `/home/app/.garminconnect` | Tokens Garmin |
| `garminsync_config` | `/app/config` | Fichier `.env` persisté |

Tous ces volumes doivent être sauvegardés. Les plus critiques sont `garminsync_data` (tokens Withings + historique) et `garminsync_garmin` (tokens Garmin).

## Variables d'environnement indispensables

Fichier `config/.env` :

| Variable | Description | Obligatoire |
|---|---|---|
| `WITHINGS_CLIENT_ID` | ID client OAuth Withings | Oui |
| `WITHINGS_CLIENT_SECRET` | Secret client Withings | Oui |
| `WITHINGS_REDIRECT_URI` | URL de callback OAuth (doit correspondre à l'app Withings) | Oui |
| `APP_BASE_URL` | URL publique de l'application | Oui |
| `USER_HEIGHT_M` | Taille en mètres (pour calcul IMC) | Recommandé |
| `ADMIN_API_TOKEN` | Token pour protéger les routes sensibles | Recommandé (LAN) |
| `APP_TIMEZONE` | Fuseau horaire | Non (`Europe/Paris`) |
| `DATA_DIR` | Dossier données | Non (`/app/data`) |
| `LOG_DIR` | Dossier logs | Non (`/app/logs`) |
| `RUNTIME_DIR` | Dossier runtime | Non (`/app/runtime`) |
| `GARMIN_TOKEN_DIR` | Dossier tokens Garmin | Non (`/home/app/.garminconnect`) |

Exemple minimal pour un accès LAN :

```env
WITHINGS_CLIENT_ID=abc123...
WITHINGS_CLIENT_SECRET=def456...
WITHINGS_REDIRECT_URI=http://192.168.1.100:8010/api/withings/auth/callback
APP_BASE_URL=http://192.168.1.100:8010
APP_HOST=0.0.0.0
USER_HEIGHT_M=1.75
ADMIN_API_TOKEN=mon_token_secret
```

## Configuration Withings (côté développeur)

1. Allez sur [developer.withings.com](https://developer.withings.com/dashboard/)
2. Créez une application ou utilisez une application existante
3. Dans les paramètres de l'application, configurez l'URL de callback :
   - LAN direct : `http://IP_DU_SERVEUR:8010/api/withings/auth/callback`
   - Reverse proxy : `https://votre.domaine.fr/api/withings/auth/callback`
4. Le scope `user.metrics` est obligatoire
5. Copiez le Client ID et le Client Secret dans votre `config/.env`

## Authentification Garmin

L'image Docker contient `garmin-mcp-auth` installé localement (pas de téléchargement GitHub au runtime).

1. Dans l'interface web, allez dans Réglages → Garmin
2. Saisissez votre email et mot de passe Garmin
3. Si l'authentification à deux facteurs est activée, saisissez le code OTP
4. Les tokens sont stockés dans `/home/app/.garminconnect` (volume `garminsync_garmin`)

Le mot de passe Garmin n'est **jamais** conservé. Seuls les tokens de session sont persistés.

## Protection des routes sensibles (ADMIN_API_TOKEN)

Si vous déployez l'application en LAN, configurez `ADMIN_API_TOKEN` pour protéger les actions sensibles :

```env
ADMIN_API_TOKEN=mon_token_secret
```

Une fois configuré, les routes suivantes nécessitent le token :
- Configuration Withings (sauvegarde credentials, test connexion, déconnexion)
- Authentification Garmin (login, reconnexion, déconnexion)
- Synchronisation manuelle
- Consultation des logs
- Ajout/suppression de mesures manuelles

Le token peut être fourni de deux façons :
- Header HTTP : `Authorization: Bearer mon_token_secret`
- Paramètre d'URL : `?token=mon_token_secret`

Les routes en lecture seule (statut, historique, dashboard) restent accessibles sans token.

Le callback OAuth Withings (`/api/withings/auth/callback`) n'est **jamais** protégé — il doit rester accessible pour que Withings puisse rediriger l'utilisateur.

## Vérification du healthcheck

Docker utilise `/api/healthz` pour le healthcheck du conteneur. Ce endpoint vérifie uniquement que FastAPI répond et que les dossiers locaux existent. Il ne teste **pas** Withings, Garmin, ni aucune API externe.

```powershell
# Vérifier le healthcheck Docker
curl http://IP_DU_SERVEUR:8010/api/healthz
# → {"status":"healthy","checks":{"data":true,"logs":true,"runtime":true,"reports":true}}

# Vérifier le statut métier (interface utilisateur)
curl http://IP_DU_SERVEUR:8010/api/status
# → {"app_name":"GarminSyncWeight","version":"0.3.6","state":"ready",...}
```

**Important** : Le conteneur ne sera jamais marqué `unhealthy` parce que Withings ou Garmin est temporairement indisponible. Si le healthcheck échoue, c'est un problème de déploiement (dossier manquant, application crashée).

## Mise à jour

```powershell
# Télécharger la dernière image
docker compose pull

# Redémarrer avec la nouvelle image
docker compose up -d

# Vérifier que le nouveau conteneur est healthy
docker compose ps
```

Pour figer une version spécifique, remplacez `latest` par un tag de version dans `docker-compose.yml` :

```yaml
image: ghcr.io/kolokolone/garminsyncweight:0.3.6
```

## Sauvegarde et restauration

### Sauvegarde des volumes

```powershell
# Arrêter le conteneur
docker compose down

# Sauvegarder les volumes (remplacer /opt/garminsyncweight par votre chemin)
docker run --rm -v garminsyncweight_garminsync_data:/data -v /opt/backups:/backup alpine tar czf /backup/garminsync_data_$(date +%Y%m%d).tar.gz -C /data .
docker run --rm -v garminsyncweight_garminsync_garmin:/data -v /opt/backups:/backup alpine tar czf /backup/garminsync_garmin_$(date +%Y%m%d).tar.gz -C /data .
docker run --rm -v garminsyncweight_garminsync_config:/data -v /opt/backups:/backup alpine tar czf /backup/garminsync_config_$(date +%Y%m%d).tar.gz -C /data .

# Redémarrer
docker compose up -d
```

### Restauration

```powershell
docker compose down

# Restaurer les volumes
docker run --rm -v garminsyncweight_garminsync_data:/data -v /opt/backups:/backup alpine tar xzf /backup/garminsync_data_20260628.tar.gz -C /data
docker run --rm -v garminsyncweight_garminsync_garmin:/data -v /opt/backups:/backup alpine tar xzf /backup/garminsync_garmin_20260628.tar.gz -C /data
docker run --rm -v garminsyncweight_garminsync_config:/data -v /opt/backups:/backup alpine tar xzf /backup/garminsync_config_20260628.tar.gz -C /data

docker compose up -d
```

### Données critiques à sauvegarder

| Donnée | Volume | Impact si perdu |
|---|---|---|
| Tokens Withings | `garminsync_data` (`withings_tokens.db`) | Ré-authentification Withings nécessaire |
| Tokens Garmin | `garminsync_garmin` | Ré-authentification Garmin nécessaire |
| Historique sync | `garminsync_data` (`withings_tokens.db`) | Perte de l'historique, possibles re-syncs |
| Configuration `.env` | `garminsync_config` | Reconfiguration manuelle nécessaire |
| Logs | `garminsync_logs` | Perte des logs historiques (non critique) |
| Rapports | `garminsync_runtime` | Perte des rapports (régénérés à la prochaine sync) |

## Maintenance

### Vérifier que l'image utilisée est la dernière

```powershell
docker compose pull --dry-run
docker compose images
```

### Vérifier la persistance des tokens après redémarrage

```powershell
# Vérifier les tokens Withings
docker compose exec garminsync python -c "from app.storage.token_store import TokenStore; from app.config import get_settings; s=get_settings(); t=TokenStore(s.resolved_data_dir); print('Token présent' if t.load_token() else 'Token absent')"

# Vérifier les tokens Garmin
docker compose exec garminsync ls -la /home/app/.garminconnect/
```

### Changer d'URL sans casser le callback OAuth

1. Mettez à jour `APP_BASE_URL` et `WITHINGS_REDIRECT_URI` dans `config/.env`
2. Mettez à jour l'URL de callback dans les paramètres de l'application Withings sur developer.withings.com
3. Redémarrez : `docker compose up -d`
4. Si vous aviez déjà des tokens Withings, déconnectez/reconnectez Withings dans l'interface

### Que faire si le callback OAuth Withings échoue ?

1. Vérifiez que `WITHINGS_REDIRECT_URI` dans `config/.env` correspond **exactement** à l'URL configurée dans l'application Withings
2. Vérifiez que l'URL est accessible depuis Internet (Withings redirige le navigateur de l'utilisateur, pas un appel serveur)
3. Si vous utilisez un reverse proxy, vérifiez qu'il ne modifie pas le chemin de l'URL
4. En LAN direct sans DNS, utilisez l'adresse IP locale dans l'URL

### Conteneur unhealthy ?

1. Vérifiez les logs : `docker compose logs garminsync`
2. Vérifiez `/api/healthz` : `curl http://IP:8010/api/healthz`
3. Vérifiez que les dossiers de volumes existent : `docker compose exec garminsync ls /app/data /app/logs /app/runtime`
4. Vérifiez les permissions : `docker compose exec garminsync ls -la /app/`
5. Si un volume est corrompu, restaurez depuis une sauvegarde

## Diagnostic des erreurs classiques

| Symptôme | Cause probable | Solution |
|---|---|---|
| Le conteneur redémarre en boucle | `.env` manquant ou mal configuré | Vérifiez `config/.env`, les variables Withings sont-elles renseignées ? |
| `unhealthy` dans `docker ps` | Dossier requis manquant | Vérifiez les volumes, recréez le conteneur |
| Callback Withings = "page non trouvée" | `WITHINGS_REDIRECT_URI` incorrect | Vérifiez l'URL dans `.env` et dans l'app Withings |
| "Garmin non connecté" après redémarrage | Tokens Garmin non persistés | Vérifiez le volume `garminsync_garmin` |
| Sync échoue après mise à jour | Changement de version non compatible | Vérifiez les logs, essayez un tag de version antérieur |
| "Token admin requis" dans l'interface | `ADMIN_API_TOKEN` configuré mais pas fourni | Ajoutez `?token=...` à l'URL ou configurez le token dans l'UI |
| Port 8010 déjà utilisé | Conflit avec un autre service | Changez le port dans `docker-compose.yml` |

## Arrêt et redémarrage

```powershell
# Arrêter
docker compose down

# Redémarrer
docker compose up -d

# Redémarrer sans recréer (garde les volumes)
docker compose restart
```

## Structure de l'image Docker

L'image est basée sur `python:3.12-slim`. Elle contient :

- Les dépendances Python installées via `uv sync --frozen` (versions exactes du `uv.lock`)
- `garmin-mcp-auth` installé depuis GitHub (commit figé au build)
- Le backend FastAPI dans `/app/backend`
- Le frontend statique dans `/app/frontend/out`

Le conteneur s'exécute en tant qu'utilisateur non-root `app`. Le port 8010 est exposé.
L'image est publiée sur GitHub Container Registry : `ghcr.io/kolokolone/garminsyncweight`.

## Déploiement avec Dockge

Dockge est compatible avec le `docker-compose.yml` standard. Collez simplement le contenu du compose dans Dockge, configurez les variables d'environnement, et déployez.

Les volumes nommés sont gérés automatiquement par Dockge. Assurez-vous que le chemin `config/.env` est accessible (Dockge permet de monter des volumes bind ou nommés).
