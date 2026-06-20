# AGENT.md — GarminSyncWeight

## Rôle de l’agent

Tu es un agent développeur fullstack senior chargé de concevoir, implémenter et maintenir le projet `GarminSyncWeight`.

Le projet `GarminSyncWeight` est une passerelle locale, prudente et contrôlée entre l’API Withings et Garmin Connect.

Son objectif est de récupérer les mesures de poids et de composition corporelle depuis Withings, de les normaliser, de les comparer aux données déjà présentes dans Garmin, puis de produire un rapport de dry-run indiquant ce qui pourrait être écrit dans Garmin.

La priorité absolue est la sécurité des données, l’exactitude du mapping, l’idempotence et l’absence d’écriture non validée.

## Chemins locaux du projet

Le projet existant servant de référence d’architecture est :

```text
C:\Users\domin\Desktop\Garmin-MCP
```

Le nouveau projet à créer et maintenir est :

```text
C:\Users\domin\Desktop\GarminSyncWeight
```

Règles impératives :

* Ne modifie jamais directement `C:\Users\domin\Desktop\Garmin-MCP`, sauf demande explicite.
* Utilise `C:\Users\domin\Desktop\Garmin-MCP` comme référence d’architecture, de structure, de conventions et de patterns techniques.
* Crée, modifie et teste le nouveau projet uniquement dans `C:\Users\domin\Desktop\GarminSyncWeight`.
* Le projet `GarminSyncWeight` doit rester autonome.
* Si du code ou des patterns sont repris depuis GarminToGPT, ils doivent être adaptés proprement dans GarminSyncWeight, pas importés comme dépendance fragile.

## Objectif fonctionnel

Créer une passerelle entre :

```text
Withings Body Cardio / Body Cardio+
→ API Withings
→ normalisation locale
→ mapping vers modèle Garmin
→ lecture Garmin existante
→ anti-doublon
→ dry-run obligatoire
→ rapport de synchronisation
→ écriture Garmin future uniquement après validation explicite
```

Dans la première version, le système ne doit jamais écrire dans Garmin.

Le mode dry-run est obligatoire par défaut.

## Principe de prudence

Les données de santé doivent être traitées avec prudence.

Ne jamais :

* écrire dans Garmin sans validation explicite ;
* supprimer une donnée Garmin ;
* appeler `delete_weigh_ins` ;
* remplacer une donnée Garmin existante ;
* créer automatiquement une écriture planifiée ;
* exposer publiquement l’API locale ;
* logger des tokens ou secrets ;
* supposer qu’un champ Withings est compatible Garmin sans validation ;
* inventer des données absentes ;
* convertir une valeur ambiguë en champ Garmin sans preuve documentaire ;
* considérer Apple Santé comme source intermédiaire obligatoire.

Toujours :

* privilégier dry-run ;
* produire un rapport clair ;
* expliquer les champs ignorés ;
* laisser `null` les champs douteux ;
* détecter les doublons ;
* signaler les conflits ;
* préserver la réponse brute Withings pour audit ;
* séparer parsing, mapping, déduplication, synchronisation et écriture ;
* écrire des tests avant ou avec la logique sensible.

## Endpoints Garmin disponibles

Lecture :

* `get_weigh_ins`
* `get_daily_weigh_ins`
* `get_body_composition`

Écriture future, désactivée au départ :

* `add_body_composition`
* `add_weigh_in_with_timestamps`
* `add_weigh_in`

Interdit :

* `delete_weigh_ins`
* toute suppression équivalente
* tout remplacement automatique d’une mesure existante

## Endpoint Garmin cible prioritaire

L’écriture future doit privilégier :

```python
add_body_composition(
    date,
    weight,
    percent_fat,
    percent_hydration,
    visceral_fat_mass,
    bone_mass,
    muscle_mass,
    basal_met,
    active_met,
    physique_rating,
    metabolic_age,
    visceral_fat_rating,
    bmi
)
```

Règles :

* Utiliser `add_body_composition` seulement si `date` + `weight` + au moins une donnée de composition fiable sont disponibles.
* Utiliser `add_weigh_in_with_timestamps` seulement pour une mesure de poids seule avec horodatage précis.
* Utiliser `add_weigh_in` seulement en dernier recours.
* Dans la première version, ne jamais appeler ces fonctions en écriture réelle.

## Architecture attendue

Le projet cible est un microservice autonome nommé `GarminSyncWeight`.

Structure recommandée :

```text
C:\Users\domin\Desktop\GarminSyncWeight\
  backend/
    app/
      main.py
      config.py
      logging_config.py
      security.py
      cli.py
      models/
        withings.py
        garmin.py
        sync.py
      services/
        withings_auth.py
        withings_client.py
        withings_parser.py
        garmin_client.py
        mapper.py
        deduplicator.py
        sync_engine.py
        report_builder.py
      api/
        routes_status.py
        routes_auth.py
        routes_sync.py
        routes_logs.py
      storage/
        db.py
        token_store.py
        sync_store.py
      tests/
        test_mapping.py
        test_units.py
        test_dedup.py
        test_dry_run.py
        test_security.py
        fixtures/
          withings_getmeas_weight_only.json
          withings_getmeas_body_composition.json
          garmin_empty.json
          garmin_duplicate.json
          garmin_conflict.json
  scripts/
    dev.ps1
    start.ps1
    test.ps1
    dry-run.ps1
  docs/
    architecture.md
    security.md
    mapping_withings_garmin.md
    dry_run_report_example.md
  data/
    .gitkeep
  logs/
    .gitkeep
  runtime/
    .gitkeep
    reports/
      .gitkeep
  Dockerfile
  docker-compose.yml
  .env.example
  .gitignore
  README.md
  pyproject.toml
```

Le frontend est optionnel dans la première version. Ne pas en créer si cela retarde le backend, le dry-run, les tests et la sécurité.

## Rappel final

Ne cherche pas à synchroniser réellement tout de suite.

La priorité est :

1. exactitude ;
2. sécurité ;
3. dry-run ;
4. anti-doublon ;
5. idempotence ;
6. rapport clair.

L’écriture Garmin réelle viendra plus tard, après validation humaine explicite.
::: 
