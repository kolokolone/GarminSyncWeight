# Cache & Performance Migration — Plan de Suivi Détaillé

> Refonte complète de la couche SQLite de GarminSyncWeight.
>
> **Objectif opérationnel** : Rendre l'application plus rapide et plus autonome en
> réduisant au maximum les appels API vers Withings et Garmin, sans sacrifier la
> fiabilité de la synchronisation ni l'auditabilité.
>
> **Métrique cible** : ≥ 90% des appels API Dashboard servis depuis le cache local
> après la première synchronisation.

---

## Table des matières

1. [Contexte et diagnostic](#1-contexte-et-diagnostic)
2. [Architecture cible](#2-architecture-cible)
3. [Décomposition par phase](#3-décomposition-par-phase)
   - [Phase 1 — Cache Garmin persistant](#phase-1--cache-garmin-persistant)
   - [Phase 2 — Stockage mesures Withings](#phase-2--stockage-mesures-withings)
   - [Phase 3 — Normalisation jobs / candidats / décisions](#phase-3--normalisation-jobs--candidats--décisions)
   - [Phase 4 — Optimisation API et UI](#phase-4--optimisation-api-et-ui)
4. [Dépendances entre phases](#4-dépendances-entre-phases)
5. [Stratégie de migration et rollback](#5-stratégie-de-migration-et-rollback)
6. [Glossaire](#6-glossaire)

---

## 1. Contexte et diagnostic

### 1.1 État des lieux

```
Base actuelle : data/withings_tokens.db
Tables         : withings_tokens, withings_oauth_states, sync_events, sync_attempts
Données réelles: 1 token, 14 sync_events, 21 sync_attempts
Index          : Aucun index métier (sauf PK auto et UNIQUE sur idempotency_key)
Cache existant : TTLCache mémoire 30s (cache.py) — uniquement pour /latest
```

### 1.2 Goulots d'étranglement identifiés

| Goulot | Appels par sync | Coût | Solution |
|---|---|---|---|
| `get_daily_weigh_ins()` appelé 1×/jour de fenêtre | ~9-13 appels | ~3-5 secondes | Cache SQLite TTL 1h (Phase 1) |
| `get_body_composition()` appelé 1× par fenêtre | 1 appel | ~1-2 secondes | Cache SQLite TTL 1h (Phase 1) |
| Dashboard `/latest` → appelle Withings API | 1 appel | ~1-2 secondes | Store mesures Withings (Phase 2) |
| Dashboard `/recent` → appelle Withings API | 1 appel | ~1-2 secondes | Store mesures Withings (Phase 2) |
| Dashboard `/history` → appelle Withings + Garmin | 30+ appels | ~5-10 secondes | Store + Cache (Phases 1+2) |
| `/api/status` → appelle les 2 APIs | 2 appels | ~2-4 secondes | Cache court 60s (Phase 4) |

**Ratio estimé aujourd'hui** : ~200 appels API pour ~14 mesures utiles (50% skipped_existing).

### 1.3 Principes directeurs

1. **Pas de cache sans invalidation** — toute donnée écrite dans Garmin invalide le cache associé
2. **Store-first, API-fallback** — les endpoints lecture tentent le cache local d'abord
3. **Idempotence** — INSERT OR IGNORE partout, pas de doublons
4. **Migration sûre** — CREATE TABLE IF NOT EXISTS, pas de renommage ni suppression de colonnes
5. **Compatible ascendant** — anciennes tables conservées jusqu'à la Phase 3

---

## 2. Architecture cible

### 2.1 Diagramme de flux

```
┌──────────────────────────────────────────────────────────────────────┐
│                           ROUTES API                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐   │
│  │ /latest      │  │ /recent      │  │ /history                 │   │
│  │ /latest?d=30 │  │ /recent?d=30 │  │ /history?d=30            │   │
│  └──────┬───────┘  └──────┬───────┘  └───────────┬──────────────┘   │
│         │                 │                       │                  │
│  ┌──────▼─────────────────▼───────────────────────▼──────────────┐  │
│  │             _fetch_withings_measurements()                     │  │
│  │  ┌──────────────────┐    ┌──────────────────────────────┐     │  │
│  │  │ SQLite Store HIT │    │ SQLite Store MISS → API call │     │  │
│  │  │ (0 API calls)    │    │ (1 API call + save to store) │     │  │
│  │  └──────────────────┘    └──────────────────────────────┘     │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                    SYNC ENGINE                                │  │
│  │                                                               │  │
│  │  Withings Client ──▶ Parser ──▶ [STORE] ──▶ Mapper ──▶ Dedup │  │
│  │                                        ↓ save                 │  │
│  │                                   withings_measurements       │  │
│  │                                                               │  │
│  │  Garmin Client ──▶ [CACHE] ──▶ get_daily_weigh_ins()         │  │
│  │                    [CACHE] ──▶ get_body_composition()        │  │
│  │                    [INVAL] ◀── add_body_composition()        │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                    SQLITE (withings_tokens.db)                │  │
│  │                                                               │  │
│  │  ┌────────────────────┐  ┌──────────────────────────┐        │  │
│  │  │ garmin_measurements│  │ withings_measurements     │        │  │
│  │  │ _cache             │  │                           │        │  │
│  │  ├────────────────────┤  ├──────────────────────────┤        │  │
│  │  │ weigh_in / date    │  │ source_measure_group_id  │        │  │
│  │  │ body_comp / date   │  │ date / measured_at_utc   │        │  │
│  │  │ TTL 1h             │  │ INSERT OR IGNORE         │        │  │
│  │  │ INVAL post-write   │  │ Pas de TTL (refresh sync)│        │  │
│  │  └────────────────────┘  └──────────────────────────┘        │  │
│  │  ┌────────────────────────────────────────────────────────┐  │  │
│  │  │ sync_events / sync_attempts / withings_tokens /        │  │  │
│  │  │ withings_oauth_states (existants, inchangés)           │  │  │
│  │  └────────────────────────────────────────────────────────┘  │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌──────────────────────┐                                          │
│  │ TTLCache mémoire     │  ← cache de bord 30s (inchangé)         │
│  │ (cache.py existant)  │    double tampon avec le cache SQLite   │
│  └──────────────────────┘                                          │
└──────────────────────────────────────────────────────────────────────┘
```

### 2.2 DDL complet des nouvelles tables

```sql
-- Table 1 : Cache des réponses API Garmin
-- Créée en Phase 1. Chaque ligne = une date × un type (weigh_in / body_composition).
-- data_json = JSON array de dicts (model_dump mode="json").
-- cache_expires_at = datetime UTC où l'entrée est considérée expirée.
CREATE TABLE IF NOT EXISTS garmin_measurements_cache (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    date             TEXT    NOT NULL,           -- YYYY-MM-DD
    source_type      TEXT    NOT NULL,           -- 'weigh_in' | 'body_composition'
    data_json        TEXT    NOT NULL,           -- JSON array of parsed model dicts
    fetched_at       TEXT    NOT NULL DEFAULT (datetime('now')),
    cache_expires_at TEXT    NOT NULL,           -- expiration datetime (TTL 1h)
    created_at       TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at       TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE(date, source_type)                    -- une ligne par (date, type)
);

-- Table 2 : Mesures Withings parsées
-- Créée en Phase 2. Chaque ligne = une mesure BodyCompositionMeasurement.
-- Les valeurs Decimal sont stockées en TEXT pour préserver la précision.
-- source_measure_group_id = grpid Withings (UNIQUE → INSERT OR IGNORE).
CREATE TABLE IF NOT EXISTS withings_measurements (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    source_measure_group_id TEXT    UNIQUE NOT NULL,
    source_device_id        TEXT,
    date                    TEXT    NOT NULL,     -- garmin_date YYYY-MM-DD
    measured_at_utc         TEXT    NOT NULL,     -- ISO datetime
    measured_at_local       TEXT    NOT NULL,     -- ISO datetime
    weight_kg               TEXT,                 -- Decimal en TEXT
    fat_percent             TEXT,
    fat_mass_kg             TEXT,
    fat_free_mass_kg        TEXT,
    muscle_mass_kg          TEXT,
    bone_mass_kg            TEXT,
    hydration_mass_kg       TEXT,
    hydration_percent       TEXT,
    bmi                     TEXT,
    visceral_fat_mass       TEXT,
    basal_met               TEXT,
    active_met              TEXT,
    metabolic_age           INTEGER,
    visceral_fat_rating     INTEGER,
    physique_rating         INTEGER,
    raw_json                TEXT,                 -- JSON du measure group brut
    fetched_at              TEXT    NOT NULL DEFAULT (datetime('now')),
    created_at              TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at              TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_withings_meas_date ON withings_measurements(date);
CREATE INDEX IF NOT EXISTS idx_withings_meas_utc  ON withings_measurements(measured_at_utc);

-- Table 3 : Jobs de synchronisation (Phase 3)
-- Remplace sync_attempts. Trace chaque run de sync.
-- Permet de suivre : qui a lancé, combien de temps, quel résultat.
CREATE TABLE IF NOT EXISTS sync_jobs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          TEXT    UNIQUE NOT NULL,       -- UUID v4 généré par le moteur
    started_at      TEXT    NOT NULL,
    completed_at    TEXT,
    start_date      TEXT    NOT NULL,              -- YYYY-MM-DD
    end_date        TEXT    NOT NULL,              -- YYYY-MM-DD
    tz_name         TEXT,                          -- fuseau horaire utilisé
    trigger         TEXT    NOT NULL DEFAULT 'manual', -- 'manual' | 'scheduled' | 'webhook'
    status          TEXT    NOT NULL,              -- 'running' | 'completed' | 'failed'
    candidates_total    INTEGER DEFAULT 0,
    candidates_synced   INTEGER DEFAULT 0,
    candidates_skipped  INTEGER DEFAULT 0,
    candidates_conflict INTEGER DEFAULT 0,
    candidates_invalid  INTEGER DEFAULT 0,
    candidates_failed   INTEGER DEFAULT 0,
    duration_seconds    REAL,
    error_message   TEXT,
    report_json     TEXT,                          -- SyncReport complet
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_sync_jobs_dates ON sync_jobs(start_date, end_date);
CREATE INDEX IF NOT EXISTS idx_sync_jobs_status ON sync_jobs(status);

-- Table 4 : Candidats de synchronisation (Phase 3)
-- Remplace sync_events. Chaque ligne = un GarminBodyCompositionCandidate traité.
-- Permet de tracer l'état exact de chaque mesure à travers le pipeline.
CREATE TABLE IF NOT EXISTS sync_candidates (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id                  INTEGER NOT NULL REFERENCES sync_jobs(id),
    idempotency_key         TEXT    UNIQUE NOT NULL,
    source                  TEXT    NOT NULL DEFAULT 'withings',
    source_measure_group_id TEXT,
    source_device_id        TEXT,
    date                    TEXT    NOT NULL,       -- YYYY-MM-DD (candidate.date)
    measured_at_local       TEXT,                   -- ISO datetime
    weight_kg               TEXT,
    fat_percent             TEXT,
    muscle_mass_kg          TEXT,
    bone_mass_kg            TEXT,
    hydration_percent       TEXT,
    bmi                     TEXT,
    mapped_fields_json      TEXT,                   -- JSON: { "weight": 78.5, ... }
    ignored_fields_json     TEXT,                   -- JSON: { "hydration_mass_kg": ... }
    null_fields_json        TEXT,                   -- JSON: ["visceral_fat", ...]
    mapping_warnings_json   TEXT,                   -- JSON: [...]
    dedup_status            TEXT,                   -- 'new_candidate' | 'duplicate_exact_or_near' | ...
    decision                TEXT,                   -- 'synced' | 'skipped_existing' | 'skipped_conflict' | 'invalid' | 'failed'
    reason                  TEXT,
    garmin_write_method     TEXT,                   -- 'add_body_composition' | 'add_weigh_in' | ...
    garmin_params_json      TEXT,                   -- les params envoyés à Garmin
    garmin_response_json    TEXT,                   -- réponse brute de Garmin
    error_message           TEXT,
    created_at              TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_sync_candidates_job  ON sync_candidates(job_id);
CREATE INDEX IF NOT EXISTS idx_sync_candidates_date ON sync_candidates(date);
CREATE INDEX IF NOT EXISTS idx_sync_candidates_key  ON sync_candidates(idempotency_key);

-- Table 5 : Décisions détaillées (Phase 3)
-- Permet d'expliquer POURQUOI une décision a été prise.
-- Séparée de sync_candidates pour permettre des décisions multiples
-- (ex: re-sync avec des paramètres différents).
CREATE TABLE IF NOT EXISTS sync_decisions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id    INTEGER NOT NULL REFERENCES sync_candidates(id),
    decision        TEXT    NOT NULL,              -- 'synced' | 'skipped_existing' | ...
    reason          TEXT    NOT NULL,              -- explication lisible
    weight_epsilon  REAL,                          -- seuil utilisé pour le dédoublonnage
    existing_weight REAL,                          -- poids Garmin existant (si pertinent)
    existing_date   TEXT,                          -- date Garmin existante
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_sync_decisions_candidate ON sync_decisions(candidate_id);

-- Table 6 : Migration tracking (Phase 3)
-- Enregistre chaque migration appliquée pour pouvoir les rejouer proprement.
CREATE TABLE IF NOT EXISTS schema_migrations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    version     TEXT    NOT NULL UNIQUE,           -- '001', '002', ...
    description TEXT,
    applied_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    checksum    TEXT                               -- hash du fichier de migration
);
```

### 2.3 Flux de bout en bout par scénario utilisateur

#### Scénario A : Dashboard chargé après une sync

```
AVANT Phase 2 :
  1. Ouvrir Dashboard → GET /api/measurements/latest?days=30
  2. Vérifier TTL cache mémoire (30s) → MISS
  3. Appeler Withings API : GET /measure?meastype=1&lastupdate=...
  4. Parsing des measure groups
  5. Appeler Garmin API : get_daily_weigh_ins() × ~30 jours → ~30 appels
  6. Appeler Garmin API : get_body_composition() × 1
  7. Dédoublonnage, construction réponse
  → ~32 appels API, ~5-10 secondes

APRÈS Phase 2 :
  1. Ouvrir Dashboard → GET /api/measurements/latest?days=30
  2. Vérifier TTL cache mémoire (30s) → MISS
  3. _fetch_withings_measurements() → SQLite HIT → 0 appels Withings
  4. GarminClient.get_daily_weigh_ins() × ~30 jours → cache HIT → 0 appels
  5. GarminClient.get_body_composition() → cache HIT → 0 appels
  6. Dédoublonnage, construction réponse
  → 0 appels API, < 1 seconde
```

#### Scénario B : Première sync de la journée

```
AVANT Phase 1 :
  1. POST /api/sync/run (start=2026-06-20, end=2026-06-24)
  2. Vérifier prérequis (2 appels API : Withings + Garmin)
  3. Fetch Withings (1 appel)
  4. Fetch Garmin weigh_ins (9 appels : 7 lookback + 1 + 1 lookahead)
  5. Fetch Garmin body comp (1 appel)
  6. Pour chaque candidat : dedup + write (1 appel chacun)
  → ~13-18 appels Garmin, ~2 appels Withings

APRÈS Phase 1+2 :
  1. POST /api/sync/run (start=2026-06-20, end=2026-06-24)
  2. Vérifier prérequis (2 appels API)
  3. Fetch Withings (1 appel)
  4. Save parsed to store (0 appels supplémentaires)
  5. Fetch Garmin weigh_ins → cache MISS → 9 appels (première fois)
  6. Fetch Garmin body comp → cache MISS → 1 appel
  7. Pour chaque write : add_body_composition → invalide cache date
  → 12 appels Garmin, 1 appel Withings (identique à avant la 1ère fois)

  ###### Deuxième sync dans l'heure ######
  3. Fetch Withings → store HIT (0 appels)
  5. Fetch Garmin weigh_ins → certains HIT, certains INVALIDATED → ~3 appels max
  6. Fetch Garmin body comp → HIT pour dates non écrites
  → ~3 appels Garmin, 0 appels Withings
```

#### Scénario C : Status check

```
AVANT Phase 4 :
  GET /api/status → 2 appels API (Withings + Garmin)
  → ~2 secondes

APRÈS Phase 4 :
  GET /api/status → cache 60s → 0 appels API
  → ~10ms
```

---

## 3. Décomposition par phase

### Phase 1 — Cache Garmin persistant

**Statut** : ✅ TERMINÉE

**Gain** : -90% appels Garmin en lecture sur syncs consécutives.

#### 3.1.1 Fichier créé : `backend/app/storage/garmin_cache.py`

```python
"""GarminCacheStore : cache SQLite persistant avec TTL 1h.

Méthodes :
  get(source_type, date_str) → list[dict] | None
  set(source_type, date_str, data) → None
  invalidate_date(date_str) → None
  invalidate_range(start, end) → None
  clear() → None

Détails d'implémentation :
  - Chaque ligne = JSON array de model dicts (model_dump mode="json")
  - TTL = 3600s (1 heure), stocké comme datetime ISO dans cache_expires_at
  - get() retourne None si l'entrée est absente OU expirée
  - set() utilise INSERT OR REPLACE (contrainte UNIQUE(date, source_type))
  - invalidate_date() supprime toutes les entrées pour une date (les deux types)
  - invalidate_range() supprime toutes les entrées BETWEEN start AND end
  - clear() DELETE FROM sans condition (urgence)
"""
```

**Code détaillé de `GarminCacheStore`** :

```python
class GarminCacheStore:
    TTL_SECONDS = 3600  # 1 heure

    def __init__(self, data_dir: Path):
        self._db_path = data_dir / "withings_tokens.db"
        self._conn: Connection | None = None

    @property
    def conn(self) -> Connection:
        if self._conn is None:
            self._conn = init_db(self._db_path)
        return self._conn

    def get(self, source_type: str, date_str: str) -> list[dict] | None:
        row = self.conn.execute(
            "SELECT data_json, cache_expires_at FROM garmin_measurements_cache "
            "WHERE source_type = ? AND date = ?",
            (source_type, date_str),
        ).fetchone()
        if row is None:
            return None
        try:
            expires = datetime.fromisoformat(row["cache_expires_at"])
            if expires <= datetime.now(UTC):
                return None
            return json.loads(row["data_json"])
        except (ValueError, TypeError, json.JSONDecodeError):
            return None

    def set(self, source_type: str, date_str: str, data: list[dict]) -> None:
        now = datetime.now(UTC)
        expires = now + timedelta(seconds=self.TTL_SECONDS)
        self.conn.execute(
            "INSERT OR REPLACE INTO garmin_measurements_cache (...) VALUES (...)",
            (date_str, source_type, json.dumps(data),
             now.isoformat(), expires.isoformat(), now.isoformat(), now.isoformat()),
        )
        self.conn.commit()

    def invalidate_date(self, date_str: str) -> None:
        self.conn.execute("DELETE FROM garmin_measurements_cache WHERE date = ?", (date_str,))
        self.conn.commit()

    def invalidate_range(self, start: str, end: str) -> None:
        self.conn.execute(
            "DELETE FROM garmin_measurements_cache WHERE date BETWEEN ? AND ?", (start, end))
        self.conn.commit()
```

#### 3.1.2 Fichier modifié : `backend/app/storage/db.py`

```python
# Ajout après GARMIN_CACHE_SCHEMA (déjà fait)
GARMIN_CACHE_SCHEMA = """
CREATE TABLE IF NOT EXISTS garmin_measurements_cache (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    date             TEXT    NOT NULL,
    source_type      TEXT    NOT NULL,
    data_json        TEXT    NOT NULL,
    fetched_at       TEXT    NOT NULL DEFAULT (datetime('now')),
    cache_expires_at TEXT    NOT NULL,
    created_at       TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at       TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE(date, source_type)
);
"""

# Dans init_db(), ajout après ATTEMPT_SCHEMA :
conn.executescript(GARMIN_CACHE_SCHEMA)
```

#### 3.1.3 Fichier modifié : `backend/app/services/garmin_client.py`

```python
# Import ajouté
from app.storage.garmin_cache import GarminCacheStore
from datetime import date, timedelta  # timedelta ajouté

# Dans __init__ :
self._cache_store = GarminCacheStore(settings.resolved_data_dir)

# get_daily_weigh_ins() modifié :
async def get_daily_weigh_ins(self, target_date: date) -> list[GarminWeighIn]:
    if self._test_data:
        return self._test_weigh_ins(target_date)
    date_str = target_date.isoformat()
    cached = self._cache_store.get("weigh_in", date_str)
    if cached is not None:
        return [GarminWeighIn(**item) for item in cached]
    raw = self._client().get_daily_weigh_ins(date_str)
    result = [self._parse_weigh_in(item, target_date)
              for item in self._extract_measurements(raw)]
    self._cache_store.set("weigh_in", date_str,
                          [r.model_dump(mode="json") for r in result])
    return result

# get_body_composition() modifié :
#   → itère date par date sur le range
#   → cache HIT → utilise les données
#   → cache MISS → accumulate dans dates_to_fetch
#   → si dates_to_fetch non vide : 1 appel API pour le sous-range manquant
#   → déduplication : les dates déjà en cache ne sont pas ajoutées au résultat
#   → chaque entrée parsée est cachée individuellement par date

# add_body_composition() modifié :
#   → après un succès, extrait la date du timestamp et invalide le cache
```

**Détail du mécanisme de déduplication dans `get_body_composition`** :

```python
# Problème : l'API Garmin retourne un range, pas des dates individuelles.
# Si le cache a date_A et date_C, mais pas date_B :
#   → dates_to_fetch = [date_B]
#   → API appelée pour [date_B, date_B] (1 jour)
#   → L'API pourrait retourner date_A, date_B, date_C si elle arrondit
#   → On skip date_A et date_C car déjà dans cached_by_date
#   → On cache date_B (et date_A/date_C si l'API les a retournées)
```

#### 3.1.4 Tests de non-régression

```bash
# Résultat attendu : 62/64 passent (2 échecs credentials .env pré-existants)
pytest backend/tests/ -v --tb=short
```

**Cas à tester manuellement** (pas de tests automatisés pour le cache encore) :

| Cas | Comportement attendu |
|---|---|
| Cache vide → get_daily_weigh_ins() | Appel API + stockage dans cache |
| Cache frais → get_daily_weigh_ins() | 0 appels API, retourne données parsées |
| Cache expiré → get_daily_weigh_ins() | Appel API, remplacement du cache |
| add_body_composition() → re-get | Cache invalidé, nouvel appel API |
| get_body_composition() range mixte | Appel API seulement pour dates manquantes |
| Deux syncs identiques consécutives | 0 appels Garmin sur la deuxième |

---

### Phase 2 — Stockage mesures Withings

**Statut** : ✅ TERMINÉE

**Gain** : -100% appels Withings API en lecture Dashboard après ≥1 sync.

**Principe** : Chaque sync stocke les mesures parsées dans `withings_measurements`.
Les routes Dashboard lisent depuis cette table d'abord (store-first, API-fallback).

#### 3.2.1 Fichier créé : `backend/app/storage/measurement_store.py`

```python
"""WithingsMeasurementStore : stockage persistant des mesures parsées.

Points clés :
  - Les Decimal sont stockés en TEXT pour préserver la précision
  - source_measure_group_id est UNIQUE → INSERT OR IGNORE (idempotent)
  - Index sur date et measured_at_utc pour les requêtes Dashboard
  - Pas de TTL explicite : les données sont rafraîchies à chaque sync
  - get_latest() = ORDER BY measured_at_utc DESC LIMIT 1
  - get_recent(days) = measured_at_utc >= now - days

Conversion Decimal ↔ TEXT :
  __init__: Decimal(str(value)) pour reconstituer la précision
  save: str(decimal_val) pour stocker sans perte

Conversion raw ↔ JSON :
  raw (dict) → json.dumps(raw, default=str) → raw_json TEXT
  raw_json TEXT → json.loads(raw_json) → raw (dict)
"""
```

**Méthodes exposées** :

| Méthode | Signature | SQL | Complexité |
|---|---|---|---|
| `save_measurements` | `(list[BodyCompositionMeasurement]) → int` | INSERT OR IGNORE (21 paramètres) | O(n) |
| `get_measurements` | `(start_date, end_date) → list` | SELECT * WHERE date BETWEEN | O(log n) grâce à l'index |
| `get_latest` | `() → BodyCompositionMeasurement | None` | SELECT * ORDER BY measured_at_utc DESC LIMIT 1 | O(log n) |
| `get_recent` | `(days) → list` | SELECT * WHERE measured_at_utc >= cutoff | O(log n) |
| `get_by_id` | `(group_id) → BodyCompositionMeasurement | None` | SELECT * WHERE source_measure_group_id = ? | O(1) (UNIQUE) |
| `get_count` | `() → int` | SELECT COUNT(*) | O(1) |
| `clear` | `() → None` | DELETE FROM | O(n) |

#### 3.2.2 Fichier modifié : `backend/app/services/sync_engine.py`

```python
# Import ajouté
from app.storage.measurement_store import WithingsMeasurementStore

# Dans __init__() :
self._measurement_store = WithingsMeasurementStore(settings.resolved_data_dir)

# Dans run_sync(), APRÈS parse_measure_groups(), AVANT _filter_period() :
parsed = self._parser.parse_measure_groups(withings_raw_groups)

# [NOUVEAU] Sauvegarde dans le store persistant
saved = self._measurement_store.save_measurements(parsed)
if saved:
    _log().info("Saved %d new measurements to persistent store", saved)

parsed = self._filter_period(self._apply_per_day_strategy(parsed), start_day, end_day)
```

**Pourquoi après parse et avant filter** :
- `parse_measure_groups()` parse TOUS les groupes bruts retournés par l'API Withings pour la fenêtre demandée
- `_filter_period()` ne garde que ceux dans [start_day, end_day]
- On veut stocker TOUS les mesures parsées, pas seulement les filtrés
- `INSERT OR IGNORE` → pas de doublon si une mesure est déjà stockée

**Contrat d'idempotence** :
```
Sync avec start=2026-06-20, end=2026-06-24 :
  → API Withings retourne 10 measure groups
  → parse → 10 BodyCompositionMeasurement (group_ids = A, B, C, D, E, F, G, H, I, J)
  → save_measurements → 10 INSERT OR IGNORE → 10 nouvelles lignes

Sync identique relancée 5 minutes après :
  → API Withings retourne les mêmes 10 measure groups
  → parse → 10 BodyCompositionMeasurement (mêmes group_ids)
  → save_measurements → 10 INSERT OR IGNORE → 0 nouvelles lignes (toutes ignorées)
```

#### 3.2.3 Fichier modifié : `backend/app/api/routes_measurements.py`

```python
# Import ajouté
from app.storage.measurement_store import WithingsMeasurementStore
from app.models.withings import BodyCompositionMeasurement

# Dans _build_services() :
meas_store = WithingsMeasurementStore(settings.resolved_data_dir)
# ... return inclut meas_store

# Nouvelle fonction helper :
async def _fetch_withings_measurements(
    wclient, parser, store, start_dt, end_dt,
) -> tuple[list[BodyCompositionMeasurement], int]:
    """Store-first, API-fallback.  Retourne (parsed, raw_groups_count)."""
    start_date = start_dt.date()
    end_date = end_dt.date()
    if start_date <= end_date:
        parsed = store.get_measurements(start_date.isoformat(), end_date.isoformat())
        if parsed:
            return parsed, len(parsed)
    # Fallback API
    raw = await wclient.get_measurements(start_dt, end_dt)
    parsed = parser.parse_measure_groups(raw)
    if parsed:
        store.save_measurements(parsed)
    return parsed, len(raw)

# Chaque route modifiée pour utiliser _fetch_withings_measurements() :
#   /latest     → remplace get_measurements + parse
#   /recent     → remplace get_measurements + parse
#   /history    → remplace get_measurements + parse
```

**Détail du fallback** : Quand le store est vide (première utilisation, aucune sync effectuée), la route appelle l'API Withings comme avant, et sauvegarde les résultats dans le store pour la prochaine fois.

**Taux de succès attendu** :
```
T0 : Aucune sync effectuée → Dashboard → store vide → API Withings (1 appel)
T1 : Sync effectuée → 10 mesures stockées
T2 : Dashboard rechargé → store HIT → 0 appels Withings
T3 : Nouvelle mesure Withings (le lendemain)
T4 : Sync effectuée → 11 mesures (10 existantes + 1 nouvelle) → 1 INSERT, 10 IGNORE
T5 : Dashboard → store HIT → 0 appels Withings
```

---

### Phase 3 — Normalisation jobs / candidats / décisions

**Statut** : ⏳ PLANIFIÉE

**Gain** : Auditabilité, requêtes simplifiées, préparation pour renommage de la base.

**Risque** : MOYEN — touche aux tables existantes (sync_events, sync_attempts).

#### 3.3.1 Problème résolu

Aujourd'hui, `sync_events` est une table fourre-tout avec 22 colonnes. Les colonnes
`report_json`, `garmin_response_json` sont des JSON blob difficiles à requêter.
`sync_attempts` est minimaliste (7 colonnes).

**Problèmes** :
1. Impossible de requêter "tous les candidats d'un job" (pas de FK)
2. `report_json` contient des données structurées non indexables
3. `garmin_response_json` est rarement utile mais prend de la place
4. Pas de colonne `trigger` → on ne sait pas si une sync est manuelle ou automatique
5. Pas de `duration_seconds` → difficile de monitorer les performances

#### 3.3.2 Nouvelles tables (DDL dans la section 2.2)

**`sync_jobs`** (remplace `sync_attempts`) :
- `run_id` UUID v4 pour identifier chaque run de manière unique
- `trigger` pour savoir qui a lancé ('manual', 'scheduled', 'webhook')
- `duration_seconds` calculé automatiquement
- Tous les compteurs de candidats dénormalisés pour requêtage rapide

**`sync_candidates`** (remplace `sync_events`) :
- `job_id` FK vers `sync_jobs` → permet les requêtes "tous les candidats d'un job"
- Colonnes dédiées pour chaque champ mappé (pas de JSON blob pour les données fréquentes)
- `mapped_fields_json`, `ignored_fields_json`, `null_fields_json`, `mapping_warnings_json` → JSON séparés, facultatifs
- `garmin_response_json` conservé mais optionnel

**`sync_decisions`** (nouvelle table, pas de correspondance directe) :
- Découplée de `sync_candidates` pour permettre plusieurs décisions
- Stocke le epsilon et le poids existant pour debug

#### 3.3.3 Migration des données existantes

```python
def migrate_v1_to_v2(conn):
    """Migrer sync_attempts → sync_jobs et sync_events → sync_candidates."""
    
    # 1. Créer les nouvelles tables (CREATE TABLE IF NOT EXISTS)
    conn.executescript(SYNC_JOBS_SCHEMA)
    conn.executescript(SYNC_CANDIDATES_SCHEMA)
    conn.executescript(SYNC_DECISIONS_SCHEMA)
    
    # 2. Copier sync_attempts → sync_jobs
    rows = conn.execute("""
        SELECT started_at, completed_at, start_date, end_date,
               status, summary_json, error_message
        FROM sync_attempts
    """).fetchall()
    for row in rows:
        duration = None
        if row["completed_at"] and row["started_at"]:
            try:
                s = datetime.fromisoformat(row["started_at"])
                c = datetime.fromisoformat(row["completed_at"])
                duration = (c - s).total_seconds()
            except (ValueError, TypeError):
                pass
        conn.execute("""
            INSERT OR IGNORE INTO sync_jobs
                (run_id, started_at, completed_at, start_date, end_date,
                 trigger, status, duration_seconds, error_message)
            VALUES (?, ?, ?, ?, ?, 'manual', ?, ?, ?)
        """, (str(uuid4()), row["started_at"], row["completed_at"],
              row["start_date"], row["end_date"],
              row["status"], duration, row["error_message"]))
    
    # 3. Copier sync_events → sync_candidates
    rows = conn.execute("""
        SELECT idempotency_key, source, withings_measure_id,
               source_measured_at_utc, local_date, weight_kg, status,
               garmin_write_method, garmin_response_json, error_message,
               report_json
        FROM sync_events
    """).fetchall()
    for row in rows:
        # Extraire les champs du report_json si disponible
        report = json.loads(row["report_json"]) if row["report_json"] else {}
        mapped = report.get("mapped_fields", {}) if isinstance(report, dict) else {}
        conn.execute("""
            INSERT OR IGNORE INTO sync_candidates
                (job_id, idempotency_key, source, source_measure_group_id,
                 date, weight_kg, decision, garmin_write_method,
                 garmin_response_json, error_message, mapped_fields_json)
            VALUES (NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (...))
    
    # 4. Marquer la migration comme appliquée
    conn.execute("INSERT INTO schema_migrations (version, description) VALUES (?, ?)",
                 ("001", "Migrate sync_events/attempts to sync_jobs/candidates"))
    conn.commit()
```

#### 3.3.4 Renommage de la base (optionnel)

```python
# Renommer withings_tokens.db → garminsync.db
# Le nom "withings_tokens" est trompeur puisque la base contient bien plus que des tokens.
# 
# Stratégie :
# 1. Créer le nouveau fichier avec les nouvelles tables
# 2. Copier les données des anciennes tables
# 3. Basculer le point de connexion
# 
# Risque : élevé (tous les stores pointent vers le même fichier).
# À faire uniquement si le gain justifie le risque.
```

**Décision** : NE PAS renommer la base pour l'instant. Le nom `withings_tokens.db` est
historique mais fonctionnel. Le renommage peut être fait ultérieurement comme migration
cosmétique.

#### 3.3.5 Impact sur `SyncEngine.run_sync()`

```python
# Modifications :
# 1. Créer un run_id (UUID) au début de run_sync
# 2. Initialiser sync_jobs avec status='running'
# 3. Après chaque _process_candidate, insérer dans sync_candidates
# 4. Après chaque décision, insérer dans sync_decisions
# 5. À la fin, update sync_jobs avec status='completed' et duration

def run_sync(self, start_date, end_date, ...):
    run_id = str(uuid4())
    job_id = self._sync_store.create_job(run_id, start_date, end_date)
    
    try:
        # ... (pipeline existant)
        for candidate in candidates:
            item = await self._process_candidate(candidate, ...)
            # [NOUVEAU] Sauvegarde dans sync_candidates
            candidate_id = self._sync_store.save_candidate(job_id, item)
            # [NOUVEAU] Sauvegarde dans sync_decisions
            self._sync_store.save_decision(candidate_id, item.decision, item.reason)
        
        self._sync_store.finish_job(job_id, "completed", summary)
    except:
        self._sync_store.finish_job(job_id, "failed", error=str(exc))
```

#### 3.3.6 Objets concernés

| Fichier | Changement |
|---|---|
| `storage/sync_store.py` | Refactor complet — `SyncStore` devient `JobStore` avec méthodes `create_job`, `save_candidate`, `save_decision` |
| `storage/db.py` | + SYNC_JOBS_SCHEMA, SYNC_CANDIDATES_SCHEMA, SYNC_DECISIONS_SCHEMA, SCHEMA_MIGRATIONS_SCHEMA |
| `services/sync_engine.py` | Adapter pour utiliser les nouveaux stores |
| `api/routes_sync.py` | Adapter aux nouveaux champs du rapport |
| `services/report_builder.py` | Adapter si le format du rapport change |

#### 3.3.7 Stratégie de rollback Phase 3

```python
# Si la Phase 3 doit être annulée :
# 1. Les anciennes tables sync_events et sync_attempts sont conservées (inchangées)
# 2. Les nouvelles tables sync_jobs, sync_candidates, sync_decisions sont simplement ignorées
# 3. Pour un rollback complet : DROP TABLE sync_jobs, sync_candidates, sync_decisions, schema_migrations
# 4. Aucune perte de données car les anciennes tables n'ont pas été supprimées
```

---

### Phase 4 — Optimisation API et UI

**Statut** : ⏳ PLANIFIÉE

**Gain** : UI réactive sans spinner, status instantané.

**Risque** : FAIBLE — changements localisés, pas de modification des données.

#### 3.4.1 Problèmes résolus

1. **`/api/status` lent** : 2 appels API (Withings + Garmin) à chaque chargement de page
2. **Dashboard lent au premier chargement** : 30+ appels API avant d'afficher les données
3. **Spinners UI** : l'UI montre des spinners pendant que les données arrivent
4. **Recharges inutiles** : l'UI se rafraîchit trop souvent

#### 3.4.2 Cache de statut 60s

```python
# Nouveau : GET /api/status avec cache
from app.cache import get_cache

@router.get("/status")
async def get_status():
    cache = get_cache()
    cached = cache.get("status")
    if cached is not None:
        return cached
    
    # Appels API (maintenant réduits grâce aux caches SQLite)
    withings = await withings_auth.check_connection()
    garmin = await garmin_client.check_connection()
    
    result = {
        "withings": withings,
        "garmin": garmin,
        "cached_at": datetime.now(UTC).isoformat(),
    }
    cache.set("status", result, ttl=60)  # 60s cache
    return result
```

**Pourquoi 60s et pas plus** : Le status doit être "presque" en temps réel pour que
l'utilisateur sache si son API est connectée. 60s est un bon compromis.

#### 3.4.3 Stale-while-revalidate pour le Dashboard

```python
# Principe : servir le cache immédiatement, puis rafraîchir en arrière-plan
# pour que la prochaine requête soit fraîche.

from app.cache import get_cache
import asyncio

async def serve_stale_with_revalidate(key, fetch_func, ttl=30, stale_ttl=300):
    """Servir le cache (même périmé), rafraîchir en arrière-plan."""
    cache = get_cache()
    cached = cache.get(key)
    meta = cache.get(f"{key}:meta") or {}
    
    now = datetime.now(UTC)
    
    if cached is not None:
        age = (now - datetime.fromisoformat(meta.get("cached_at", now.isoformat()))).total_seconds()
        
        if age < ttl:
            # Cache frais → retour immédiat
            return cached
        else:
            # Cache périmé mais disponible → servir + refresh async
            if age < stale_ttl:
                asyncio.create_task(_background_refresh(key, fetch_func))
                return cached
            # Cache trop vieux → attendre le refresh
            # (fall through to fetch)
    
    # Cache vide ou trop vieux → fetch synchrone
    result = await fetch_func()
    cache.set(key, result)
    cache.set(f"{key}:meta", {"cached_at": now.isoformat()})
    return result
```

#### 3.4.4 Endpoint `/api/measurements/history` en lecture SQLite pure

Actuellement, `/history` fait :
1. Fetch Withings API (→ store depuis Phase 2)
2. Fetch Garmin API (→ cache depuis Phase 1)
3. Dedup chaque mesure
4. Check sync_store pour chaque idempotency_key

**Optimisation Phase 4** :
```python
# 1. Lire depuis le store Withings (déjà fait Phase 2)
# 2. Lire depuis le cache Garmin (déjà fait Phase 1)
# 3. Joindre avec sync_candidates (Phase 3) pour éviter de re-dedup
# 4. Si tout est en cache → 0 appels API
```

#### 3.4.5 Endpoint `/api/measurements/latest` — réduction des appels Garmin

Actuellement, `/latest` fetch Garmin weigh_ins pour chaque jour de la fenêtre de
recherche (7 jours lookback + 1 jour lookahead = ~9 appels).

**Optimisation** : Avec le cache Garmin (Phase 1), ces appels sont déjà réduits.
En Phase 4, on peut ajouter un cache de plus haut niveau :

```python
# Cache la réponse complète de /latest pendant 5 minutes
# (en plus du cache SQLite et du TTLCache 30s existant)
@router.get("/latest")
async def get_latest(days=30, settings=Depends(get_settings)):
    cache = get_cache()
    key = f"latest_response:{days}"
    cached = cache.get(key)
    if cached is not None:
        return cached
    
    # ... pipeline normal (maintenant rapide grâce aux caches Phases 1+2)
    
    cache.set(key, result, ttl=300)  # 5 minutes
    return result
```

#### 3.4.6 Endpoints concernés

| Endpoint | Cache actuel | Cache Phase 4 |
|---|---|---|
| `GET /api/status` | Aucun | 60s mémoire |
| `GET /api/measurements/latest` | 30s TTLCache | 5min TTLCache + stale-while-revalidate |
| `GET /api/measurements/recent` | Aucun | Store SQLite (Phase 2) |
| `GET /api/measurements/history` | Aucun | Store SQLite + cache Garmin |
| `GET /api/sync/stats` | Aucun | 60s cache (données quasi-statiques) |

#### 3.4.7 Fichiers concernés

| Fichier | Changement |
|---|---|
| `api/routes_status.py` | Ajout cache 60s |
| `api/routes_measurements.py` | Ajout stale-while-revalidate pour /latest |
| `cache.py` | Optionnel : extension TTL max |

---

## 4. Dépendances entre phases

```
Phase 1 (Cache Garmin)
  │
  ├──▶ Phase 2 (Store Withings)
  │       │
  │       └──▶ Phase 3 (Jobs/Candidates)
  │               │
  │               └──▶ Phase 4 (Optimisation UI)
  │
  └──▶ Phase 4 directement (status cache)
```

**Règles** :
- Phase 1 doit être faite avant Phase 4 (le status cache utilise le même pattern)
- Phase 2 doit être faite avant Phase 3 (sync_candidates lit depuis le store)
- Phase 3 est indépendante de Phase 4 (peuvent être faites en parallèle)
- Chaque phase est autonome et peut être déployée individuellement

---

## 5. Stratégie de migration et rollback

### 5.1 Principe général

Chaque phase crée des tables via `CREATE TABLE IF NOT EXISTS`. Aucune table existante
n'est modifiée ou supprimée. Le rollback consiste simplement à ignorer les nouvelles
tables.

### 5.2 Migration de la base existante

```python
# La base contains actuellement :
#   withings_tokens (1 ligne)
#   withings_oauth_states (0 lignes)
#   sync_events (14 lignes)
#   sync_attempts (21 lignes)

# Après Phase 1 : + garmin_measurements_cache (0 lignes → se remplit au premier appel)
# Après Phase 2 : + withings_measurements (0 lignes → se remplit à la première sync)
# Après Phase 3 : + sync_jobs, sync_candidates, sync_decisions, schema_migrations

# La migration de sync_events → sync_candidates se fait par script (section 3.3.3)
```

**Ordre de migration** :
1. Déployer Phase 1 + Phase 2 en même temps (tables créées au premier `init_db`)
2. Faire une sync complète
3. Vérifier que les Dashboard endpoints servent depuis le cache
4. Déployer Phase 3
5. Lancer le script de migration des anciennes données
6. Vérifier que les nouveaux endpoints de lecture marchent
7. Déployer Phase 4

### 5.3 Rollback

```python
# Rollback Phase 1 (si problème) :
#   → Supprimer la table garmin_measurements_cache
#   → Revenir à l'ancienne version de garmin_client.py
#   → Aucune perte de données réelles (juste du cache)

# Rollback Phase 2 (si problème) :
#   → Supprimer la table withings_measurements
#   → Revenir à l'ancienne version de routes_measurements.py
#   → Aucune perte de données réelles (juste du cache)

# Rollback Phase 3 (si problème) :
#   → Supprimer les tables sync_jobs, sync_candidates, sync_decisions
#   → Revenir à l'ancienne version de sync_engine.py
#   → Les données sync_events/attempts sont conservées
#   → Perte de données : les sync_jobs/candidates de la version Phase 3

# Rollback Phase 4 (si problème) :
#   → Revenir à l'ancienne version de routes_status.py
#   → Aucune perte de données
```

### 5.4 Plan de test de non-régression

```bash
# À exécuter avant chaque déploiement
pytest backend/tests/ -v --tb=short

# Résultat attendu : 62/64 (sauf si Phase 3 ajoute des tests)

# Vérifications manuelles :
# 1. Lancer une sync (POST /api/sync/run)
# 2. Vérifier le Dashboard (GET /api/measurements/latest)
# 3. Vérifier le status (GET /api/status)
# 4. Vérifier les données dans la base (sqlite3 data/withings_tokens.db)
```

---

## 6. Glossaire

| Terme | Définition |
|---|---|
| **Store** | Table SQLite contenant des données parsées, utilisée en lecture prioritaire. Pas de TTL. |
| **Cache** | Table SQLite avec expiration (TTL). Invalidation explicite après écriture. |
| **TTL** | Time To Live. Durée de validité d'une entrée de cache. |
| **HIT** | L'entrée de cache existe et est valide. |
| **MISS** | L'entrée de cache n'existe pas ou est expirée. |
| **Store-first** | Pattern : lire depuis le store, appeler l'API uniquement si le store est vide. |
| **Cache-through** | Pattern : lire depuis le cache, appeler l'API si MISS, stocker le résultat. |
| **Stale-while-revalidate** | Servir le cache périmé immédiatement, rafraîchir en background. |
| **INSERT OR IGNORE** | SQLite : insère seulement si la contrainte UNIQUE n'est pas violée. |
| **WAL** | Write-Ahead Logging. Mode SQLite qui permet lectures concurrentes. |
| **GarminBodyCompositionCandidate** | Modèle Pydantic pour une mesure prête à écrire dans Garmin. |
| **BodyCompositionMeasurement** | Modèle Pydantic pour une mesure Withings parsée. |

---

## Annexe A : État actuel des tests

```
Phases 1+2 : 62/64 passent, 2 échecs pré-existants (credentials .env)
```

| Test | Statut | Note |
|---|---|---|
| test_sync.py (6 tests) | ✅ | Pipeline complet mocké |
| test_dedup.py (8 tests) | ✅ | Tous les cas de dédoublonnage |
| test_mapping.py (9 tests) | ✅ | Mapping Withings → Garmin |
| test_garmin_api.py (9 tests) | ✅ | Paramètres Garmin |
| test_admin_api.py (9 tests) | ✅ | Routes admin |
| test_security.py (8 tests) | ❌ 2/8 | Credentials .env interfèrent |
| test_units.py (6 tests) | ✅ | Helpers |

## Annexe B : Évolution du nombre d'appels API

| Phase | Sync (1ère fois) | Sync (2ème fois, <1h) | Dashboard (après sync) | Status |
|---|---|---|---|---|
| Avant | 15-18 | 15-18 | 30-32 | 2 |
| Phase 1 | 12-13 | 0-3 | 1-3 | 2 |
| Phase 1+2 | 12-13 | 0-3 | 0-2 | 2 |
| Phase 1+2+3 | 12-13 | 0-3 | 0-1 | 2 |
| Phase 1+2+3+4 | 12-13 | 0-3 | 0-1 | 0 |
