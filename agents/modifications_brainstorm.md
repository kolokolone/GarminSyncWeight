# Modifications Brainstorm — 2026-06-28

## Résumé

Audit complet de la séparation frontend/backend de GarminSyncWeight. Trois violations critiques découvertes : (1) le calcul de l'IMC est fait en double dans le frontend (`renderMappingTable` et `renderCompactPreview` ligne 1229-1234) alors que le backend le calcule déjà dans `mapper.py`, (2) les dates de période de synchronisation sont calculées côté frontend (`runSync` ligne 765-767) sans validation backend, et (3) le flux OTP Garmin est confus — le champ OTP est toujours visible dans le formulaire, aucun bouton "Valider l'OTP" dédié n'existe, et le backend relance tout le processus `garmin-mcp-auth` à chaque tentative. La navigation frontend est déjà cohérente (Tableau de bord / Historique / Statistiques / Réglages / Logs). Le `/api/status` est correctement caché 60s avec `stale_while_revalidate`. `docs/ARCHITECTURE_FRONTEND_BACKEND.md` n'existe pas et doit être créée.

---

## Demande originale

```
Tu dois auditer puis corriger l'architecture de l'application GarminSyncWeight afin de garantir une séparation nette entre backend et frontend.
[... voir agents/modification.txt pour le texte complet ...]
```

---

## État des lieux de l'audit

### Ce que le backend fait déjà (✅ correct)

- **Sync engine** (`sync_engine.py` L61-203) : orchestre toute la sync (check → read → dedupe → write → report) ✅
- **Mapper** (`mapper.py` L98-113) : calcule l'IMC (`weight / height²`) avec `quantize(Decimal("0.1"))`, priorise la valeur Withings si présente ✅
- **Parser** (`withings_parser.py` L120-126) : calcule aussi l'IMC dans `BodyCompositionMeasurement.bmi` ✅
- **Deduplicator** (`deduplicator.py`) : toute la logique de déduplication ✅
- **Period validation** (`sync_engine.py` L76-77) : `if end_day < start_day: raise ValueError` ✅
- **Timezones** (`sync_engine.py` L73, L428-430) : normalisation timezone ✅
- **All external API calls** : Withings et Garmin sont appelés exclusivement côté backend ✅
- **Report generation** (`report_builder.py`) : backend uniquement ✅
- **SSE events** (`routes_sync.py` L166-198, `sync_engine.py` L88-196) : événements qualifiés (`start`, `parsed`, `garmin_fetched`, `candidate`, `complete`, `error`, `report`) ✅
- **`/api/status` caching** (`routes_status.py` L108) : caché 60s ✅

### Ce que le frontend fait à tort (❌ violations)

1. **Calcul IMC** — `app.js` L536-544 (`renderMappingTable`) et L1229-1234 (`renderCompactPreview`) :
   ```javascript
   const hM = hCm / 100;
   const bmi = lm.weight_kg / (hM * hM);
   tiles.push(["IMC", Math.round(bmi * 10) / 10]);
   ```
   Le frontend stocke `state._heightCm` dans `localStorage` et recalcule l'IMC localement. Le backend le calcule déjà.

2. **Calcul de période** — `app.js` L712-714 et L765-767 :
   ```javascript
   const pStart = new Date(Date.now() - (state._periodDays - 1) * 86400000);
   const pStartStr = pStart.toISOString().slice(0, 10);
   ```
   Le frontend calcule `start_date` à partir du nombre de jours sans validation backend.

3. **Flux OTP Garmin** — `app.js` L2026-2066 :
   - Le champ OTP (`#g-otp`) est toujours visible dans le formulaire, même sans demande MFA
   - Un seul bouton "Connecter Garmin" soumet tout (email + password + otp)
   - Aucun bouton "Valider le code OTP" distinct
   - Le message `needs_otp` du backend n'est pas exploité pour afficher une UI dédiée

### Ce qui est déjà correct (✅ conforme)

- **Navigation** : HTML (Tableau de bord, Historique, Statistiques, Réglages, Logs) = code JS (`PATH_TO_PAGE`) = routes (`PAGE_URLS`) ✅
- **Pas d'appels directs à Garmin/Withings** depuis le frontend ✅
- **Pas de logique de décision de sync** dans le frontend (le `runSync` se contente d'afficher les événements SSE) ✅
- **Pas de secrets dans le frontend** ✅
- **`/api/status` est rapide** grâce au cache 60s ✅

---

## Fichiers concernés

| Fichier | Rôle dans les modifications |
|---|---|
| `frontend/out/assets/app.js` | Supprimer calcul IMC local (2 endroits), supprimer calcul de période, restructurer formulaire Garmin OTP en 2 étapes |
| `frontend/out/index.html` | Pas de changement nécessaire — les blocs OTP sont créés dynamiquement dans app.js |
| `backend/app/services/mapper.py` | Déjà OK — l'IMC est calculé backend. Vérifier que `bmi` est bien inclus dans `mapped_fields` |
| `backend/app/api/routes_measurements.py` | Ajouter `bmi_info` structuré dans `latest_measurement` et `HistoryMeasurementItem` |
| `backend/app/models/sync.py` | Ajouter `bmi: float | None` et `bmi_source: str | None` à `HistoryMeasurementItem` |
| `backend/app/services/garmin_auth_service.py` | Ajouter mécanisme de session temporaire (`auth_session_id`) pour le flux OTP en 2 étapes |
| `backend/app/api/routes_garmin_auth.py` | Modifier `/login` pour accepter `auth_session_id` + `otp` sans `email`/`password` au 2e appel |
| `backend/app/models/auth.py` | Ajouter `auth_session_id` à `GarminLoginRequest`, ajouter `error_code` à `GarminAuthResult` |
| `backend/app/api/routes_sync.py` | Ajouter champ `period` optionnel dans `SyncRequest`, retourner `resolved_start`/`resolved_end` |
| `backend/app/services/sync_engine.py` | Ajouter `_resolve_period()` avec validation (inversée, future, trop longue, timezone) |
| `backend/tests/test_mapping.py` | Ajouter tests IMC : poids+taille valide, taille absente, taille invalide, arrondi, Withings vs calculé |
| `backend/tests/test_sync.py` | Ajouter tests validation période : inversée, future, trop longue, timezone |
| `backend/tests/test_garmin_api.py` | Ajouter tests flux OTP : sans OTP, OTP requis, OTP valide, OTP invalide, session expirée |
| `docs/ARCHITECTURE_FRONTEND_BACKEND.md` | **NOUVEAU** — documentation de la frontière de responsabilité |
| `docs/README_GUIDE.md` | Ajouter sections "Séparation frontend / backend" et "Connexion Garmin avec OTP" |

---

## Étapes d'implémentation

### Étape 1 — Supprimer le calcul d'IMC du frontend et enrichir l'API backend

- **Fichier(s)** : `backend/app/models/sync.py`, `backend/app/api/routes_measurements.py`, `frontend/out/assets/app.js`
- **Description** : Le backend calcule déjà l'IMC dans `mapper.py` (L98-113) — avec priorité à la valeur Withings si présente, sinon calcul à partir de `user_height_m`. Il faut enrichir la réponse API pour exposer ce calcul de façon structurée, et supprimer les 2 calculs IMC locaux du frontend.
- **Changements précis** :
  1. Dans `HistoryMeasurementItem` (`models/sync.py` L179-191), ajouter :
     ```python
     bmi: float | None = None
     bmi_source: str | None = None  # "withings" | "computed_backend"
     ```
  2. Dans `routes_measurements.py` `_compute_latest_preview()` L296-308, remplacer le simple `"bmi": float(latest.bmi) if latest.bmi else None` par un objet structuré :
     ```python
     "bmi": {
         "value": float(latest.bmi) if latest.bmi else None,
         "source": "withings" if latest.bmi and latest.bmi == measurement.bmi else "computed_backend",
         "inputs": {
             "weight_kg": float(latest.weight_kg) if latest.weight_kg else None,
             "height_cm": int(settings.user_height_m * 100) if settings.user_height_m else None
         }
     }
     ```
     ⚠️ Noter que cela change la structure du champ `bmi` de `float | None` à `dict | None` dans `latest_measurement`. C'est un breaking change mais le frontend est le seul consommateur.
  3. Dans `routes_measurements.py` `get_measurement_history()` L559-625, enrichir chaque `HistoryMeasurementItem` avec `bmi` et `bmi_source` depuis le mapper.
  4. Dans `frontend/out/assets/app.js`, supprimer le calcul IMC local :
     - **`renderMappingTable()`** L536-544 : supprimer le bloc `const localBmi = ...` (L536-544) et l'override conditionnel (L556-561). Lire directement `preview.latest_measurement.bmi?.value` et `preview.latest_measurement.bmi?.source`.
     - **`renderCompactPreview()`** L1228-1236 : supprimer :
       ```javascript
       const hCm = state._heightCm;
       if (hCm && hCm > 0) {
           const hM = hCm / 100;
           const bmi = lm.weight_kg / (hM * hM);
           tiles.push(["IMC", Math.round(bmi * 10) / 10]);
       } else if (lm.bmi != null) {
           tiles.push(["IMC", lm.bmi]);
       }
       ```
       Remplacer par :
       ```javascript
       if (lm.bmi?.value != null) tiles.push(["IMC", lm.bmi.value]);
       ```
     - Ajouter un indicateur visuel de source si `bmi.source === "computed_backend"` (ex: "(calculé)" en petit).
  5. Vérifier si `state._heightCm` est utilisé ailleurs que pour l'IMC. Il est utilisé dans `renderReglages()` L2142 (affichage du champ taille dans Réglages) et `savePrefs()`/`loadPrefs()`. Ces utilisations sont légitimes (UI uniquement). Garder `state._heightCm`.
- **Pattern à suivre** : Le `DedupPreview` / `DecisionPreview` déjà existants montrent comment structurer des sous-objets dans la réponse API.
- **Tests** :
  - `backend/tests/test_mapping.py` — ajouter `test_bmi_with_height()`, `test_bmi_without_height()`, `test_bmi_invalid_height()`, `test_bmi_withings_vs_computed()`, `test_bmi_rounding()`
  - `backend/tests/test_sync.py` — vérifier que `bmi_info` est présent dans le `MeasurementPreviewResponse`
- **Risques** : Le changement de structure de `bmi` (float → objet `{value, source, inputs}`) dans `latest_measurement` est un breaking change. Le frontend est le seul consommateur connu, donc acceptable. Vérifier qu'aucun autre code (CLI, scripts) ne lit ce champ.

### Étape 2 — Normaliser les périodes de synchronisation côté backend

- **Fichier(s)** : `backend/app/services/sync_engine.py`, `backend/app/api/routes_sync.py`, `backend/app/models/sync.py`, `frontend/out/assets/app.js`
- **Description** : Le frontend envoie `start_date`/`end_date`. Le backend doit valider, normaliser, et documenter la période réellement utilisée. Ajouter aussi un champ `period` (intention : `"1d"`, `"7d"`, `"30d"`) pour que le frontend n'ait pas à calculer les dates.
- **Changements précis** :
  1. Dans `SyncRequest` (`routes_sync.py` L40-45), ajouter :
     ```python
     period: str | None = None  # "1d", "7d", "30d", "custom"
     ```
  2. Dans `SyncEngine.run_sync()`, ajouter `_resolve_period()`:
     ```python
     def _resolve_period(self, start_date: str, end_date: str, period: str | None, tz) -> tuple[date, date]:
         from datetime import date as date_cls, timedelta
         today = datetime.now(tz).date()
         if period and period != "custom":
             days = {"1d": 1, "7d": 7, "30d": 30}.get(period)
             if days is None:
                 raise ValueError(f"Période inconnue: {period}. Valeurs acceptées: 1d, 7d, 30d")
             start_day = today - timedelta(days=days - 1)
             end_day = today
         else:
             start_day = self._parse_date(start_date)
             end_day = self._parse_date(end_date)
         if end_day < start_day:
             raise ValueError("La date de fin doit être postérieure ou égale à la date de début")
         if end_day > today + timedelta(days=1):
             raise ValueError("La date de fin ne peut pas être dans le futur")
         if (end_day - start_day).days > 365:
             raise ValueError("La période ne peut pas excéder 365 jours")
         return start_day, end_day
     ```
  3. Modifier `run_sync()` L73-77 pour appeler `_resolve_period()`.
  4. Dans `SyncReport.period` (construit L152), ajouter `resolved_start`, `resolved_end` :
     ```python
     "period": {
         "requested_start": start_date,
         "requested_end": end_date,
         "requested_period": body.period if hasattr(body, 'period') else None,
         "resolved_start": dt_start.isoformat(),
         "resolved_end": dt_end.isoformat(),
         "timezone": str(tz),
     }
     ```
  5. Dans `frontend/out/assets/app.js` `runSync()` L757-767 : ne plus calculer `startDate` à partir de `Date.now()`. Envoyer `period` au lieu de `start_date`/`end_date` quand c'est une période prédéfinie :
     ```javascript
     if (mode === "latest") {
         startDate = previewDate ? previewDate.slice(0, 10) : getLocalDate();
         endDate = startDate;
     } else if (mode === "period") {
         // Envoyer period au lieu de start_date/end_date calculés localement
         const days = state._periodDays || 1;
         const periodMap = { 1: "1d", 7: "7d", 30: "30d" };
         const period = periodMap[days] || "custom";
         body = { period };
     }
     ```
  6. Dans `renderSyncActions` (L712-717) et `renderCompactSyncPanel` (L1441-1449) : remplacer le calcul local de `pStart`/`periodSummary` par l'affichage de la période reçue du backend après sync.
- **Pattern à suivre** : `sync_engine.py` `_parse_date()` (L411-416) et `_local_day_window()` (L427-430) existants.
- **Tests** :
  - `backend/tests/test_sync.py` — `test_period_reversed()`, `test_period_future()`, `test_period_too_long()`, `test_period_7d()`, `test_period_timezone_europe_paris()`
- **Risques** : Rétrocompatibilité : `start_date`/`end_date` restent acceptés sans `period` (mode `custom`). Le frontend continue de les envoyer pour le mode `latest` (date unique).

### Étape 3 — Restructurer le flux OTP Garmin (backend + frontend)

- **Fichier(s)** : `backend/app/services/garmin_auth_service.py`, `backend/app/api/routes_garmin_auth.py`, `backend/app/models/auth.py`, `frontend/out/assets/app.js`
- **Description** : Implémenter un flux OTP en 2 étapes distinctes. Étape 1 : envoie email+password → si MFA requis, retourne `needs_otp` + `auth_session_id`. Étape 2 : envoie `auth_session_id` + `otp` → complète l'auth. Le frontend affiche un bloc OTP dédié uniquement quand `needs_otp` est reçu, avec un bouton "Valider le code OTP et connecter Garmin".
- **Changements précis** :
  1. Dans `models/auth.py`, modifier `GarminLoginRequest` :
     ```python
     class GarminLoginRequest(BaseModel):
         email: str | None = None
         password: str | None = None
         otp: str | None = None
         auth_session_id: str | None = None  # NOUVEAU
     ```
     Vérifier que `GarminAuthResult` a déjà `needs_otp: bool = False` et `auth_session_id: str | None = None` (sinon les ajouter).
  2. Dans `garmin_auth_service.py`, ajouter un gestionnaire de sessions in-memory :
     ```python
     import uuid, time, threading
     
     _sessions: dict[str, dict] = {}
     _sessions_lock = threading.Lock()
     _SESSION_TTL = 300  # 5 minutes
     
     def _create_session(self, email: str, password: str, process) -> str:
         sid = str(uuid.uuid4())
         with _sessions_lock:
             _sessions[sid] = {"email": email, "password": password, "process": process, "created": time.time()}
         return sid
     
     def _get_session(self, sid: str) -> dict | None:
         with _sessions_lock:
             s = _sessions.get(sid)
             if s and time.time() - s["created"] < _SESSION_TTL:
                 return s
             if s:
                 del _sessions[sid]
         return None
     
     def _cleanup_session(self, sid: str) -> None:
         with _sessions_lock:
             _sessions.pop(sid, None)
     ```
  3. Modifier `login()` et `_start_with_credentials()` dans `garmin_auth_service.py` :
     - `_start_with_credentials()` : quand MFA est détecté, créer une session au lieu de terminer le process, et retourner `auth_session_id`
     - `login()` : si `auth_session_id` est fourni, appeler une nouvelle méthode `_complete_session_with_otp(sid, otp)` qui récupère la session, écrit l'OTP dans le stdin du process existant, attend la fin, nettoie la session
     - Maintenir le comportement legacy (`email`+`password`+`otp` sans session) pour rétrocompatibilité
  4. Dans `routes_garmin_auth.py` `/login` : accepter `auth_session_id` + `otp` sans `email`/`password`.
  5. Dans `frontend/out/assets/app.js` `renderReglages()` (L2026-2066) :
     - **Supprimer** le champ OTP (`#g-otp`) du formulaire initial
     - **Ajouter** un bloc OTP conditionnel (`#g-otp-block`) masqué par défaut :
       ```html
       <div id="g-otp-block" style="display:none; margin-top:12px">
         <p style="color:var(--amber);font-size:13px">Garmin demande un code de vérification. Saisis le code reçu, puis valide la connexion.</p>
         <label>Code OTP Garmin<input id="g-otp" autocomplete="one-time-code" /></label>
         <button id="g-otp-btn">Valider le code OTP et connecter Garmin</button>
         <p id="g-otp-error" style="color:var(--red);font-size:12px;display:none"></p>
       </div>
       ```
     - Modifier le handler "Connecter Garmin" : envoyer email+password sans OTP, si `needs_otp` → afficher `#g-otp-block` et stocker `auth_session_id`
     - Ajouter handler "Valider le code OTP et connecter Garmin" : envoyer `auth_session_id`+`otp`, si succès → masquer bloc OTP, rafraîchir statut
     - Gérer les erreurs OTP (invalide, expiré) avec message clair
  6. **Ne pas modifier** `/api/garmin/auth/verify` — il reste une vérification d'état uniquement.
- **Pattern à suivre** : `_spawn_auth_reader()` existant (L162-193) lit déjà stdout/stderr du subprocess. La session permet de réutiliser ce même subprocess pour l'étape OTP.
- **Tests** :
  - `backend/tests/test_garmin_api.py` — `test_login_without_otp()`, `test_login_needs_otp_returns_session()`, `test_login_with_valid_otp_via_session()`, `test_login_with_invalid_otp()`, `test_login_with_expired_session()`, `test_verify_does_not_accept_otp()`
- **Risques** :
  - Le dict `_sessions` est en mémoire (pas de persistance). Acceptable car TTL = 5 min.
  - Thread safety : `threading.Lock()` utilisé. Suffisant pour un worker unique.
  - Si `garmin-mcp-auth` timeout entre l'étape 1 et l'étape 2, la session devient invalide. Le frontend doit gérer l'erreur "session expirée" et proposer de recommencer.

### Étape 4 — Améliorer les messages d'erreur Garmin

- **Fichier(s)** : `backend/app/services/garmin_auth_service.py`, `backend/app/models/auth.py`
- **Description** : Standardiser les messages d'erreur avec un champ `error_code` dans `GarminAuthResult`. Le frontend pourra afficher des messages adaptés sans interpréter le texte brut.
- **Changements précis** :
  1. Dans `models/auth.py`, ajouter à `GarminAuthResult` : `error_code: str | None = None`
     - Valeurs : `"invalid_credentials"`, `"otp_required"`, `"otp_invalid"`, `"otp_expired"`, `"timeout"`, `"garmin_unavailable"`, `"already_connected"`, `"disconnected"`, `"verify_failed"`
  2. Dans `garmin_auth_service.py`, mapper les erreurs :
     - `_start_with_credentials()` : détection MFA → `error_code="otp_required"`
     - `process.returncode != 0` → `error_code="invalid_credentials"`
     - `TimeoutExpired` → `error_code="timeout"`
     - `_complete_session_with_otp()` : OTP invalide → `error_code="otp_invalid"`
     - Session expirée → `error_code="otp_expired"`
- **Pattern à suivre** : `GarminAuthResult` existe déjà avec `ok`, `message`, `needs_otp`.
- **Tests** : `test_error_codes_mapped_correctly()`
- **Risques** : Les messages de `garmin-mcp-auth` peuvent varier — le mapping par `error_code` est plus robuste que le parsing.

### Étape 5 — Documenter l'architecture frontend/backend

- **Fichier(s)** : `docs/ARCHITECTURE_FRONTEND_BACKEND.md` (**NOUVEAU**), `docs/README_GUIDE.md`
- **Description** : Créer une documentation de la frontière de responsabilité, et mettre à jour le guide README.
- **Changements précis** :
  1. Créer `docs/ARCHITECTURE_FRONTEND_BACKEND.md` avec :
     - "Règle d'or" : backend = source de vérité, frontend = affichage uniquement
     - Tableau "Ce que le frontend PEUT faire" (affichage, UI, appels API, état local)
     - Tableau "Ce que le frontend NE DOIT PAS faire" (calculs métier, mapping, déduplication, décisions)
     - Tableau "Ce que le backend DOIT garder" (auth, parsing, mapping, déduplication, sync, rapports)
     - "Pourquoi les calculs métier côté frontend sont dangereux"
     - "Comment ajouter une nouvelle métrique proprement" (exemple IMC)
     - "Connexion Garmin avec OTP" : flux étape 1/2, différence `/login` vs `/verify`, erreurs fréquentes, données à ne pas logger
  2. Dans `docs/README_GUIDE.md`, ajouter une référence vers `docs/ARCHITECTURE_FRONTEND_BACKEND.md` dans la section appropriée.
- **Pattern à suivre** : `docs/mapping_withings_garmin.md` pour le style.
- **Tests** : Aucun.
- **Risques** : Aucun.

### Étape 6 — Vérification finale : audit post-correction

- **Fichier(s)** : `frontend/out/assets/app.js` (audit uniquement)
- **Description** : Vérifier qu'aucune logique métier ne subsiste dans le frontend.
- **Changements précis** :
  1. Grep pour `hM * hM`, `weight_kg / (hM`, `/(hM`, `bmi` dans `app.js` → doit être 0 occurrence de calcul
  2. Grep pour `Date.now() - (` ou `86400000` dans `app.js` → doit être 0 occurrence de calcul de période
  3. Vérifier que `email`/`password`/`otp` ne sont jamais dans `localStorage`
  4. Vérifier que `renderStatusBar()` ne bloque pas le rendu (les appels sont async via `refreshStatus()`)
- **Pattern à suivre** : N/A (vérification).
- **Tests** : Revue manuelle + grep.
- **Risques** : Si d'autres violations sont découvertes, les ajouter.

---

## Ordre d'exécution recommandé

1. **Étape 1 (IMC)** — Impact direct sur la séparation, pas de dépendances
2. **Étape 2 (Périodes)** — Peut être fait en parallèle de l'étape 1
3. **Étape 3 (OTP Garmin)** — Plus complexe, dépend de `auth.py`. Après étapes 1-2
4. **Étape 4 (Messages d'erreur)** — Dépend de l'étape 3, immédiatement après
5. **Étape 5 (Documentation)** — Indépendante, en parallèle
6. **Étape 6 (Vérification finale)** — Après tout

---

## Points d'attention

- **Rétrocompatibilité API** : Le changement de `bmi` (float → objet) dans `latest_measurement` et l'ajout de `period` dans `SyncRequest` sont des breaking changes. Le frontend est le seul consommateur connu → acceptable.
- **Session OTP in-memory** : Non partagé entre workers. OK car single-worker actuellement. Si multi-worker → migrer vers Redis ou SQLite.
- **`state._heightCm`** : Conservé dans le frontend pour l'affichage dans Réglages. Le backend lit `USER_HEIGHT_M` depuis `.env` pour les calculs. Pas de conflit.
- **Convention `app.` imports** : Tout nouveau code backend utilise `from app.xxx import YYY`, jamais `from backend.app.xxx`.
- **Settings frozen** : `Settings` est `frozen=True` — toujours `Settings(**overrides)` pour les tests.
- **`/api/status`** : Déjà optimal (caché 60s, `stale_while_revalidate`). Ne pas toucher.
- **Navigation frontend** : Déjà cohérente et propre. Ne pas modifier.

---

## Checklist de vérification post-implémentation

- [ ] `uv run ruff check backend` — pas d'erreurs
- [ ] `uv run pytest` — tous les tests passent
- [ ] Tests IMC : poids+taille valide, taille absente, invalide, arrondi, Withings vs calculé
- [ ] Tests période : inversée, future, trop longue, timezone
- [ ] Tests OTP : sans OTP, requis+session, OTP valide, invalide, session expirée, `/verify` ne soumet pas d'OTP
- [ ] Aucun calcul IMC résiduel dans `app.js` (vérifié par grep)
- [ ] Aucun calcul de période résiduel dans `app.js`
- [ ] Le flux OTP fonctionne en 2 étapes distinctes dans l'UI
- [ ] `/api/garmin/auth/verify` ne soumet jamais d'OTP
- [ ] Les secrets (password, OTP) n'apparaissent pas dans les logs
- [ ] `docs/ARCHITECTURE_FRONTEND_BACKEND.md` existe et est complet
