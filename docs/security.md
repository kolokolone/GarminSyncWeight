# Sécurité — GarminSyncWeight

## Principes

1. **Aucune écriture Garmin sans validation humaine explicite**
2. **Aucun secret dans le code, les logs, ou Git**
3. **Aucun endpoint de suppression Garmin**
4. **Bind localhost par défaut**

## Secrets

### Variables d'environnement (`.env`)

Les secrets suivants sont chargés depuis `.env` (jamais versionné) :

- `WITHINGS_CLIENT_ID`
- `WITHINGS_CLIENT_SECRET`

### Tokens OAuth2

Les tokens Withings sont stockés dans `data/withings_tokens.db` (SQLite).
Le fichier est exclu de Git via `.gitignore` (`*tokens*`).

### Redaction automatique

Les patterns suivants sont systématiquement masqués par `[REDACTED]`
dans les logs et les réponses API :

- `access_token`
- `refresh_token`
- `client_secret`
- `Authorization: Bearer`
- `password`, `passwd`
- `cookie`
- `secret`
- Adresses email

### Fichiers exclus de Git

```gitignore
.env
.env.*
!.env.example
logs/*
runtime/*
data/*
*tokens*
*secret*
*password*
```

## Garmin — Garde-fous d'écriture

Toute écriture dans Garmin est protégée par **8 conditions** :

1. `ENABLE_GARMIN_WRITES=true`
2. `FIRST_WRITE_CONFIRMATION_REQUIRED=false` (ou confirmation persistée)
3. Argument CLI `--execute` obligatoire
4. Mode `dry_run=False`
5. Statut anti-doublon = `new_candidate` uniquement
6. `idempotency_key` non déjà écrite
7. Poids valide (20-300 kg)
8. Méthode Garmin autorisée explicitement

Si une seule condition n'est pas remplie → refus avec message explicite.

### Interdictions absolues

- **Aucun appel à `delete_weigh_ins`**
- **Aucun endpoint DELETE exposé**
- **Aucun remplacement automatique de données**
- **Aucune écriture sans confirmation**
- **Aucune écriture en cas de conflit**
- **Aucune écriture en cas de doublon probable**

## API locale

- Écoute sur `127.0.0.1:8010` par défaut
- Non exposée publiquement
- Si exposition Docker, binder sur `127.0.0.1` uniquement
- Variable `APP_HOST` documentée comme "non recommandée" pour `0.0.0.0`

## Logs

- Format JSONL structuré
- Fichiers séparés par sous-système
- Rotation automatique (10 Mo, 5 fichiers)
- Redaction centralisée avant écriture
- Aucun token dans les logs (vérifié par test automatisé)

## Tests de sécurité

Les tests suivants vérifient la sécurité :

- `test_log_redaction_tokens` — tokens masqués dans les logs
- `test_log_redaction_authorization_header` — header Authorization masqué
- `test_log_redaction_password` — mots de passe masqués
- `test_log_redaction_client_secret` — client_secret masqué
- `test_log_redaction_email` — emails masqués
- `test_no_delete_endpoint_available` — aucun endpoint de suppression
- `test_execute_blocked_by_default` — écriture bloquée par défaut
- `test_dry_run_never_calls_write` — dry-run n'écrit jamais
