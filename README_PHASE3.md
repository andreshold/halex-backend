# Halex Phase 3 — moteur normatif

## Objectif

Le retrieval trouve les textes pertinents. Le moteur normatif qualifie ensuite
leur rôle AVANT la rédaction finale.

Flux :

QUESTION
→ résolution conversationnelle
→ retrieval vectoriel
→ expansion références explicites
→ enrichissement modifications
→ qualification normative
→ résolution déterministe des incompatibilités
→ contexte ordonné
→ LLM rédacteur

## Règle de décision

Une décision de priorité n'est prise que lorsqu'une incompatibilité a été
explicitement qualifiée.

Ordre :
1. statut/applicabilité
2. relation explicite déjà enrichie
3. rang
4. spécialité à rang égal
5. date juridique à rang égal
6. conflit non résolu

`date_publication` ne participe jamais à la primauté.

## Rôle du LLM de qualification

Le qualificateur peut dire :
- principal
- complémentaire
- contexte
- non pertinent

et qualifier :
- complémentarité
- spécialité
- contradiction
- même régime
- indépendant
- incertain

Il ne choisit jamais le texte gagnant.

## Installation

Copier dans le backend :
- `moteur_normatif.py`
- `halex_core_supabase.py`
- `api.py`

Le projet doit déjà contenir :
- `conversation_context.py`
- `schema_metadata.py` avec Loi/Code/Décret = rang 30
- `modifications.py`

Côté frontend, remplacer `Chat.jsx` par la version fournie si vous voulez
conserver le diagnostic `normatif` dans le state.

Aucune migration SQL Supabase supplémentaire n'est requise pour cette phase.

## Tests

Sans réseau :
```powershell
python test_phase3_normatif.py
```

Attendu :
```text
OK — moteur normatif déterministe Phase 3
```

Qualificateur live :
```powershell
python test_phase3_live.py
```

API complète :
```powershell
python test_phase3_api.py
```

## Diagnostic API

Une réponse vectorielle contient désormais :

```json
{
  "conversation": {...},
  "normatif": {
    "documents": [...],
    "relations": [...],
    "decisions": [...],
    "conflits_non_resolus": [...]
  }
}
```

Ce diagnostic est destiné au développement. Il n'est pas nécessaire de
l'afficher au citoyen.
