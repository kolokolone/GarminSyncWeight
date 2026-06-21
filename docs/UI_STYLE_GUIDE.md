# UI Style Guide — GarminSyncWeight

## Objectif du fichier

Ce document décrit le style visuel à conserver pour GarminSyncWeight pendant la refonte UX/navigation.

La refonte demandée ne doit pas transformer l’identité graphique de l’application. Elle doit améliorer l’organisation, la lisibilité, les parcours utilisateur et les composants, tout en restant visuellement cohérente avec l’interface existante.

Le style actuel est déjà identifiable : interface locale sombre, fond vert/noir, accents vert/cyan, cartes translucides, badges arrondis, boutons simples, ambiance “console locale sécurisée”. Il faut l’étendre proprement, pas le remplacer.

## Principe directeur

Conserver l’identité existante, améliorer la hiérarchie.

La nouvelle UI doit donner une impression de produit plus clair et mieux organisé, mais elle ne doit pas ressembler à une autre application. Ne pas repartir sur un design blanc, SaaS générique, Bootstrap, Tailwind par défaut, Material UI, ou une interface complètement différente.

## Sources de vérité

Le style visuel de référence est celui déjà présent dans :

- `frontend/out/index.html`
- `frontend/out/assets/styles.css`
- les classes existantes : `.shell`, `.header`, `.brand`, `.brand-mark`, `.nav`, `.hero`, `.safe-card`, `.card`, `.panel`, `.badge`, `.actions`, `.button`, `.grid`, `.report`.

Tout nouveau composant doit réutiliser ou étendre ces conventions.

## Tokens CSS existants à préserver

Les variables CSS existantes doivent rester la base du design :

```css
:root {
  --bg: #07110e;
  --panel: rgba(246, 241, 224, 0.08);
  --panel-strong: rgba(246, 241, 224, 0.14);
  --text: #f6f1e0;
  --muted: #aab9ac;
  --line: rgba(246, 241, 224, 0.18);
  --green: #8cffb5;
  --amber: #ffd166;
  --red: #ff7a7a;
  --cyan: #6bdcff;
  --ink: #07110e;
}
```

Règles :

- Ne pas remplacer cette palette.
- Ne pas introduire une nouvelle palette majeure.
- Ne pas hardcoder des couleurs partout.
- Utiliser les variables existantes pour les nouveaux composants.
- Si une nouvelle nuance est indispensable, l’ajouter comme variable CSS dans `:root`, avec parcimonie.

Exemples acceptables :

```css
--panel-soft: rgba(246, 241, 224, 0.055);
--shadow-soft: rgba(0, 0, 0, 0.28);
```

Exemples à éviter :

```css
background: white;
color: black;
background: #2563eb;
box-shadow: 0 0 24px #00ff00;
```

## Fond et ambiance générale

Conserver le fond actuel :

- base sombre vert/noir ;
- gradients radiaux cyan/vert ;
- effet discret de grille/noise via `.noise` ;
- impression d’application locale technique mais soignée.

Ne pas rendre l’interface plus “corporate SaaS” ou plus “dashboard financier générique”. GarminSyncWeight doit rester une console locale sécurisée et maîtrisée.

## Typographie

Conserver la logique actuelle :

- police système : `"Segoe UI", "Aptos", sans-serif` ;
- titres larges et denses ;
- labels techniques courts en uppercase via `.eyebrow` ;
- textes secondaires avec `--muted` ;
- forte hiérarchie entre titre, résumé, détail technique.

Ne pas ajouter de webfont externe.

Hiérarchie recommandée :

- `h1` : titre de page/dashboard, fort mais pas inutilement énorme si l’espace doit servir au contenu métier ;
- `h2` : titre de carte ;
- `.eyebrow` : catégorie courte, par exemple “WITHINGS”, “GARMIN”, “APERÇU AVANT SYNCHRONISATION” ;
- `.message`, `.lede`, `.muted` : explications courtes, lisibles, non redondantes.

## Layout global

Conserver `.shell` comme conteneur principal :

```css
.shell {
  width: min(1180px, calc(100vw - 32px));
  margin: 0 auto;
}
```

Le Dashboard doit rester dans cette largeur.

La page principale doit être organisée autour du workflow :

1. état global ;
2. dernière mesure ;
3. graphique récent ;
4. tableau Withings → Garmin ;
5. actions de synchronisation ;
6. résultat de dernière synchronisation.

La structure doit être plus claire, pas plus chargée.

## Header et navigation

Conserver :

- `.header` sticky ;
- `.brand` ;
- `.brand-mark` avec le carré arrondi “GS” ;
- navigation en pills arrondis.

Adapter les libellés de navigation, mais pas le style général.

Navigation cible :

- Dashboard
- Historique
- Réglages
- Logs

`API` ne doit plus être un onglet principal. Le lien peut exister en discret dans les réglages ou le footer.

Les liens actifs doivent garder l’approche existante : bordure légère, fond translucide, texte clair.

## Cartes et panneaux

Les cartes sont un élément fort du style existant. Les nouveaux modules doivent continuer à utiliser des cartes translucides.

Base visuelle à conserver :

```css
.card,
.panel,
.safe-card {
  border: 1px solid var(--line);
  background: linear-gradient(180deg, var(--panel-strong), rgba(246, 241, 224, .055));
  border-radius: 28px;
  box-shadow: 0 24px 80px rgba(0,0,0,.28);
}
```

Règles :

- Ne pas passer à des rectangles plats et blancs.
- Ne pas utiliser des bordures trop contrastées.
- Ne pas réduire excessivement les rayons d’arrondi.
- Ne pas multiplier les ombres différentes.
- Garder une séparation claire entre cartes principales et détails secondaires.

## Badges d’état

Conserver le système de badges arrondis.

États recommandés :

- `ok` : prêt, connecté, synchronisé ;
- `warn` : partiel, attention, token trouvé mais non vérifié, mesure déjà existante ;
- `bad` : bloquant, erreur, non connecté ;
- neutre : inconnu, non vérifié, inactif.

Couleurs :

- OK : `--green`
- Warning : `--amber`
- Error : `--red`
- Info : `--cyan` si nécessaire, sans excès

Les badges doivent aider à comprendre, pas décorer.

## Boutons

Conserver le style actuel :

- bouton principal vert (`--green`) ;
- bouton secondaire translucide ;
- bouton danger rouge (`--red`) ;
- coins arrondis ;
- texte dense et lisible.

Règles :

- Une seule action principale par zone.
- Les actions secondaires doivent être visuellement moins fortes.
- Pendant une action réseau, désactiver le bouton et afficher un libellé explicite.
- Éviter les boutons nombreux sur la même ligne si cela brouille le choix.

Exemples :

- Principal : “Synchroniser cette mesure”
- Secondaire : “Rafraîchir les mesures”
- Secondaire : “Choisir une période”
- Danger : “Déconnecter Withings”

## DashboardStatusBar

Créer une barre d’état compacte, cohérente avec `.panel` ou `.card`, mais moins haute qu’une grande carte.

Contenu cible :

```text
Withings connecté · Garmin prêt · Dernière mesure : aujourd’hui 07:42 · Dernière sync : hier 08:03
```

Règles visuelles :

- fond translucide ;
- petits badges ;
- texte court ;
- pas de JSON ;
- responsive ;
- pas trop d’icônes.

## LatestMeasurementCard

La dernière mesure doit être le point d’entrée métier du Dashboard.

Exemple :

```text
Dernière mesure détectée
88,4 kg
Body Cardio+ · 21 juin 2026 · 07:42
```

Puis tuiles de métriques :

- masse grasse ;
- masse musculaire ;
- masse osseuse ;
- IMC ;
- métabolisme basal si disponible ;
- âge métabolique si disponible ;
- graisse viscérale si disponible.

Style :

- grande valeur de poids ;
- tuiles compactes ;
- même palette ;
- pas de surcharge ;
- valeurs absentes indiquées clairement.

## MeasurementMetricTile

Créer des petites tuiles pour les métriques secondaires.

Structure :

```text
Masse grasse
17,8 %
```

Règles :

- fond `var(--panel)` ;
- bordure `var(--line)` ;
- rayon cohérent ;
- label muted ;
- valeur claire.

## MeasurementSparkline

Le graphique doit être léger et intégré dans le style existant.

Objectif : confirmer visuellement que Withings remonte des mesures récentes.

Règles :

- graphique simple ;
- pas de grosse librairie si inutile ;
- SVG ou canvas acceptable ;
- ligne utilisant `--green` ou `--cyan` ;
- axes très discrets ou absents ;
- afficher un état vide si moins de deux points ;
- ne pas créer un dashboard analytique lourd.

## MappingPreviewTable — Withings → Garmin

Le tableau est central. Il doit être lisible, dense et rassurant.

Colonnes recommandées :

- Champ
- Withings
- Garmin prévu
- Décision

Règles :

- utiliser le style sombre existant ;
- en-tête sobre ;
- lignes séparées par `--line` ;
- décisions sous forme de badge ou texte court ;
- pas de couleurs criardes ;
- scroll horizontal propre sur mobile si nécessaire ;
- ne pas mentir sur les champs ignorés.

Exemples de décisions :

- “Sera envoyé”
- “Calculé”
- “Ignoré volontairement”
- “Absent”
- “Déjà présent”
- “Conflit”
- “Non supporté”

L’hydratation Withings en kg doit être affichée comme ignorée si elle n’est pas mappée vers Garmin. Ne pas inventer de conversion.

## SyncActionPanel

Ce panneau contient les actions de synchronisation.

Règles :

- action principale visible ;
- action secondaire moins forte ;
- expliquer brièvement ce qui va se passer ;
- désactiver si la prévisualisation indique que la sync n’est pas possible ;
- afficher un état de chargement ;
- empêcher les doubles clics.

Exemple :

```text
Synchronisation
Les données affichées dans le tableau seront envoyées à Garmin Connect.
[Synchroniser cette mesure]
[Rafraîchir les mesures] [Choisir une période]
```

## SyncResultCard

Ne pas afficher le résultat principal en JSON brut.

Afficher d’abord :

```text
Synchronisation terminée
1 mesure synchronisée
0 doublon
0 conflit
0 erreur
```

Puis détails lisibles :

```text
21/06/2026 07:42 — 88,4 kg — synchronisé
Hydratation ignorée volontairement
```

Puis accordéon :

```text
Voir détails techniques
```

Le JSON complet peut rester dans l’accordéon.

## TechnicalDetailsAccordion

Les détails techniques doivent rester accessibles mais non prioritaires.

À mettre dans les détails techniques :

- MCP ;
- Taxuspt/garmin_mcp ;
- token_dir ;
- payload JSON ;
- méthode `add_body_composition` ;
- réponse brute Garmin ;
- logs courts ;
- erreurs techniques détaillées.

Ne pas mettre ces informations comme titre principal de carte.

## Réglages Withings/Garmin

Les pages Withings et Garmin doivent devenir des sections de `Réglages`.

### Withings

Titre : “Withings”

Texte possible :

```text
Withings fournit les mesures de poids et de composition corporelle.
```

Actions :

- Connecter Withings
- Vérifier la connexion
- Rafraîchir les mesures
- Déconnecter

### Garmin

Titre principal :

```text
Garmin Connect prêt
```

ou :

```text
Garmin prêt pour la synchronisation
```

Ne pas utiliser en titre principal :

```text
Garmin MCP Taxuspt connected
```

Cette information doit être dans les détails techniques.

## États vides, erreurs et chargement

Chaque zone doit gérer :

- chargement ;
- succès ;
- erreur ;
- état vide ;
- état partiel.

Les messages doivent être orientés utilisateur.

Mauvais :

```text
500 Internal Server Error
```

Bon :

```text
Impossible de récupérer les mesures Withings. Le token est peut-être expiré. Reconnecte Withings depuis les réglages.
```

## Responsive

Le style doit rester correct sur :

- desktop ;
- tablette ;
- mobile.

Règles :

- le header peut passer en colonne comme actuellement ;
- les grilles doivent passer en une colonne sous 860 px ;
- le tableau Withings → Garmin peut utiliser un scroll horizontal propre ;
- les boutons doivent rester accessibles ;
- éviter les cartes trop hautes sans contenu utile.

## À ne pas faire

Ne pas :

- changer radicalement la palette ;
- ajouter Tailwind, Bootstrap, Material UI ou une grosse librairie UI ;
- transformer l’app en interface blanche ;
- remplacer les cartes translucides par des cards plates génériques ;
- afficher les JSON comme contenu principal ;
- mettre MCP/Taxuspt en information principale ;
- multiplier les animations ;
- ajouter des icônes décoratives sans fonction ;
- créer une UI différente page par page ;
- introduire des styles inline dispersés ;
- casser la navigation SPA existante.

## Critères d’acceptation style

La refonte respecte le style si :

1. On reconnaît immédiatement GarminSyncWeight après les changements.
2. Le fond sombre, les gradients et la logique de cartes translucides sont conservés.
3. Les nouvelles sections utilisent les variables CSS existantes.
4. Le Dashboard paraît plus clair, mais pas visuellement étranger au projet.
5. Les détails techniques sont accessibles sans dominer l’écran.
6. Les composants ont une cohérence de spacing, rayon, couleur et typographie.
7. L’interface reste lisible et responsive.
8. Aucun framework UI lourd n’a été ajouté sans nécessité.
