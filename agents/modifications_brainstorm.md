# Modifications Brainstorm — 2026-06-28

## Résumé

Deux modifications : (1) ajout d'un bouton "Sync Withings" sur la page Historique pour forcer le rafraîchissement des données depuis Withings, avec rafraîchissement automatique si la dernière sync date de plus de 2 jours — toute la logique de décision (quand rafraîchir, vérifier la fraîcheur) est dans le backend, le frontend ne fait qu'appeler des endpoints et afficher ; (2) déplacement de la version `v0.3.1` dans la barre de navigation pour qu'elle s'affiche à droite du titre "GarminSyncWeight — Sync locale et contrôlée", alignée verticalement.

---

## Demande originale

```
## je viens de remarquer que je n'ai pas de bouton pour faire une synchronisation avec withings (obtenir les nouvelles données depuis Withings): 
- je veux ajouter un bouton qui permet de synchroniser les données depuis winthings :
    - idéalement ajouter ce bouton sur la page /historique tout en bas juste avant le bouton "Vérifier les statuts Garmin" et sur la meme ligne,
- ajouter une synchronisation automatique avec withings (pour obtenir les nouvelles données) si pas de synchronisation faite depuis > 2jours; 

## Concernant le titre dans la barre tout en haut : 
- il y a actuellement écrit : "GS
GarminSyncWeight
Sync locale et contrôlée
v0.3.0",
- est-ce qu'il est possible de déplacer la version juste à droite de "GarminSyncWeight
Sync locale et contrôlée" et biensur tout doit rester centré verticalement comme c'est actuellement; 
```

---

## Fichiers concernés

| Fichier | Rôle dans les modifications |
|---|---|
| `frontend/out/index.html` | Structure HTML du header : déplacer `<small class="version">` hors du `<span>` englobant |
| `frontend/out/assets/styles.css` | CSS : adapter le style de `.version` en tant que flex child de `.brand` |
| `frontend/out/assets/app.js` | JS : ajouter le bouton "Sync Withings" dans `renderHistorique()`, supprimer l'auto-sync du `boot()` (délégué au backend) |
| `backend/app/api/routes_measurements.py` | Backend : rendre `_fetch_withings_measurements` intelligent — décide automatiquement de rafraîchir si données > 2j, + paramètre `force_refresh` pour le bouton manuel |
| `backend/app/storage/sync_store.py` | Backend : exposer `last_sync_time()` pour la décision de staleness (déjà existant, pas de modification nécessaire) |
| `backend/tests/test_measurement_store.py` | Tests : couvrir le nouveau comportement `force_refresh` et l'auto-refresh sur staleness |

---

## Étapes d'implémentation

### Étape 1 — Déplacer la version dans le header

- **Fichier(s)** : `frontend/out/index.html`, `frontend/out/assets/styles.css`
- **Description** : Sortir `<small class="version">v0.3.1</small>` du `<span>` qui contient le titre pour en faire un enfant direct de `<a class="brand">`. La version sera ainsi un flex child au même niveau que `.brand-mark` et le `<span>` du titre, et sera automatiquement placée à droite et centrée verticalement grâce au `display: flex; align-items: center` déjà présent sur `.brand`.
- **Changements précis** :
  - Dans `index.html` : le bloc actuel (lignes 14-20) :
    ```html
    <a class="brand" href="/" data-route="dashboard">
      <span class="brand-mark">GS</span>
      <span>
        <strong>GarminSyncWeight</strong>
        <small>Sync locale et contrôlée</small>
        <small class="version">v0.3.1</small>
      </span>
    </a>
    ```
    devient :
    ```html
    <a class="brand" href="/" data-route="dashboard">
      <span class="brand-mark">GS</span>
      <span>
        <strong>GarminSyncWeight</strong>
        <small>Sync locale et contrôlée</small>
      </span>
      <small class="version">v0.3.1</small>
    </a>
    ```
  - Dans `styles.css` ligne 64 : remplacer `.brand .version { font-size: 0.65em; color: var(--dim); margin-top: 0; }` par `.brand > .version { font-size: 0.8em; color: var(--muted); white-space: nowrap; }` — le sélecteur `>` cible uniquement le flex child direct. La version sera automatiquement centrée verticalement (`.brand` a `align-items: center`) et suivra le flux horizontal après le `<span>` du titre.
- **Pattern à suivre** : La classe `.brand` est déjà `display: flex; gap: 12px; align-items: center`. Tout enfant direct est automatiquement centré verticalement.
- **Tests** : Vérification manuelle — ouvrir le dashboard, vérifier que le header affiche `GS | GarminSyncWeight — Sync locale et contrôlée | v0.3.1` sur une ligne, centré verticalement.
- **Risques** :
  - Responsive `<860px` : `.header` passe en `flex-direction: column`, mais `.brand` reste en `flex-direction: row` (par défaut). La version restera à droite du titre.
  - AMBIGUITY : La demande mentionne "v0.3.0" mais le fichier contient "v0.3.1". Je conserve la valeur réelle.

---

### Étape 2 — Rendre le fetch Withings intelligent côté backend (staleness + force_refresh)

- **Fichier(s)** : `backend/app/api/routes_measurements.py`
- **Description** : Modifier `_fetch_withings_measurements` pour qu'elle décide **automatiquement** de rafraîchir depuis l'API Withings si la dernière synchronisation date de plus de 2 jours. Ajouter également le paramètre `force_refresh` pour le bouton manuel. **Toute la logique de décision reste dans le backend.**
- **Changements précis** :
  - Ajouter l'import : `from app.storage.sync_store import SyncStore`
  - Modifier la signature de `_fetch_withings_measurements` (ligne 162) :
    ```python
    async def _fetch_withings_measurements(
        wclient: WithingsClient,
        parser: WithingsParser,
        store: WithingsMeasurementStore,
        start_dt: datetime,
        end_dt: datetime,
        force_refresh: bool = False,
        settings: Settings | None = None,
    ) -> tuple[list[BodyCompositionMeasurement], int]:
        start_date = start_dt.date()
        end_date = end_dt.date()

        # ── Décision backend : faut-il rafraîchir depuis l'API ? ──
        should_use_api = force_refresh
        if not should_use_api and settings:
            sync_store = SyncStore(settings.resolved_data_dir)
            last_sync = sync_store.last_sync_time()
            if last_sync:
                try:
                    last_sync_dt = datetime.fromisoformat(last_sync)
                    stale_seconds = (datetime.now(UTC) - last_sync_dt).total_seconds()
                    if stale_seconds > 2 * 86400:  # > 2 jours
                        should_use_api = True
                except (ValueError, TypeError):
                    pass
            else:
                # Jamais synchronisé → forcer le fetch
                should_use_api = True

        # ── Store-first si données fraîches ──
        if not should_use_api and start_date <= end_date:
            parsed = store.get_measurements(start_date.isoformat(), end_date.isoformat())
            if parsed:
                return parsed, len(parsed)

        # ── Live API ──
        raw = await wclient.get_measurements(start_dt, end_dt)
        parsed = parser.parse_measure_groups(raw)
        if parsed:
            store.save_measurements(parsed)
        return parsed, len(raw)
    ```
  - Dans `_compute_latest_preview` (ligne 190), passer `settings=settings` à l'appel de `_fetch_withings_measurements`
  - Dans `get_latest_measurement_preview` (ligne 364), ajouter `force_refresh: bool = Query(default=False)` et le transmettre. Si `force_refresh`, invalider le cache avant : `get_cache().invalidate(f"latest:{days}")`
  - Dans `get_measurement_history` (ligne 431), ajouter `force_refresh: bool = Query(default=False)` et le transmettre
  - Dans `get_recent_measurements` (ligne 386), idem
- **Pattern à suivre** : `last_sync_time()` est déjà utilisé dans `routes_status.py` (ligne 41). La vérification de staleness suit le même principe.
- **Tests** :
  - `backend/tests/test_measurement_store.py` — ajouter un test : avec `last_sync` récent, le store est utilisé ; avec `last_sync` > 2j, l'API est appelée
  - `backend/tests/test_measurement_store.py` — test `force_refresh=true` contourne toujours le store
  - Utiliser les fixtures existantes : `settings` (conftest) et `sync_store` (conftest)
- **Risques** :
  - `SyncStore` utilise `withings_tokens.db` — s'assurer que le `data_dir` de test pointe vers un fichier temporaire (c'est déjà le cas via `conftest.py`)
  - L'appel à `sync_store.last_sync_time()` nécessite que la table `sync_jobs` existe — `init_db` est appelé par `SyncStore.__init__`, donc OK
  - Ne pas casser l'existant : `force_refresh` est optionnel (default `False`), le comportement par défaut sans le paramètre reste inchangé SAUF l'auto-refresh sur staleness, qui est le comportement désiré

---

### Étape 3 — Ajouter le bouton "Sync Withings" sur la page Historique

- **Fichier(s)** : `frontend/out/assets/app.js`
- **Description** : Dans `renderHistorique()`, ajouter un bouton "Sync Withings" dans la `actionRow` juste avant "Vérifier les statuts Garmin". Ce bouton appelle l'endpoint backend avec `force_refresh=true` — **le frontend ne fait que déclencher, le backend gère la logique**.
- **Changements précis** :
  - Dans `renderHistorique()`, dans le bloc `actionRow` (ligne 1807), ajouter AVANT le `refreshBtn` :
    ```javascript
    const withingsBtn = btn("Sync Withings", async () => {
      if (withingsBtn.disabled) return;
      withingsBtn.disabled = true;
      withingsBtn.textContent = "Sync en cours…";
      try {
        // Le backend gère la logique : force_refresh=true → appel live à l'API Withings
        const res = await api("/api/measurements/history?days=30&include_garmin_status=true&force_refresh=true");
        state._historyItems = res.items || [];
        state._historySummary = res.summary || null;
        state._historyFetchedAt = Date.now();
        showToast("Sync Withings", "Données Withings actualisées.", "success");
      } catch (err) {
        showToast("Erreur", err.message, "error");
      } finally {
        withingsBtn.disabled = false;
        withingsBtn.textContent = "Sync Withings";
      }
      render();
    }, "secondary");
    actionRow.append(withingsBtn);
    ```
  - Placer `actionRow.append(withingsBtn)` avant `actionRow.append(refreshBtn)` (ligne 1816)
- **Pattern à suivre** : Même structure que le bouton "Vérifier les statuts Garmin" (lignes 1810-1816). Le frontend est purement un déclencheur + affichage.
- **Tests** : Vérification manuelle — le bouton apparaît avant "Vérifier les statuts Garmin", le clic déclenche un appel API et un toast, le bouton est désactivé pendant la requête.
- **Risques** : Aucun. Le `force_refresh=true` est géré intégralement par le backend (Étape 2).

---

### Étape 4 — Rafraîchissement automatique au chargement (backend-driven)

- **Fichier(s)** : `frontend/out/assets/app.js`
- **Description** : Le frontend appelle `loadHistory()` au boot **sans aucune condition**. Le backend (via l'Étape 2) décide automatiquement si les données sont fraîches (cache) ou périmées (appel live à l'API Withings). **Zéro logique de décision dans le frontend.**
- **Changements précis** :
  - Dans `boot()` (ligne 2526), après `setRoute(initialRoute, false)`, AJOUTER :
    ```javascript
    // Le backend décide automatiquement si les données Withings sont fraîches
    // ou si un rafraîchissement depuis l'API est nécessaire (> 2 jours sans sync).
    // Le frontend ne fait qu'appeler l'endpoint — aucune logique de décision ici.
    if (state.withings?.connected && state.garmin?.token_valid) {
      loadHistory().catch(() => {});
    }
    ```
  - **NE PAS** ajouter de vérification `Date.now() - lastSync`, **NE PAS** ajouter de `setTimeout` ou de `loadDashboardData()` conditionnel. Le `loadDashboardData()` appelé juste après (ligne 2537-2539) gère déjà le dashboard.
- **Pattern à suivre** : L'appel à `loadHistory()` au boot est identique à ce que fait déjà le dashboard quand l'utilisateur navigue vers `/historique` (ligne 1694). La seule différence est qu'il est systématique au boot (uniquement si services connectés).
- **Tests** :
  - Le backend (testé séparément à l'Étape 2) garantit que si `last_sync` > 2j, les données sont rafraîchies depuis l'API Withings
  - Le backend garantit que si `last_sync` < 2j, les données du store sont retournées (pas d'appel API inutile)
  - Vérification manuelle : ouvrir l'app, vérifier que l'historique se charge (depuis le cache ou l'API, selon la fraîcheur)
- **Risques** :
  - Appeler `loadHistory()` à chaque boot peut sembler redondant, mais le backend protège contre les appels API inutiles (store-first si données fraîches)
  - Si Withings ou Garmin n'est pas connecté, `loadHistory()` échouera → `catch(() => {})` le gère silencieusement

---

## Ordre d'exécution recommandé

1. **Étape 2** — Rendre le backend intelligent (staleness + force_refresh). Prérequis pour les étapes 3 et 4.
2. **Étape 3** — Ajouter le bouton "Sync Withings" dans l'UI. Dépend de l'étape 2 (a besoin de `force_refresh`).
3. **Étape 4** — Appeler `loadHistory()` au boot. Dépend de l'étape 2 (a besoin du comportement auto-refresh backend).
4. **Étape 1** — Déplacer la version dans le header. Indépendant, peut être fait en parallèle.

---

## Points d'attention

- **Principe backend-driven** : La règle est stricte — le frontend ne contient **aucune** vérification de timestamp, aucun `if (days > 2)`, aucune décision de "dois-je rafraîchir ou pas". Tout est dans `_fetch_withings_measurements`.
- **Seuil des 2 jours** : Hardcodé côté backend (`2 * 86400`). Si le seuil doit devenir configurable, ajouter une variable d'environnement (ex. `WITHINGS_STALE_SECONDS`). Pas nécessaire pour cette itération.
- **Cache invalidation** : `_compute_latest_preview` utilise `stale_while_revalidate`. Quand `force_refresh=true`, il faut invalider explicitement le cache `latest:{days}`. Sans cela, le cache peut servir des données périmées.
- **Différence boutons** : "Sync Withings" = `force_refresh=true` → appel live à l'API Withings. "Vérifier les statuts Garmin" = appel normal → store-first, vérifie juste les statuts Garmin des mesures existantes. "Rafraîchir les mesures" = recharge `/api/measurements/recent`.
- **Responsive header** : À `<860px`, le header passe en `flex-direction: column`, mais `.brand` reste en `flex-direction: row`. La version reste à droite du titre. Vérifier visuellement.
- **Version hardcodée** : `v0.3.1` est hardcodée dans `index.html`. Pas de régression.
- **Pas d'écriture Garmin** : Ce plan est 100% read-only côté Garmin. Aucune modification des appels `add_body_composition`.

---

## Checklist de vérification post-implémentation

- [ ] `uv run ruff check backend` — pas d'erreurs
- [ ] `uv run pytest` — tous les tests passent
- [ ] `uv run pytest -k "force_refresh"` — les nouveaux tests de staleness/force_refresh passent
- [ ] Vérification manuelle : header affiche `GS | GarminSyncWeight — Sync locale et contrôlée | v0.3.1` centré verticalement
- [ ] Vérification manuelle : bouton "Sync Withings" présent sur `/historique`, avant "Vérifier les statuts Garmin"
- [ ] Vérification manuelle : clic sur "Sync Withings" → appel API Withings → toast "Données Withings actualisées"
- [ ] Vérification manuelle : au boot, si `last_sync` > 2j → les données Withings sont rafraîchies automatiquement (vérifiable dans les logs backend)
- [ ] Vérification manuelle : au boot, si `last_sync` < 2j → les données viennent du cache (pas d'appel API Withings inutile)
- [ ] Pas de régression sur le dashboard, l'historique, les réglages
