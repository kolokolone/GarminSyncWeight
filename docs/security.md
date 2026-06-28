# Sécurité — GarminSyncWeight

GarminSyncWeight manipule des données de santé, des tokens OAuth et des credentials Garmin temporaires. Le service doit rester local sauf authentification forte ajoutée par l'utilisateur.

## Principes

1. Aucun secret dans le code, Git, l'UI ou les logs.
2. Bind Docker sur `8010:8010` pour un accès LAN. Protéger les routes sensibles avec `ADMIN_API_TOKEN`.
3. Withings et Garmin doivent être vérifiés activement avant synchronisation.
4. La lecture Garmin et la lecture Withings doivent réussir avant toute écriture.
5. Aucune suppression ou modification de mesure Garmin existante.
6. Les conflits et doublons sont refusés.

## Secrets

Variables sensibles :

- `WITHINGS_CLIENT_SECRET`
- `GARMIN_EMAIL`, `GARMIN_PASSWORD`, OTP/MFA uniquement pendant l'appel d'authentification
- tokens Withings dans SQLite
- tokens Garmin dans `.garminconnect`

Redaction automatique : `access_token`, `refresh_token`, `client_secret`, `Authorization: Bearer`, `password`, `cookie`, `secret`, emails.

## Garmin

GarminSyncWeight utilise `Taxuspt/garmin_mcp` pour l'authentification. En Docker, `garmin-mcp-auth` est installé directement dans l'image (pas de téléchargement GitHub au runtime).

Pour le développement local :

```powershell
uvx --python 3.12 --from git+https://github.com/Taxuspt/garmin_mcp garmin-mcp-auth
uvx --python 3.12 --from git+https://github.com/Taxuspt/garmin_mcp garmin-mcp-auth --verify
```

Le backend ne stocke pas le mot de passe Garmin. Les tokens sont persistés dans `.garminconnect`.

## Withings

Le backend utilise OAuth2 Authorization Code avec `state` CSRF. Le refresh token Withings est rotatif : chaque réponse de refresh remplace le refresh token précédent en base.

Le scope `user.metrics` est obligatoire.

## Routes sensibles

Ces routes sont protégées par `ADMIN_API_TOKEN` :

- `POST /api/withings/auth/config` — sauvegarde des credentials Withings
- `POST /api/withings/auth/disconnect` — déconnexion Withings
- `POST /api/withings/auth/test` — test de connexion Withings
- `POST /api/garmin/auth/login` — authentification Garmin
- `POST /api/garmin/auth/reauthenticate` — reconnexion Garmin
- `POST /api/garmin/auth/disconnect` — déconnexion Garmin
- `POST /api/sync/run` — déclenchement de synchronisation
- `POST /api/sync` — alias sync
- `GET /api/sync/stream` — synchronisation SSE
- `GET /api/logs/{service}` — consultation des logs
- `POST /api/measurements/manual` — ajout mesure manuelle
- `DELETE /api/measurements/manual/{id}` — suppression mesure manuelle

Le callback OAuth Withings `/api/withings/auth/callback` n'est **jamais** protégé — il doit rester accessible pour le flux OAuth.

Si `ADMIN_API_TOKEN` n'est pas configuré (valeur vide), toutes les routes restent ouvertes (comportement legacy).

Lorsque `ADMIN_API_TOKEN` est configuré, le token peut être fourni via :
- Header HTTP : `Authorization: Bearer <token>`
- Paramètre d'URL : `?token=<token>`

## Healthcheck Docker

Le healthcheck Docker utilise `/api/healthz` (et non `/api/status`). Ce endpoint vérifie uniquement que FastAPI répond et que les dossiers locaux existent. Il ne teste pas Withings, Garmin, ni aucune API externe. Le conteneur ne sera jamais marqué `unhealthy` pour des raisons externes (API down, tokens expirés).

## Tests

Les tests vérifient la redaction, l'absence d'endpoint de suppression Garmin et les comportements de synchronisation sans doublon.
