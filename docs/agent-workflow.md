# Workflow Agent — GarminSyncWeight

Système de modification du code en deux étapes via des agents spécialisés.
Un agent analyse et planifie (read-only), l'autre implémente.

---

## Vue d'ensemble

```
┌─────────────────────┐     ┌──────────────────────────┐     ┌──────────────────────┐
│  modification.txt    │────▶│  agent_brainstorm.md     │────▶│  modifications_       │
│  (toi qui écris)    │     │  (analyse + planifie)    │     │  brainstorm.md        │
└─────────────────────┘     └──────────────────────────┘     └──────────┬───────────┘
                                                                        │
                                                                        ▼
                                                              ┌──────────────────────┐
                                                              │  agent_dev.md        │
                                                              │  (implémente)        │
                                                              └──────────┬───────────┘
                                                                         │
                                                                         ▼
                                                              ┌──────────────────────┐
                                                              │  Code modifié        │
                                                              │  + tests verts       │
                                                              └──────────────────────┘
```

---

## Fichiers

| Fichier | Rôle | Qui l'écrit |
|---|---|---|
| `agents/modification.txt` | Demandes de changement en langage naturel | **Toi** |
| `agents/agent_brainstorm.md` | Prompt de l'agent analyste (read-only) | Fourni (ne pas modifier) |
| `agents/modifications_brainstorm.md` | Plan d'implémentation détaillé | Agent Brainstorm |
| `agents/agent_dev.md` | Prompt de l'agent développeur | Fourni (ne pas modifier) |

---

## Comment l'utiliser

### Étape 1 — Écris tes modifications

Ouvre `agents/modification.txt` et décris ce que tu veux changer, en langage naturel.
Tu peux faire des listes, écrire en prose, mélanger les deux. Sois précis mais pas technique.

Exemple :
```
Je voudrais que l'historique des mesures affiche aussi la date au format français.
Aussi, le bouton "Sync" devrait être bleu au lieu de vert.
```

### Étape 2 — Lance l'agent Brainstorm

1. Ouvre OpenCode
2. Copie le contenu de `agents/agent_brainstorm.md` comme prompt système
3. L'agent va :
   - Lire `AGENTS.md` et la documentation du projet
   - Lire `agents/modification.txt`
   - Analyser les fichiers concernés
   - Générer `agents/modifications_brainstorm.md`

**Important** : l'agent Brainstorm ne modifie JAMAIS le code. Il lit et planifie uniquement.

### Étape 3 — Vérifie le plan

Ouvre `agents/modifications_brainstorm.md` et vérifie que :
- Toutes tes demandes sont couvertes
- Les étapes sont logiques et dans le bon ordre
- Rien d'important n'a été oublié

Si quelque chose ne va pas, modifie `modification.txt` et relance l'étape 2.

### Étape 4 — Lance l'agent Dev

1. Ouvre une NOUVELLE session OpenCode (ne pas mélanger avec Brainstorm)
2. Copie le contenu de `agents/agent_dev.md` comme prompt système
3. L'agent va :
   - Lire `AGENTS.md` et la documentation du projet
   - Lire `agents/modifications_brainstorm.md`
   - Lire tous les fichiers concernés
   - Implémenter chaque étape du plan
   - Vérifier que les tests passent et que le lint est propre

### Étape 5 — Commit

Une fois l'implémentation terminée et vérifiée :
```powershell
git add -A
git commit -m "feat: description des changements"
git push
```

---

## Détail des agents

### Agent Brainstorm (`agent_brainstorm.md`)

| Propriété | Valeur |
|---|---|
| Rôle | Architecte / Analyste |
| Peut modifier le code | ❌ Non (read-only) |
| Peut lire le code | ✅ Oui |
| Peut utiliser explore/librarian | ✅ Oui |
| Output | `agents/modifications_brainstorm.md` uniquement |

**Ce qu'il fait :**
1. Lit `AGENTS.md`, `docs/architecture.md`, `docs/security.md` pour comprendre le projet
2. Lit `agents/modification.txt` — le langage naturel de l'utilisateur
3. Analyse les fichiers qui seraient impactés par les changements
4. Produit un plan structuré avec :
   - Résumé en français
   - Liste des fichiers concernés
   - Étapes d'implémentation détaillées (fichiers, changements précis, patterns à suivre)
   - Tests à créer ou modifier
   - Points d'attention et risques
   - Checklist de vérification post-implémentation

**Ce qu'il NE fait PAS :**
- Modifier du code
- Éditer des fichiers (sauf `modifications_brainstorm.md`)
- Exécuter des commandes mutatives
- Deviner en cas d'ambiguïté (il la signale explicitement)

### Agent Dev (`agent_dev.md`)

| Propriété | Valeur |
|---|---|
| Rôle | Développeur Senior |
| Peut modifier le code | ✅ Oui |
| Peut lire le code | ✅ Oui |
| Peut exécuter des commandes | ✅ Oui (ruff, pytest) |
| Output | Code modifié + tests verts |

**Ce qu'il fait :**
1. Lit `AGENTS.md`, `docs/architecture.md`, `config.py` pour comprendre le projet
2. Lit `agents/modifications_brainstorm.md` — le plan d'implémentation
3. Lit chaque fichier avant de le modifier
4. Implémente étape par étape :
   - Applique le changement
   - Vérifie avec `lsp_diagnostics`
   - Lance les tests concernés
   - Passe à l'étape suivante
5. Vérification finale : `ruff check` + `pytest` complets

**Règles strictes qu'il suit :**
- Imports en `app.` (jamais `backend.app.`)
- Settings frozen, injection de test GarminClient
- Pas de mock au niveau garminconnect
- Redaction automatique des logs (pas de redaction manuelle)
- Port `127.0.0.1:8010` uniquement
- Jamais de `@ts-ignore`, `as any`, suppression de tests
- Style de code identique au code existant

---

## Format de `modifications_brainstorm.md`

Le plan généré par Brainstorm suit cette structure :

```markdown
# Modifications Brainstorm — {YYYY-MM-DD}

## Résumé
(résumé 2-4 phrases en français)

## Demande originale
(copie du contenu de modification.txt)

## Fichiers concernés
| Fichier | Rôle dans les modifications |
|---|---|

## Étapes d'implémentation
### Étape 1 — Titre
- Fichier(s)
- Description
- Changements précis
- Pattern à suivre
- Tests
- Risques

### Étape 2 — Titre
...

## Ordre d'exécution recommandé

## Points d'attention

## Checklist de vérification post-implémentation
```

---

## Bonnes pratiques

1. **Une demande à la fois** — ne mélange pas 10 changements dans le même `modification.txt`
2. **Relis le plan Brainstorm** avant de le donner au Dev — c'est ton dernier point de contrôle
3. **Session propre pour le Dev** — ne réutilise pas la session Brainstorm
4. **Si le Dev échoue** — vérifie le plan Brainstorm, affine `modification.txt`, recommence
5. **Commit après chaque cycle** — un commit par `modification.txt` traité
