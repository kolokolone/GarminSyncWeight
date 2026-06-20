# Exemple de rapport dry-run

```json
{
  "mode": "dry_run",
  "period": {
    "start_date": "2026-06-01",
    "end_date": "2026-06-19",
    "timezone": "Europe/Paris"
  },
  "withings": {
    "raw_groups_count": 12,
    "parsed_measurements_count": 10,
    "measurements": [
      {
        "group_id": "1001",
        "date_local": "2026-06-01T08:30:00+02:00",
        "weight_kg": "78.5",
        "fields": {
          "weight_kg": "78.5",
          "fat_percent": "22.0",
          "muscle_mass_kg": "55.0",
          "bone_mass_kg": "2.8",
          "hydration_mass_kg": "42.0",
          "bmi": null
        }
      }
    ]
  },
  "garmin": {
    "daily_weigh_ins": [
      {"date": "2026-06-01", "weight_kg": "78.5"}
    ],
    "body_composition": [
      {"date": "2026-06-01", "weight_kg": "78.5"}
    ]
  },
  "candidates": [
    {
      "date": "2026-06-01",
      "measured_at_local": "2026-06-01T08:30:00+02:00",
      "source_measure_group_id": "1001",
      "mapped_fields": {
        "weight": 78.5,
        "percent_fat": 22.0,
        "bone_mass": 2.8,
        "muscle_mass": 55.0
      },
      "ignored_fields": {
        "hydration_mass_kg": 42.0
      },
      "null_fields": [
        "percent_hydration",
        "visceral_fat_mass",
        "basal_met",
        "active_met",
        "physique_rating",
        "metabolic_age",
        "visceral_fat_rating",
        "bmi"
      ],
      "warnings": [
        "hydration_mass_kg provided but percent_hydration not computed — conversion formula not validated",
        "visceral_fat_mass, basal_met, active_met, ...: no reliable Withings source — set to null"
      ],
      "dedup_status": "duplicate_exact_or_near",
      "decision": "skip",
      "garmin_call": {
        "method": "none",
        "params": {}
      },
      "idempotency_key": "withings:1001:2026-06-01:78.50:nodevice"
    }
  ],
  "summary": {
    "would_write_count": 2,
    "skipped_duplicates_count": 7,
    "possible_duplicates_count": 0,
    "conflicts_count": 1,
    "invalid_count": 0,
    "warnings_count": 3
  }
}
```

## Interprétation

| Champ | Signification |
|---|---|
| `mode` | Toujours `"dry_run"` en v1 |
| `withings.raw_groups_count` | Nombre de groupes récupérés |
| `withings.parsed_measurements_count` | Nombre de mesures exploitables |
| `candidates[].dedup_status` | Statut après comparaison Garmin |
| `candidates[].decision` | `would_write` ou `skip` |
| `candidates[].garmin_call.method` | Méthode qui serait utilisée |
| `summary.would_write_count` | **Nombre d'écritures potentielles** |

## Prochaines étapes après validation du rapport

1. Vérifier les candidats `would_write`
2. S'assurer que les champs mappés sont corrects
3. Si tout est OK → définir `ENABLE_GARMIN_WRITES=true`
4. Relancer en dry-run pour confirmer
5. Ajouter l'argument `--execute` à la commande CLI
6. La première écriture réelle Garmin se produit
