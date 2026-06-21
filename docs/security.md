# Sécurité — GarminSyncWeight

GarminSyncWeight manipule des données de santé, des tokens OAuth et des credentials Garmin temporaires. Le service doit rester local sauf authentification forte ajoutée par l’utilisateur.

## Principes

1. Aucun secret dans le code, Git, l’UI ou les logs.
2. Bind Docker sur `127.0.0.1:8010` par défaut.
3. Withings et Garmin doivent être vérifiés activement avant synchronisation.
4. La lecture Garmin et la lecture Withings doivent réussir avant toute écriture.
5. Aucune suppression ou modification de mesure Garmin existante.
6. Les conflits et doublons sont refusés.

## Secrets

Variables sensibles :

- `WITHINGS_CLIENT_SECRET`
- `GARMIN_EMAIL`, `GARMIN_PASSWORD`, OTP/MFA uniquement pendant l’appel d’authentification
- tokens Withings dans SQLite
- tokens Garmin dans `.garminconnect`

Redaction automatique : `access_token`, `refresh_token`, `client_secret`, `Authorization: Bearer`, `password`, `cookie`, `secret`, emails.

## Garmin

GarminSyncWeight utilise `Taxuspt/garmin_mcp` pour l’authentification :

```powershell
uvx --python 3.12 --from git+https://github.com/Taxuspt/garmin_mcp garmin-mcp-auth
uvx --python 3.12 --from git+https://github.com/Taxuspt/garmin_mcp garmin-mcp-auth --verify
```

Le backend ne stocke pas le mot de passe Garmin. Les tokens sont persistés dans `.garminconnect`.

## Withings

Le backend utilise OAuth2 Authorization Code avec `state` CSRF. Le refresh token Withings est rotatif : chaque réponse de refresh remplace le refresh token précédent en base.

Le scope `user.metrics` est obligatoire.

## Routes sensibles

Ces routes doivent rester locales ou protégées par un reverse proxy authentifié :

- configuration Withings ;
- callback OAuth ;
- authentification Garmin ;
- lancement de synchronisation ;
- consultation des logs ;
- consultation des statuts.

Ne pas exposer publiquement l’application sans authentification forte. Attention particulière aux tunnels Cloudflare ou reverse proxies.

## Tests

Les tests vérifient la redaction, l’absence d’endpoint de suppression Garmin et les comportements de synchronisation sans doublon.
