# Architecture Frontend / Backend — GarminSyncWeight

## Règle d'or

> **Le backend est la source unique de vérité. Le frontend est exclusivement une couche d'affichage.**

Tout calcul métier, toute validation, toute décision, tout appel à une API externe (Withings, Garmin) doit être **exclusivement** dans le backend. Le frontend ne fait que présenter les données que le backend lui fournit.

---

## Ce que le frontend PEUT faire

| Catégorie | Exemples |
|---|---|
| **Affichage** | Rendu HTML, mise en forme des dates, couleurs, badges |
| **UI / UX** | Navigation, onglets, modales, animations CSS, responsive |
| **Appels API** | `fetch()` vers `/api/*` (uniquement les routes exposées par le backend) |
| **État local** | Stockage temporaire des préférences d'affichage (onglet actif, période sélectionnée) |
| **Formatage** | `toLocaleDateString()`, `Math.round()`, concaténation de chaînes pour l'affichage |
| **Cache UI** | Mémorisation du dernier état pour éviter un flash lors d'un re-render |

## Ce que le frontend NE DOIT PAS faire

| Catégorie | Exemple de violation | Pourquoi c'est dangereux |
|---|---|---|
| **Calculs métier** | `bmi = weight / (height * height)` | Double calcul incohérent entre frontend et backend. Si la formule change, il faut modifier 2 endroits. |
| **Validation métier** | `if (startDate > endDate) reject()` | Le backend doit être le gardien. Le frontend peut faire de la validation UX (ex. champ non vide) mais jamais de la validation métier. |
| **Décisions de sync** | `if (weightDiff < 0.05) skip()` | La déduplication est une règle métier critique. Seul le backend a accès à l'historique complet. |
| **Mapping de données** | Convertir kg → lbs, calculer l'hydratation en % | Le mapping est la responsabilité du `mapper.py`. |
| **Appels directs à Garmin/Withings** | `fetch("https://apis.garmin.com/...")` | Violation de sécurité : expose les tokens. Jamais d'appel externe depuis le frontend. |
| **Calcul de périodes** | `new Date(Date.now() - days * 86400000)` | La période effective doit être validée par le backend (fuseau horaire, date future, plage max). |
| **Stockage de secrets** | `localStorage.setItem("garmin_password", ...)` | Extrêmement dangereux. Les secrets ne doivent jamais toucher le frontend. |

## Ce que le backend DOIT garder

| Responsabilité | Composant |
|---|---|
| Authentification Withings (OAuth2) | `withings_auth.py` |
| Authentification Garmin (garmin-mcp-auth) | `garmin_auth_service.py` |
| Parsing des mesures Withings | `withings_parser.py` |
| Mapping Withings → Garmin | `mapper.py` |
| Déduplication | `deduplicator.py` |
| Écriture Garmin | `garmin_client.py` |
| Orchestration de la sync | `sync_engine.py` |
| Génération de rapports | `report_builder.py` |
| Validation des périodes | `sync_engine._resolve_period()` |
| Calcul de l'IMC | `mapper.py` + `withings_parser.py` |
| Cache des statuts | `cache.py` (TTL 60s, stale-while-revalidate) |
| Streaming SSE | `routes_sync.py` |

---

## Pourquoi les calculs métier côté frontend sont dangereux

1. **Incohérence** : si la formule change, il faut modifier 2 endroits. Un oubli = données différentes affichées vs synchronisées.
2. **Sécurité** : un utilisateur peut modifier `app.js` dans son navigateur et contourner la validation.
3. **Maintenabilité** : quand tout le métier est dans `backend/app/`, un nouveau développeur sait exactement où chercher.
4. **Testabilité** : les tests backend (`pytest`) couvrent le métier. Les tests frontend sont quasi inexistants dans ce projet.

---

## Comment ajouter une nouvelle métrique proprement

Exemple : on veut afficher l'IMC dans le frontend.

1. **Backend** : le calcul est déjà fait dans `mapper.py` (L98-113).
2. **API** : exposer la valeur dans la réponse (ex. `bmi: { value: 25.6, source: "computed_backend" }`).
3. **Frontend** : lire `preview.latest_measurement.bmi.value` — **ne jamais recalculer**.

```
❌ Frontend: const bmi = weight / (height * height)
✅ Frontend: <span>{preview.latest_measurement.bmi.value}</span>
```

---

## Connexion Garmin avec OTP (flux en 2 étapes)

### Étape 1 : Envoi email + mot de passe

```
POST /api/garmin/auth/login
{
  "email": "...",
  "password": "..."
}
```

Réponse si MFA requis :
```json
{
  "ok": false,
  "needs_otp": true,
  "auth_session_id": "uuid-...",
  "error_code": "otp_required",
  "message": "Code MFA Garmin requis."
}
```

### Étape 2 : Validation OTP via session

```
POST /api/garmin/auth/login
{
  "auth_session_id": "uuid-...",
  "otp": "123456"
}
```

Réponse si succès :
```json
{
  "ok": true,
  "message": "Authentification Garmin réussie."
}
```

### Différence `/login` vs `/verify`

- **`POST /login`** : démarre ou complète l'authentification. Accepte `email`+`password` (étape 1) ou `auth_session_id`+`otp` (étape 2).
- **`POST /verify`** : vérifie uniquement si un token valide existe. Ne soumet jamais d'OTP, ne démarre jamais d'authentification.

### Erreurs fréquentes

| `error_code` | Cause | Action |
|---|---|---|
| `otp_required` | MFA activé sur le compte Garmin | Afficher le champ OTP |
| `otp_invalid` | Code OTP incorrect | Demander de ressaisir |
| `otp_expired` | Session de 5 minutes expirée | Recommencer depuis l'étape 1 |
| `timeout` | `garmin-mcp-auth` n'a pas répondu | Réessayer |
| `invalid_credentials` | Email ou mot de passe incorrect | Corriger les identifiants |

### Données à ne pas logger

- Le mot de passe Garmin est passé via variable d'environnement au subprocess, jamais écrit dans un fichier.
- L'OTP est écrit dans le stdin du subprocess, jamais persisté.
- `RedactingJsonFormatter` nettoie automatiquement les logs.

---

## Flux de données complet

```
Withings API ──→ withings_client ──→ withings_parser ──→ mapper ──→ deduplicator ──→ garmin_client ──→ Garmin API
                                          │                    │              │
                                          ▼                    ▼              ▼
                                   measurement_store    sync_candidates  sync_decisions
                                          │
                                          ▼
                                   routes_measurements ──→ frontend (affichage seul)
```

Le frontend ne voit jamais les appels à Withings ou Garmin. Il ne reçoit que des données déjà parsées, mappées et validées par le backend.
