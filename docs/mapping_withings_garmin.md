# Mapping Withings → Garmin

## Tableau de correspondance

| Garmin | Withings Type | Statut | Notes |
|---|---|---|---|
| `date` | timestamp Withings | ✅ Certain | Dérivé du timestamp Withings, timezone configurable |
| `weight` | type 1 (kg) | ✅ Certain | Poids directement compatible |
| `percent_fat` | type 6 (fat ratio) | ⚠️ Probable | Pourcentage de masse grasse, à confirmer |
| `bone_mass` | type 88 (kg) | ⚠️ Probable | Masse osseuse en kg, à confirmer |
| `muscle_mass` | type 76 (kg) | ⚠️ Probable | Masse musculaire en kg, à confirmer |
| `bmi` | calculé | ⚠️ Calculé | `weight / height²` — null si `USER_HEIGHT_M` absent |
| `percent_hydration` | type 77 (kg) | ❌ Ambigu | Withings renvoie en kg, pas en %. **Null par défaut.** |
| `visceral_fat_mass` | — | ❌ Non mappé | Pas de source Withings confirmée |
| `basal_met` | — | ❌ Non mappé | Pas de source Withings confirmée |
| `active_met` | — | ❌ Non mappé | Pas de source Withings confirmée |
| `physique_rating` | — | ❌ Non mappé | Pas de source Withings confirmée |
| `metabolic_age` | — | ❌ Non mappé | Pas de source Withings confirmée |
| `visceral_fat_rating` | — | ❌ Non mappé | Pas de source Withings confirmée |

## Légende

- ✅ **Certain** : mapping fiable et testé
- ⚠️ **Probable** : compatible Withings, à confirmer sur données réelles
- ⚠️ **Calculé** : dérivé, pas source directe
- ❌ **Ambigu** : données Withings disponibles mais format incompatible
- ❌ **Non mappé** : volontairement null, documentation Withings insuffisante

## Décisions de mapping

### Hydratation

Withings type 77 semble renvoyer la masse d'hydratation **en kilogrammes**,
tandis que Garmin attend un **pourcentage**. La conversion n'est pas triviale
et dépend de la formule exacte utilisée par Withings.

**Décision** : Ne pas mapper automatiquement. `percent_hydration` reste `null`.
Le champ `hydration_mass_kg` est conservé dans `ignored_fields` pour audit.

### IMC

L'IMC Garmin peut être calculé si la taille utilisateur est configurée
explicitement via `USER_HEIGHT_M`. Sans cette configuration, `bmi` reste `null`.

Formule : `bmi = weight_kg / (height_m)²`

### Champs non mappés par prudence

`visceral_fat_mass`, `basal_met`, `active_met`, `physique_rating`,
`metabolic_age`, `visceral_fat_rating` — ces champs n'ont pas de source
Withings directe confirmée dans la documentation actuelle. Ils restent `null`
jusqu'à validation explicite.

## Décision de méthode d'écriture

| Condition | Méthode Garmin |
|---|---|
| Poids + composition fiable | `add_body_composition` |
| Poids seul + timestamp pertinent | `add_weigh_in_with_timestamps` |
| Poids seul | `add_weigh_in` |
| Ni poids ni composition | `invalid` |

## Limites

- La documentation des types de mesure Withings n'est pas exhaustive.
  Les types 76 (muscle), 77 (hydratation) et 88 (os) sont des hypothèses
  issues de la communauté, pas de la documentation officielle Withings.
- Vérifier les réponses réelles de l'API Withings avant utilisation
  en production.
